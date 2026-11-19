<script setup lang="ts">
import { readFfmpegFile, useFfmpeg } from '@/composable/useFfmpeg';
import { useJobStore } from '@/stores/job.store';
import { downloadBlob, getBaseName, parseTimeToSeconds, uid } from '@/utils/media';
import { formatBytes } from '@/utils/convert';
import { checkBackendHealth, startMediaJob } from '@/utils/converterApi';

type VideoFmt = 'mp4' | 'webm' | 'mp3' | 'gif';
type Engine = 'local' | 'backend';

interface VItem {
  id: string
  file: File
  url: string
  outUrl: string | null
  outBlob: Blob | null
  outSize: number | null
  status: 'ready' | 'working' | 'done' | 'error'
  error?: string
  sentKey: string | null
}

const { ensureLoaded, isLoading, loadError, progress, isSupported } = useFfmpeg();
const jobStore = useJobStore();

const engine = ref<Engine>('local');
const backendOk = ref<boolean | null>(null);
const engineOptions = [
  { label: 'Trình duyệt (nhanh, file nhỏ)', value: 'local' },
  { label: 'Backend job (file lớn, có tiến độ)', value: 'backend' },
];

const targetFormat = ref<VideoFmt>('mp4');
const resolution = ref('original');
const crf = ref(23);
const trimEnabled = ref(false);
const trimStart = ref('0');
const trimDuration = ref('');
const fps = ref(15);
const gifWidth = ref(480);
const mergeMode = ref(false);

const items = ref<VItem[]>([]);
const isWorking = ref(false);
const log = ref('');

const formatOptions = [
  { label: 'MP4 (H.264)', value: 'mp4' },
  { label: 'WEBM (VP9)', value: 'webm' },
  { label: 'MP3 (tách tiếng)', value: 'mp3' },
  { label: 'GIF (ảnh động)', value: 'gif' },
];
const resOptions = [
  { label: 'Giữ nguyên', value: 'original' },
  { label: '1080p', value: '1080' },
  { label: '720p', value: '720' },
  { label: '480p', value: '480' },
];

function onFiles(files: File[]) {
  for (const f of files) {
    const url = URL.createObjectURL(f);
    items.value.push({ id: uid(), file: f, url, outUrl: null, outBlob: null, outSize: null, status: 'ready', sentKey: null });
  }
}
function onSingle(f: File) {
  onFiles([f]);
}
function clearAll() {
  for (const it of items.value) {
    URL.revokeObjectURL(it.url);
    if (it.outUrl) {
      URL.revokeObjectURL(it.outUrl);
    }
  }
  items.value = [];
}

function removeItem(id: string) {
  const idx = items.value.findIndex(i => i.id === id);
  if (idx === -1) {
    return;
  }
  const [rm] = items.value.splice(idx, 1);
  URL.revokeObjectURL(rm.url);
  if (rm.outUrl) {
    URL.revokeObjectURL(rm.outUrl);
  }
}

function move(idx: number, dir: -1 | 1) {
  const j = idx + dir;
  if (j < 0 || j >= items.value.length) {
    return;
  }
  const arr = [...items.value];
  const [x] = arr.splice(idx, 1);
  arr.splice(j, 0, x);
  items.value = arr;
}

function scaleFilter(): string[] {
  if (resolution.value === 'original') {
    return [];
  }
  const h = Number(resolution.value);
  return ['-vf', `scale=-2:${h}`];
}

function encodeArgs(fmt: VideoFmt): string[] {
  if (fmt === 'mp4') {
    return ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', String(crf.value), '-c:a', 'aac', '-b:a', '128k', ...scaleFilter()];
  }
  if (fmt === 'webm') {
    return ['-c:v', 'libvpx-vp9', '-b:v', '1M', '-c:a', 'libopus', ...scaleFilter()];
  }
  if (fmt === 'mp3') {
    return ['-vn', '-c:a', 'libmp3lame', '-b:a', '192k'];
  }
  return ['-vf', `fps=${fps.value},scale=${gifWidth.value}:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse`];
}

