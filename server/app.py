"""Converter backend for it-tools fork.

- Office (docx/pptx/xlsx/odt/md/html/txt) -> PDF via LibreOffice headless
- PDF -> text via pypdf
- PDF -> images (zip) via PyMuPDF
- Media (audio/video) -> convert/trim via ffmpeg binary (fallback for large files)
- Jobs API: long-running ffmpeg work with progress / pause / resume / cancel
"""
import io
import os
import re
import signal
import subprocess
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from pypdf import PdfReader, PdfWriter

app = FastAPI(title='it-tools converter API', version='0.1.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=False,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.get('/health')
def health():
    return {'status': 'ok'}


def _safe_suffix(name: str) -> str:
    suf = Path(name).suffix.lower()
    return suf if len(suf) <= 8 else ''


# ---------------------------------------------------------------- jobs ---

JOB_ROOT = Path(tempfile.gettempdir()) / 'it-jobs'
JOB_ROOT.mkdir(parents=True, exist_ok=True)
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_TIME_RE = re.compile(r'time=(\d+):(\d+):([\d.]+)')

MEDIA_MIME = {'mp3': 'audio/mpeg', 'wav': 'audio/wav', 'ogg': 'audio/ogg',
              'm4a': 'audio/mp4', 'flac': 'audio/flac', 'mp4': 'video/mp4',
              'webm': 'video/webm', 'gif': 'image/gif',
              'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg'}


def _ffprobe_duration(path: Path) -> float | None:
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
            capture_output=True, text=True, timeout=30)
        d = float((r.stdout or '').strip())
        return d if d > 0 else None
    except Exception:
        return None


def _media_encode_args(fmt: str, crf: int = 23, resolution: str = 'original',
                       bitrate: str = '192k', fps: int = 15, gif_width: int = 480) -> list[str]:
    if fmt == 'mp4':
        args = ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', str(crf),
                '-c:a', 'aac', '-b:a', '128k']
    elif fmt == 'webm':
        args = ['-c:v', 'libvpx-vp9', '-b:v', '1M', '-c:a', 'libopus']
    elif fmt == 'mp3':
        return ['-vn', '-c:a', 'libmp3lame', '-b:a', bitrate]
    elif fmt == 'gif':
        return ['-vf', f'fps={fps},scale={gif_width}:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse']
    elif fmt == 'wav':
        return ['-c:a', 'pcm_s16le']
    elif fmt == 'ogg':
        return ['-c:a', 'libvorbis', '-b:a', bitrate]
    elif fmt == 'm4a':
        return ['-c:a', 'aac', '-b:a', bitrate]
    elif fmt == 'flac':
        return ['-c:a', 'flac']
    else:
        raise HTTPException(400, f'Unsupported format: {fmt}')
    if fmt in ('mp4', 'webm') and resolution != 'original':
        args += ['-vf', f'scale=-2:{int(resolution)}']
    return args


def _job_public(job: dict) -> dict:
    return {k: job[k] for k in
            ('id', 'name', 'format', 'status', 'progress', 'created_at',
             'error', 'out_filename', 'out_size') if k in job}