function buildArgs(inName: string, outName: string, fmt: VideoFmt): string[] {
  const args = ['-y'];
  const ss = parseTimeToSeconds(trimStart.value);
  const dur = parseTimeToSeconds(trimDuration.value);
  if (trimEnabled.value && ss !== null) {
    args.push('-ss', String(ss));
  }
  args.push('-i', inName);
  if (trimEnabled.value && dur !== null) {
    args.push('-t', String(dur));
  }

  args.push(...encodeArgs(fmt));
  args.push(outName);
  return args;
}

async function convertAll() {
  if (!items.value.length) {
    return;
  }
  if (engine.value === 'backend') {
    await sendBackendJobs();
    return;
  }
  isWorking.value = true;
  log.value = '';
  try {
    const ffmpeg = await ensureLoaded();
    if (mergeMode.value && items.value.length > 1) {
      await mergeAll(ffmpeg);
    }
    else {
      for (const it of items.value) {
        await convertOne(ffmpeg, it);
      }
    }
  }
  catch (e: any) {
    log.value = e?.message ?? String(e);
  }
  finally {
    isWorking.value = false;
  }
}

async function sendBackendJobs() {
  isWorking.value = true;
  log.value = '';
  try {
    if (mergeMode.value && items.value.length > 1) {
      const job = await startMediaJob({
        files: items.value.map(i => i.file),
        format: targetFormat.value,
        crf: crf.value,
        resolution: resolution.value,
        merge: true,
      });
      jobStore.track(job.id, `Gộp ${items.value.length} video → ${targetFormat.value.toUpperCase()}`);
      log.value = `Đã gửi job gộp #${job.id}\n`;
    }
    else {
      const key = `${targetFormat.value}|${trimEnabled.value ? `${trimStart.value}>${trimDuration.value}` : ''}`;
      const pending = items.value.filter(it => it.sentKey !== key);
      if (!pending.length) {
        log.value = 'Tất cả file đã được gửi job với tùy chọn hiện tại rồi (xem Job Center). Đổi định dạng, xóa bớt hoặc thêm file mới để gửi tiếp.';
        return;
      }
      for (const it of pending) {
        const job = await startMediaJob({
          files: [it.file],
          format: targetFormat.value,
          crf: crf.value,
          resolution: resolution.value,
          trimStart: trimEnabled.value ? trimStart.value : '',
          trimDuration: trimEnabled.value ? trimDuration.value : '',
        });
        it.sentKey = key;
        jobStore.track(job.id, `${it.file.name} → ${targetFormat.value.toUpperCase()}`);
        log.value += `Đã gửi job #${job.id} cho ${it.file.name}\n`;
      }
    }
    jobStore.openDrawer();
  }
  catch (e: any) {
    log.value = e?.message ?? String(e);
  }
  finally {
    isWorking.value = false;
  }
}

watch(engine, async (v) => {
  if (v === 'backend' && backendOk.value === null) {
    backendOk.value = await checkBackendHealth();
  }
});

async function mergeAll(ffmpeg: any) {
  const fmt = targetFormat.value;
  const listName = 'concat-list.txt';
  let listContent = '';
  for (const [i, it] of items.value.entries()) {
    const inName = `merge-${i}-${it.file.name}`.replace(/[^\w.-]/g, '_');
    await ffmpeg.writeFile(inName, await readFfmpegFile(it.file));
    listContent += `file '${inName}'\n`;
    it.status = 'working';
  }
  await ffmpeg.writeFile(listName, new TextEncoder().encode(listContent));
  const outName = `merged.${fmt}`;
  const args = ['-y', '-f', 'concat', '-safe', '0', '-i', listName, ...encodeArgs(fmt), outName];
  log.value += `$ ffmpeg ${args.join(' ')}\n`;
  await ffmpeg.exec(args);
  const data = await ffmpeg.readFile(outName) as Uint8Array;
  const mime = fmt === 'mp4' ? 'video/mp4' : fmt === 'webm' ? 'video/webm' : fmt === 'mp3' ? 'audio/mpeg' : 'image/gif';
  const blob = new Blob([data.buffer as ArrayBuffer], { type: mime });
  const first = items.value[0];
  if (first.outUrl) {
    URL.revokeObjectURL(first.outUrl);
  }
  first.outUrl = URL.createObjectURL(blob);
  first.outBlob = blob;
  first.outSize = blob.size;
  first.status = 'done';
  for (const it of items.value.slice(1)) {
    it.status = 'done';
    it.outUrl = first.outUrl;
    it.outBlob = blob;
    it.outSize = blob.size;
  }
  await ffmpeg.deleteFile(listName).catch(() => {});
  await ffmpeg.deleteFile(outName).catch(() => {});
}

async function convertOne(ffmpeg: any, it: VItem) {
  it.status = 'working';
  try {
    const inName = `in-${it.id}-${it.file.name}`.replace(/[^\w.-]/g, '_');
    const outName = `out-${it.id}.${targetFormat.value}`;
    await ffmpeg.writeFile(inName, await readFfmpegFile(it.file));
    const args = buildArgs(inName, outName, targetFormat.value);
    log.value += `$ ffmpeg ${args.join(' ')}\n`;
    await ffmpeg.exec(args);
    const data = await ffmpeg.readFile(outName) as Uint8Array;
    const mime = targetFormat.value === 'mp4' ? 'video/mp4' : targetFormat.value === 'webm' ? 'video/webm' : targetFormat.value === 'mp3' ? 'audio/mpeg' : 'image/gif';
    const blob = new Blob([data.buffer as ArrayBuffer], { type: mime });
    if (it.outUrl) {
      URL.revokeObjectURL(it.outUrl);
    }
    it.outUrl = URL.createObjectURL(blob);
    it.outBlob = blob;
    it.outSize = blob.size;
    it.status = 'done';
    await ffmpeg.deleteFile(inName).catch(() => {});
    await ffmpeg.deleteFile(outName).catch(() => {});
  }
  catch (e: any) {
    it.status = 'error';
    it.error = e?.message ?? String(e);
  }
}

function downloadOne(it: VItem) {
  if (!it.outBlob) {
    return;
  }
  const name = mergeMode.value && items.value.length > 1 ? `merged.${targetFormat.value}` : `${getBaseName(it.file.name)}.${targetFormat.value}`;
  downloadBlob(it.outBlob, name);
}
</script>