def _run_media_job(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return
        # giữ 'queued' cho tới khi ffmpeg spawn xong (tránh race pause/cancel sớm)
    workdir: Path = job['workdir']
    try:
        total = 0.0
        for src in job['inputs']:
            d = _ffprobe_duration(workdir / src)
            if d:
                total += d
        # trim rút ngắn thời lượng ước tính
        if job.get('trim_duration'):
            try:
                total = min(total, float(job['trim_duration']))
            except ValueError:
                pass
        job['duration'] = total or None

        with _jobs_lock:
            if job['status'] == 'canceled':
                return
        if len(job['inputs']) > 1 or job.get('merge'):
            lst = workdir / 'concat.txt'
            lst.write_text(''.join(f"file '{s}'\n" for s in job['inputs']))
            cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', str(lst)]
        else:
            cmd = ['ffmpeg', '-y']
            if job.get('trim_start'):
                cmd += ['-ss', str(job['trim_start'])]
            cmd += ['-i', str(workdir / job['inputs'][0])]
        if job.get('trim_duration'):
            cmd += ['-t', str(job['trim_duration'])]
        out_name = f"output.{job['format']}"
        cmd += _media_encode_args(job['format'], job.get('crf', 23),
                                 job.get('resolution', 'original'),
                                 bitrate=job.get('bitrate', '192k'),
                                 fps=job.get('fps', 15),
                                 gif_width=job.get('gif_width', 480)) + [str(workdir / out_name)]
        job['cmd'] = ' '.join(cmd)

        proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True, bufsize=1,
                                start_new_session=True)
        job['proc'] = proc
        with _jobs_lock:
            if job['status'] == 'queued':
                job['status'] = 'running'
        assert proc.stderr is not None
        for line in proc.stderr:
            m = _TIME_RE.search(line)
            if m and job.get('duration'):
                t = int(m.group(1)) * 3600 + int(m.group(2)) + float(m.group(3))
                p = max(0.0, min(1.0, t / job['duration']))
                job['progress'] = max(job.get('progress', 0.0), p)
        proc.wait()
        with _jobs_lock:
            if job['status'] == 'canceled':
                return
            if proc.returncode == 0 and (workdir / out_name).exists():
                job['status'] = 'done'
                job['progress'] = 1.0
                job['out_filename'] = f"{Path(job['name']).stem}.{job['format']}"
                job['out_size'] = (workdir / out_name).stat().st_size
            else:
                job['status'] = 'error'
                job['error'] = f'ffmpeg exit {proc.returncode}'
    except Exception as e:
        with _jobs_lock:
            if job['status'] != 'canceled':
                job['status'] = 'error'
                job['error'] = str(e)[:500]
    finally:
        with _jobs_lock:
            job.pop('proc', None)
        _cleanup_jobs()


def _cleanup_jobs():
    # giữ tối đa 50 job, xóa job xong quá 24h (kèm file tạm)
    with _jobs_lock:
        ids = sorted(_jobs, key=lambda i: _jobs[i]['created_at'])
        while len(ids) > 50:
            _drop_job(ids.pop(0))
        now = time.time()
        for i in ids:
            j = _jobs[i]
            if j['status'] in ('done', 'error', 'canceled') and now - j['created_at'] > 86400:
                _drop_job(i)


def _drop_job(job_id: str):
    job = _jobs.pop(job_id, None)
    if not job:
        return
    proc = job.get('proc')
    if proc and proc.poll() is None:
        try:
            proc.terminate()
        except Exception:
            pass
    try:
        import shutil
        shutil.rmtree(job['workdir'], ignore_errors=True)
    except Exception:
        pass


@app.post('/jobs/media')
async def create_media_job(
    files: list[UploadFile] = File(...),
    format: str = Form('mp4'),
    crf: int = Form(23),
    resolution: str = Form('original'),
    trim_start: str = Form(''),
    trim_duration: str = Form(''),
    merge: bool = Form(False),
    bitrate: str = Form('192k'),
    fps: int = Form(15),
    gif_width: int = Form(480),
):
    """Tạo job ffmpeg chạy nền: convert 1 file hoặc merge nhiều file theo thứ tự."""
    fmt = format.lower().strip()
    if fmt not in MEDIA_MIME:
        raise HTTPException(400, f'format must be one of {sorted(MEDIA_MIME)}')
    if not files:
        raise HTTPException(400, 'No files')
    if len(files) > 20:
        raise HTTPException(400, 'Too many files (max 20)')
    job_id = uuid.uuid4().hex[:12]
    workdir = JOB_ROOT / job_id
    workdir.mkdir(parents=True, exist_ok=True)
    names = []
    for i, f in enumerate(files):
        data = await f.read()
        if len(data) > 1024 * 1024 * 1024:
            raise HTTPException(413, f'{f.filename}: file too large (>1GB)')
        safe = f'{i:02d}_{(f.filename or "input").replace("/", "_")}'
        (workdir / safe).write_bytes(data)
        names.append(safe)
    job = {
        'id': job_id, 'name': files[0].filename or 'media',
        'format': fmt, 'status': 'queued', 'progress': 0.0,
        'created_at': time.time(), 'error': None,
        'out_filename': None, 'out_size': None,
        'workdir': workdir, 'inputs': names, 'merge': merge or len(names) > 1,
        'crf': max(0, min(51, crf)), 'resolution': resolution,
        'trim_start': trim_start.strip(), 'trim_duration': trim_duration.strip(),
        'bitrate': bitrate.strip() or '192k',
        'fps': max(1, min(60, fps)), 'gif_width': max(160, min(1280, gif_width)),
    }
    with _jobs_lock:
        _jobs[job_id] = job
    threading.Thread(target=_run_media_job, args=(job_id,), daemon=True).start()
    return _job_public(job)