<template>
  <div flex flex-col gap-4>
    <c-alert v-if="!isSupported" type="warning">
      Trình duyệt thiếu WebAssembly nên không chạy được video converter.
    </c-alert>

    <c-card title="1. Chọn video">
      <c-file-upload multiple accept="video/*,audio/*,.mkv,.mov,.avi,.mp4,.webm" title="Kéo thả video (mp4/webm/mkv/mov/avi...)" @files-upload="onFiles" @file-upload="onSingle" />
      <div mt-2>
        <c-button v-if="items.length" size="small" @click="clearAll">
          Xóa tất cả
        </c-button>
      </div>
    </c-card>

    <c-card title="2. Tùy chọn">
      <c-buttons-select v-model:value="engine" :options="engineOptions" label="Nơi xử lý" />
      <div v-if="engine === 'backend'" mt-2 text-sm op-70>
        Job chạy dưới backend — theo dõi tiến độ / tạm dừng / hủy ở nút Job trên thanh navbar.
      </div>
      <div grid grid-cols-1 mt-3 gap-4 md:grid-cols-2>
        <c-select v-model:value="targetFormat" label="Định dạng đầu ra" :options="formatOptions" />
        <c-select v-if="targetFormat === 'mp4' || targetFormat === 'webm'" v-model:value="resolution" label="Độ phân giải" :options="resOptions" />
      </div>
      <div v-if="targetFormat === 'gif'" grid grid-cols-1 mt-3 gap-4 md:grid-cols-2>
        <div>
          <label mb-1 block text-sm>FPS: {{ fps }}</label>
          <n-slider v-model:value="fps" :min="5" :max="30" :step="1" />
        </div>
        <div>
          <label mb-1 block text-sm>Chiều rộng GIF: {{ gifWidth }}px</label>
          <n-slider v-model:value="gifWidth" :min="240" :max="800" :step="10" />
        </div>
      </div>
      <div v-if="targetFormat === 'mp4'" mt-3>
        <label mb-1 block text-sm>CRF (chất lượng H.264): {{ crf }} <span op-60>— càng nhỏ càng nét/nặng (18–28 khuyên dùng)</span></label>
        <n-slider v-model:value="crf" :min="18" :max="28" :step="1" />
      </div>
      <div mt-3>
        <n-checkbox v-model:checked="trimEnabled" :disabled="mergeMode">
          Cắt đoạn (seek + duration)
        </n-checkbox>
      </div>
      <div v-if="trimEnabled" grid grid-cols-1 mt-3 gap-4 md:grid-cols-2>
        <c-input-text v-model:value="trimStart" label="Bắt đầu (giây hoặc mm:ss)" placeholder="0:10" />
        <c-input-text v-model:value="trimDuration" label="Độ dài đoạn (giây, vd 15)" placeholder="15" />
      </div>
      <div mt-3>
        <n-checkbox v-model:checked="mergeMode">
          Gộp (merge) tất cả thành 1 video theo thứ tự danh sách
        </n-checkbox>
        <div v-if="mergeMode" mt-1 text-xs op-60>
          Dùng nút ↑ ↓ ở danh sách bên dưới để sắp xếp thứ tự. Chế độ gộp sẽ encode lại toàn bộ và bỏ qua Cắt đoạn.
        </div>
      </div>
      <div v-if="engine === 'backend' && backendOk === false" mt-2>
        <c-alert type="warning">
          Backend đang offline — kiểm tra converter đã chạy chưa.
        </c-alert>
      </div>
      <div mt-4 flex gap-2>
        <c-button type="primary" :disabled="!items.length || isWorking || (engine === 'local' && isLoading)" @click="convertAll">
          {{ engine === 'backend'
            ? (isWorking ? 'Đang gửi job...' : mergeMode && items.length > 1 ? `Gửi job gộp ${items.length} video → ${targetFormat.toUpperCase()}` : `Gửi job → ${targetFormat.toUpperCase()}`)
            : (isLoading ? 'Đang tải ffmpeg...' : isWorking ? `Đang xử lý ${(progress * 100).toFixed(0)}%...` : mergeMode && items.length > 1 ? `Gộp ${items.length} video → ${targetFormat.toUpperCase()}` : `Convert → ${targetFormat.toUpperCase()}`) }}
        </c-button>
      </div>
      <div v-if="loadError" mt-2 text-sm text-red-500>
        {{ loadError }}
      </div>
      <c-alert mt-3 type="info">
        Chế độ trình duyệt xử lý local, phù hợp file &lt; 300MB. File 4K/dài → chọn Backend job để chạy dưới server, có thanh tiến độ / tạm dừng / hủy ở nút job trên navbar. GIF chỉ nên cắt đoạn ngắn &lt; 10s.
      </c-alert>
    </c-card>

    <c-card v-if="items.length" title="3. Kết quả">
      <div flex flex-col gap-3>
        <div v-for="(it, i) in items" :key="it.id" border rounded p-3>
          <div flex items-center justify-between gap-2>
            <div truncate font-medium>
              {{ i + 1 }}. {{ it.file.name }} • {{ formatBytes(it.file.size) }}
              <n-tag v-if="it.sentKey" size="small" type="success" ml-1>
                đã gửi job
              </n-tag>
            </div>
            <div flex shrink-0 gap-1>
              <template v-if="items.length > 1">
                <c-button size="small" :disabled="i === 0" @click="move(i, -1)">
                  ↑
                </c-button>
                <c-button size="small" :disabled="i === items.length - 1" @click="move(i, 1)">
                  ↓
                </c-button>
              </template>
              <c-button size="small" @click="removeItem(it.id)">
                Xóa
              </c-button>
            </div>
          </div>
          <video :src="it.url" controls mt-2 max-h-240px w-full rounded bg-black />
          <div v-if="it.outUrl" mt-2>
            <div text-sm>
              Output: {{ formatBytes(it.outSize ?? 0) }}
            </div>
            <video v-if="targetFormat !== 'mp3' && targetFormat !== 'gif'" :src="it.outUrl" controls mt-1 max-h-240px w-full rounded bg-black />
            <img v-else-if="targetFormat === 'gif'" :src="it.outUrl" mt-1 max-h-240px rounded>
            <audio v-else :src="it.outUrl" controls mt-1 w-full />
            <c-button size="small" type="primary" mt-2 @click="downloadOne(it)">
              Tải xuống
            </c-button>
          </div>
          <div v-if="it.error" text-sm text-red-500>
            {{ it.error }}
          </div>
        </div>
      </div>
      <pre v-if="log" mt-3 overflow-auto rounded bg-gray-100 p-2 text-xs dark:bg-gray-800>{{ log }}</pre>
    </c-card>
  </div>
</template>