def _stitch_vertical(images: list, progress_cb) -> 'np.ndarray':
    """Ghep screenshot cuon doc: bo header/footer tinh, tim do cuon giua cac anh."""
    import cv2
    import numpy as np
    h = min(im.shape[0] for im in images)
    w = min(im.shape[1] for im in images)
    images = [im[:h, :w] for im in images]
    grays = [cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.int16) for im in images]
    # pixel "dong" = khac nhau o it nhat 1 cap anh lien tiep
    diff = np.zeros((h, w), np.int16)
    for a, b in zip(grays, grays[1:]):
        diff = np.maximum(diff, np.abs(a - b))
    moving = diff > 25
    row_dyn = np.append(moving.mean(1) > 0.02, False)
    col_dyn = np.where(moving.mean(0) > 0.02)[0]
    # vung cuon = doan hang dong dai nhat (cho phep khe nho), ngoai ra la header/footer
    y0, y1, start, gap = 0, h, None, 0
    for y, dyn in enumerate(row_dyn):
        if dyn:
            start, gap = (y if start is None else start), 0
        elif start is not None:
            gap += 1
            if gap > h // 50 or y == h:
                end = y - gap + 1
                if (y0, y1) == (0, h) or end - start > y1 - y0:
                    y0, y1 = start, end
                start, gap = None, 0
    rh = y1 - y0
    x0, x1 = (col_dyn[0], col_dyn[-1] + 1) if len(col_dyn) else (0, w)

    def score(a, b, dy):
        # a[dy:] khop b[:-dy]; chi tinh pixel co noi dung de nen trong khong lam diem thap gia
        x, y = a[dy:], b[:a.shape[0] - dy]
        ink = np.maximum(x, y) > 40
        n = ink.sum()
        return float(np.abs(x - y)[ink].sum() / n) if n > ink.size * 0.01 else 1e9

    s = 4
    small = [cv2.resize(g[y0:y1, x0:x1].astype(np.uint8), None, fx=1 / s, fy=1 / s,
                        interpolation=cv2.INTER_AREA).astype(np.float32) for g in grays]
    min_ov = max(8, rh // 10)
    offsets = []
    for i in range(len(images) - 1):
        a, b = small[i], small[i + 1]
        d = int(np.argmin([score(a, b, k) for k in range(a.shape[0] - min_ov // s)])) * s
        A = grays[i][y0:y1, x0:x1].astype(np.float32)
        B = grays[i + 1][y0:y1, x0:x1].astype(np.float32)
        d = min(range(max(0, d - s), min(rh - min_ov, d + s) + 1), key=lambda k: score(A, B, k))
        offsets.append(d)
        progress_cb((i + 1) / len(images))

    tops = np.concatenate([[0], np.cumsum(offsets)]).astype(int)
    total = tops[-1] + rh
    reg = [im[y0:y1] for im in images]
    # nut noi (mui ten, play, thanh cuon...) co dinh tren man hinh: o (hang, dai cot)
    # nao hay lech giua 2 anh chong lap thi bi phat -> lay o do tu anh khac
    bw = 64
    nb = (w + bw - 1) // bw
    votes = np.zeros((rh, nb), np.float32)
    for i, d in enumerate(offsets):
        a, b = reg[i][d:].astype(np.int16), reg[i + 1][:rh - d].astype(np.int16)
        bad = (np.abs(a - b).max(2) > 12).astype(np.float32)
        bad = np.pad(bad, ((0, 0), (0, nb * bw - w))).reshape(rh - d, nb, bw).sum(2)
        votes[d:] += bad
        votes[:rh - d] += bad
    votes = cv2.dilate(votes, np.ones((31, 3), np.uint8))
    # nut noi co dinh: 2 anh lien tiep giong nhau tai cung vi tri man hinh
    # trong khi noi dung tuong ung (da cuon) lai khac -> danh dau o ca 2 anh
    bg = np.median(np.concatenate([r[::16, ::16].reshape(-1, 3) for r in reg]), axis=0)
    fixed = [np.zeros((rh, w), bool) for _ in reg]
    k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    k3 = np.ones((3, 3), np.uint8)

    def grow(core, cand):
        # mo rong loi -> ca vung "khac noi dung" lien thong (vien/bong cua nut)
        n, lab = cv2.connectedComponents(cv2.dilate((cand | core).astype(np.uint8), k3))
        keep = np.isin(lab, np.unique(lab[core])) & (lab > 0)
        return cv2.dilate(keep.astype(np.uint8), np.ones((11, 11), np.uint8)).astype(bool)

    for i, d in enumerate(offsets):
        a, b = reg[i].astype(np.int16), reg[i + 1].astype(np.int16)
        ink_a, ink_b = np.abs(a - bg).max(2) > 20, np.abs(b - bg).max(2) > 20
        same = (np.abs(a - b).max(2) < 16) & ink_a & ink_b
        diff = np.abs(a[d:] - b[:rh - d]).max(2) > 30
        moved_a, moved_b = np.zeros((rh, w), bool), np.zeros((rh, w), bool)
        moved_a[d:], moved_b[:rh - d] = diff, diff
        core = cv2.morphologyEx((same & (moved_a | moved_b)).astype(np.uint8),
                                cv2.MORPH_OPEN, k_open).astype(bool)
        if core.any():
            # ngoai vung chong lap khong co "noi dung tuong ung" -> dung dieu kien giong nhau
            near = np.abs(a - b).max(2) < 16
            out_a, out_b = np.ones(rh, bool), np.ones(rh, bool)
            out_a[d:], out_b[:rh - d] = False, False
            fixed[i] |= grow(core, (moved_a | (near & out_a[:, None])) & (np.abs(a - bg).max(2) > 8))
            fixed[i + 1] |= grow(core, (moved_b | (near & out_b[:, None])) & (np.abs(b - bg).max(2) > 8))
    # uu tien giua anh: mep vung cuon hay dinh bong do cua header/footer
    pen = np.abs(np.arange(rh) - rh / 2) / rh
    pen[:rh // 8] += 500
    pen[-(rh // 8):] += 500
    cost = votes + pen[:, None]
    best = np.full((total, nb), np.inf, np.float32)
    src = np.zeros((total, nb), int)
    for i in range(len(reg)):
        sl = slice(tops[i], tops[i] + rh)
        f = np.pad(fixed[i], ((0, 0), (0, nb * bw - w))).reshape(rh, nb, bw).any(2)
        c = cost + f * 1e4
        take = c < best[sl]
        best[sl][take], src[sl][take] = c[take], i
    content = np.zeros((total, w, 3), np.uint8)
    for i in range(len(reg)):
        sl = slice(tops[i], tops[i] + rh)
        m = np.repeat(src[sl] == i, bw, axis=1)[:, :w]
        content[sl][m] = reg[i][m]
        # khong anh nao khac phu cho nay -> to mau nen de xoa nut
        # (bo qua nut cham mep vung cuon, vi phan con lai nam trong header/footer)
        n, lab = cv2.connectedComponents(fixed[i].astype(np.uint8))
        edge = np.unique(np.concatenate([lab[0], lab[-1]]))
        content[sl][m & fixed[i] & ~np.isin(lab, edge)] = bg
    return np.vstack([images[0][:y0], content, images[-1][y1:]])


def _run_stitch_job(job_id: str):
    import cv2
    import numpy as np
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job['status'] = 'running'
    workdir: Path = job['workdir']
    try:
        files = sorted(workdir.glob('img-*'), key=lambda p: p.name)
        if job.get('order') != 'upload':
            names: list[str] = job.get('orig_names', [])
            order_idx = sorted(range(len(files)),
                               key=lambda i: names[i] if i < len(names) else '')
            if job.get('order') == 'reverse':
                order_idx = order_idx[::-1]
            files = [files[i] for i in order_idx]
        images = []
        for f in files:
            data = np.frombuffer(f.read_bytes(), dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError(f'Cannot decode {f.name}')
            images.append(img)
            with _jobs_lock:
                if job['status'] == 'canceled':
                    return
        if len(images) < 2:
            raise ValueError('Need at least 2 images')

        def progress_cb(p: float):
            with _jobs_lock:
                if job['status'] == 'paused':
                    pass
                job['progress'] = max(job.get('progress', 0.0), min(0.99, p))
            ev = job.get('pause_event')
            while ev is not None and not ev.is_set():
                if job.get('status') == 'canceled':
                    raise InterruptedError('canceled')
                time.sleep(0.2)

        if job.get('mode') == 'panorama':
            stitcher = cv2.Stitcher_create(cv2.Stitcher_PANORAMA)
            status, pano = stitcher.stitch(images)
            if status != cv2.Stitcher_OK:
                stitcher = cv2.Stitcher_create(cv2.Stitcher_SCANS)
                status, pano = stitcher.stitch(images)
            if status != cv2.Stitcher_OK:
                raise ValueError(f'Stitcher failed (code {status}), thử chế độ cuộn dọc')
            result = pano
            progress_cb(1.0)
        else:
            result = _stitch_vertical(images, progress_cb)

        fmt = job['format']
        out_name = f'output.{fmt}'
        ok = cv2.imwrite(str(workdir / out_name), result,
                         [int(cv2.IMWRITE_JPEG_QUALITY), 92] if fmt == 'jpg' else [])
        if not ok:
            raise ValueError('Cannot write output')
        with _jobs_lock:
            if job['status'] == 'canceled':
                return
            job['status'] = 'done'
            job['progress'] = 1.0
            job['out_filename'] = f'stitched.{fmt}'
            job['out_size'] = (workdir / out_name).stat().st_size
    except InterruptedError:
        pass
    except Exception as e:
        with _jobs_lock:
            if job['status'] != 'canceled':
                job['status'] = 'error'
                job['error'] = str(e)[:500]
    finally:
        _cleanup_jobs()


@app.post('/jobs/stitch')
async def create_stitch_job(
    files: list[UploadFile] = File(...),
    mode: str = Form('scroll'),
    order: str = Form('name'),
    format: str = Form('jpg'),
):
    """Ghep anh: scroll = screenshot cuon doc (template-match), panorama = anh chup."""
    fmt = format.lower().strip()
    if fmt not in ('jpg', 'png'):
        raise HTTPException(400, 'format must be jpg or png')
    if mode not in ('scroll', 'panorama'):
        raise HTTPException(400, 'mode must be scroll or panorama')
    if order not in ('name', 'upload', 'reverse'):
        raise HTTPException(400, 'order must be name, upload or reverse')
    if not (2 <= len(files) <= 50):
        raise HTTPException(400, 'Send 2..50 images')
    job_id = uuid.uuid4().hex[:12]
    workdir = JOB_ROOT / job_id
    workdir.mkdir(parents=True, exist_ok=True)
    orig_names: list[str] = []
    for i, f in enumerate(files):
        data = await f.read()
        if len(data) > 100 * 1024 * 1024:
            raise HTTPException(413, f'{f.filename}: file too large (>100MB)')
        (workdir / f'img-{i:03d}').write_bytes(data)
        orig_names.append(f.filename or f'img-{i:03d}')
    job = {
        'id': job_id, 'name': f'stitch {len(files)} ảnh',
        'format': fmt, 'status': 'queued', 'progress': 0.0,
        'created_at': time.time(), 'error': None,
        'out_filename': None, 'out_size': None,
        'workdir': workdir, 'inputs': [], 'kind': 'stitch',
        'mode': mode, 'order': order, 'orig_names': orig_names,
        'pause_event': threading.Event(),
    }
    job['pause_event'].set()
    with _jobs_lock:
        _jobs[job_id] = job
    threading.Thread(target=_run_stitch_job, args=(job_id,), daemon=True).start()
    return _job_public(job)


@app.get('/jobs')
def list_jobs():
    with _jobs_lock:
        return [_job_public(_jobs[i]) for i in
                sorted(_jobs, key=lambda i: _jobs[i]['created_at'], reverse=True)]


@app.get('/jobs/{job_id}')
def get_job(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, 'Job not found')
        return _job_public(job)


def _signal_job(job_id: str, sig: int, to_status: str):
    # đợi tối đa ~15s cho ffmpeg spawn (job vừa tạo còn đang ffprobe)
    proc = None
    for _ in range(150):
        with _jobs_lock:
            job = _jobs.get(job_id)
            if not job:
                raise HTTPException(404, 'Job not found')
            if job.get('kind') == 'stitch':
                # job python thuần: đảo cờ pause, worker tự nhường
                job['status'] = to_status
                ev: threading.Event = job.get('pause_event')
                if ev is not None:
                    ev.clear() if to_status == 'paused' else ev.set()
                return _job_public(job)
            if job['status'] not in ('running', 'paused', 'queued'):
                raise HTTPException(409, f'Job is {job["status"]}, cannot change state')
            proc = job.get('proc')
            if proc is not None and proc.poll() is None:
                break
            proc = None
        time.sleep(0.1)
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, 'Job not found')
        proc = job.get('proc')
        if job['status'] not in ('running', 'paused') or not proc or proc.poll() is not None:
            raise HTTPException(409, f'Job is {job["status"]}, cannot change state')
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except Exception as e:
            raise HTTPException(500, f'Signal failed: {e}')
        job['status'] = to_status
        return _job_public(job)


@app.post('/jobs/{job_id}/pause')
def pause_job(job_id: str):
    return _signal_job(job_id, signal.SIGSTOP, 'paused')


@app.post('/jobs/{job_id}/resume')
def resume_job(job_id: str):
    return _signal_job(job_id, signal.SIGCONT, 'running')


@app.post('/jobs/{job_id}/cancel')
def cancel_job(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, 'Job not found')
        proc = job.get('proc')
        if proc and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                pass
        job['status'] = 'canceled'
        return _job_public(job)


@app.delete('/jobs/{job_id}')
def delete_job(job_id: str):
    with _jobs_lock:
        if job_id not in _jobs:
            raise HTTPException(404, 'Job not found')
    _drop_job(job_id)
    return {'deleted': job_id}


@app.get('/jobs/{job_id}/download')
def download_job(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, 'Job not found')
        if job['status'] != 'done':
            raise HTTPException(409, f'Job is {job["status"]}')
        path = job['workdir'] / f"output.{job['format']}"
    return FileResponse(path, media_type=MEDIA_MIME[job['format']],
                        filename=job.get('out_filename') or f'output.{job["format"]}')



@app.post('/convert/office-to-pdf')
async def office_to_pdf(files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(400, 'No files')
    outs: list[tuple[str, bytes]] = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for f in files:
            data = await f.read()
            if len(data) > 200 * 1024 * 1024:
                raise HTTPException(413, f'{f.filename}: file too large (>200MB)')
            src = tmp / f.filename.replace('/', '_')
            src.write_bytes(data)
            # LibreOffice converts in-place to same dir
            cmd = [
                'libreoffice', '--headless', '--convert-to', 'pdf',
                '--outdir', str(tmp), str(src),
            ]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            except FileNotFoundError:
                raise HTTPException(500, 'LibreOffice not installed in backend image')
            except subprocess.TimeoutExpired:
                raise HTTPException(500, f'{f.filename}: convert timeout')
            if r.returncode != 0:
                raise HTTPException(500, f'{f.filename}: LibreOffice failed: {(r.stderr or r.stdout)[:1000]}')
            pdf_path = tmp / (src.stem + '.pdf')
            if not pdf_path.exists():
                # try any pdf produced
                cands = list(tmp.glob('*.pdf'))
                if not cands:
                    raise HTTPException(500, f'{f.filename}: no PDF produced')
                pdf_path = cands[0]
            outs.append((pdf_path.stem + '.pdf', pdf_path.read_bytes()))
            # cleanup source to avoid re-pickup
            try:
                src.unlink(missing_ok=True)
                pdf_path.unlink(missing_ok=True)
            except Exception:
                pass

    if len(outs) == 1:
        name, blob = outs[0]
        return Response(content=blob, media_type='application/pdf',
                        headers={'Content-Disposition': f'attachment; filename="{name}"'})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, blob in outs:
            z.writestr(name, blob)
    buf.seek(0)
    return StreamingResponse(buf, media_type='application/zip',
                             headers={'Content-Disposition': 'attachment; filename="converted.zip"'})


@app.post('/convert/pdf-to-text')
async def pdf_to_text(files: list[UploadFile] = File(...)):
    if len(files) != 1:
        raise HTTPException(400, 'Send exactly 1 PDF')
    data = await files[0].read()
    try:
        reader = PdfReader(io.BytesIO(data))
        parts = []
        for i, page in enumerate(reader.pages):
            try:
                parts.append(f'--- page {i + 1} ---\n' + (page.extract_text() or ''))
            except Exception as e:
                parts.append(f'--- page {i + 1} (error: {e}) ---\n')
        text = '\n'.join(parts)
    except Exception as e:
        raise HTTPException(400, f'Invalid PDF: {e}')
    return Response(content=text.encode('utf-8'), media_type='text/plain; charset=utf-8')


@app.post('/convert/pdf-to-images')
async def pdf_to_images(files: list[UploadFile] = File(...), dpi: int = Form(150)):
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise HTTPException(500, 'PyMuPDF not installed')
    if len(files) != 1:
        raise HTTPException(400, 'Send exactly 1 PDF')
    dpi = max(72, min(dpi, 300))
    data = await files[0].read()
    try:
        doc = fitz.open(stream=data, filetype='pdf')
    except Exception as e:
        raise HTTPException(400, f'Invalid PDF: {e}')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=dpi)
            z.writestr(f'page-{i + 1:03d}.png', pix.tobytes('png'))
    buf.seek(0)
    return StreamingResponse(buf, media_type='application/zip',
                             headers={'Content-Disposition': 'attachment; filename="pages.zip"'})


@app.post('/convert/media')
async def media_convert(
    files: list[UploadFile] = File(...),
    format: str = Form('mp3'),
    extra_args: str = Form(''),
):
    """Fallback server-side ffmpeg for large files. format: mp3|wav|ogg|mp4|webm|gif"""
    allowed = {'mp3', 'wav', 'ogg', 'm4a', 'flac', 'mp4', 'webm', 'gif'}
    fmt = format.lower().strip()
    if fmt not in allowed:
        raise HTTPException(400, f'format must be one of {sorted(allowed)}')
    if len(files) != 1:
        raise HTTPException(400, 'Send exactly 1 media file')
    data = await files[0].read()
    if len(data) > 1024 * 1024 * 1024:
        raise HTTPException(413, 'File too large (>1GB)')
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        src = tmp / f'input{_safe_suffix(files[0].filename or "")}'
        src.write_bytes(data)
        out = tmp / f'output.{fmt}'
        cmd = ['ffmpeg', '-y', '-i', str(src)]
        if extra_args.strip():
            cmd += extra_args.strip().split()
        if fmt == 'mp3':
            cmd += ['-codec:a', 'libmp3lame', '-b:a', '192k']
        elif fmt == 'gif':
            cmd += ['-vf', 'fps=15,scale=480:-1:flags=lanczos']
        cmd += [str(out)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except FileNotFoundError:
            raise HTTPException(500, 'ffmpeg not installed')
        if r.returncode != 0 or not out.exists():
            raise HTTPException(500, f'ffmpeg failed: {(r.stderr or "")[-2000:]}')
        blob = out.read_bytes()
    mime = {'mp3': 'audio/mpeg', 'wav': 'audio/wav', 'ogg': 'audio/ogg',
            'm4a': 'audio/mp4', 'flac': 'audio/flac', 'mp4': 'video/mp4',
            'webm': 'video/webm', 'gif': 'image/gif'}[fmt]
    stem = Path(files[0].filename or 'output').stem
    return Response(content=blob, media_type=mime,
                    headers={'Content-Disposition': f'attachment; filename="{stem}.{fmt}"'})
