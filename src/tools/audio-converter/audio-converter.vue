<script setup lang="ts">
import { readFfmpegFile, useFfmpeg } from '@/composable/useFfmpeg';
import { downloadBlob, formatTime, getBaseName, parseTimeToSeconds, uid } from '@/utils/media';
import { formatBytes } from '@/utils/convert';

type AudioFmt = 'mp3' | 'wav' | 'ogg' | 'm4a' | 'flac';

interface AudioItem {
  id: string
  file: File
  url: string
  duration: number | null
  outUrl: string | null
  outBlob: Blob | null
  outSize: number | null
  status: 'ready' | 'working' | 'done' | 'error'
  error?: string
}

const { ensureLoaded, isLoading, loadError, progress, isSupported } = useFfmpeg();

const targetFormat = ref<AudioFmt>('mp3');
const bitrate = ref('192k');
const trimEnabled = ref(false);
const trimStart = ref('0');
const trimEnd = ref('');
const mergeMode = ref(false);

const items = ref<AudioItem[]>([]);
const isWorking = ref(false);
const log = ref('');

const formatOptions = [
  { label: 'MP3', value: 'mp3' },
  { label: 'WAV', value: 'wav' },
  { label: 'OGG Vorbis', value: 'ogg' },
  { label: 'M4A (AAC)', value: 'm4a' },
  { label: 'FLAC', value: 'flac' },
];
const bitrateOptions = ['96k', '128k', '192k', '256k', '320k'].map(v => ({ label: v, value: v }));

function probeDuration(file: File): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const el = document.createElement('audio');
    el.preload = 'metadata';
    el.onloadedmetadata = () => {
      const d = el.duration;
      URL.revokeObjectURL(url);
      resolve(Number.isFinite(d) ? d : null);
    };
    el.onerror = () => {
      URL.revokeObjectURL(url);
      resolve(null);
    };
    el.src = url;
  });
}

async function onFiles(files: File[]) {
  for (const f of files) {
    const url = URL.createObjectURL(f);
    const duration = await probeDuration(f);
    items.value.push({ id: uid(), file: f, url, duration, outUrl: null, outBlob: null, outSize: null, status: 'ready' });
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

function buildArgs(input: string, output: string, fmt: AudioFmt): string[] {
  const args = ['-y', '-i', input];
  const ss = parseTimeToSeconds(trimStart.value);
  const to = parseTimeToSeconds(trimEnd.value);
  if (trimEnabled.value && (ss !== null || to !== null)) {
    if (ss !== null) {
      args.push('-ss', String(ss));
    }
    if (to !== null && ss !== null && to > ss) {
      args.push('-t', String(to - ss));
    }
    else if (to !== null) {
      args.push('-to', String(to));
    }
  }
  if (fmt === 'mp3') {
    args.push('-codec:a', 'libmp3lame', '-b:a', bitrate.value);
  }
  else if (fmt === 'ogg') {
    args.push('-codec:a', 'libvorbis', '-b:a', bitrate.value);
  }
  else if (fmt === 'm4a') {
    args.push('-codec:a', 'aac', '-b:a', bitrate.value);
  }
  else if (fmt === 'flac') {
    args.push('-codec:a', 'flac');
  }
  else if (fmt === 'wav') {
    args.push('-codec:a', 'pcm_s16le');
  }
  args.push(output);
  return args;
}

async function convertAll() {
  if (!items.value.length) {
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

async function convertOne(ffmpeg: any, it: AudioItem) {
  it.status = 'working';
  try {
    const inName = `in-${it.id}-${it.file.name}`.replace(/[^\w.-]/g, '_');
    const outName = `out-${it.id}.${targetFormat.value}`;
    await ffmpeg.writeFile(inName, await readFfmpegFile(it.file));
    const args = buildArgs(inName, outName, targetFormat.value);
    log.value += `$ ffmpeg ${args.join(' ')}\n`;
    await ffmpeg.exec(args);
    const data = await ffmpeg.readFile(outName) as Uint8Array;
    const mime = targetFormat.value === 'mp3' ? 'audio/mpeg' : targetFormat.value === 'wav' ? 'audio/wav' : targetFormat.value === 'ogg' ? 'audio/ogg' : targetFormat.value === 'm4a' ? 'audio/mp4' : 'audio/flac';
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

async function mergeAll(ffmpeg: any) {
  const listName = 'concat-list.txt';
  let listContent = '';
  for (const [i, it] of items.value.entries()) {
    const inName = `merge-${i}-${it.file.name}`.replace(/[^\w.-]/g, '_');
    await ffmpeg.writeFile(inName, await readFfmpegFile(it.file));
    listContent += `file '${inName}'\n`;
    it.status = 'working';
  }
  await ffmpeg.writeFile(listName, new TextEncoder().encode(listContent));
  const outName = `merged.${targetFormat.value}`;
  const baseArgs = ['-y', '-f', 'concat', '-safe', '0', '-i', listName];
  if (targetFormat.value === 'mp3') {
    baseArgs.push('-codec:a', 'libmp3lame', '-b:a', bitrate.value);
  }
  else { baseArgs.push('-c', 'copy'); }
  baseArgs.push(outName);
  log.value += `$ ffmpeg ${baseArgs.join(' ')}\n`;
  await ffmpeg.exec(baseArgs);
  const data = await ffmpeg.readFile(outName) as Uint8Array;
  const blob = new Blob([data.buffer as ArrayBuffer], { type: 'audio/mpeg' });
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
}

function downloadOne(it: AudioItem) {
  if (!it.outBlob) {
    return;
  }
  const name = mergeMode.value ? `merged.${targetFormat.value}` : `${getBaseName(it.file.name)}.${targetFormat.value}`;
  downloadBlob(it.outBlob, name);
}
</script>

<template>
  <div flex flex-col gap-4>
    <c-alert v-if="!isSupported" type="warning">
      Trình duyệt thiếu WebAssembly/Worker nên không chạy được ffmpeg.wasm. Hãy dùng Chrome/Edge/Firefox mới.
    </c-alert>

    <c-card title="1. Chọn file audio">
      <c-file-upload multiple accept="audio/*,video/*,.mkv,.flac,.m4a,.ogg,.wav,.mp3" title="Kéo thả audio (mp3/wav/ogg/m4a/flac, hoặc video để tách tiếng)" @files-upload="onFiles" @file-upload="onSingle" />
      <div mt-2 flex gap-2>
        <c-button v-if="items.length" size="small" @click="clearAll">
          Xóa tất cả
        </c-button>
      </div>
    </c-card>

    <c-card title="2. Tùy chọn">
      <div grid grid-cols-1 gap-4 md:grid-cols-3>
        <c-select v-model:value="targetFormat" label="Định dạng" :options="formatOptions" />
        <c-select v-model:value="bitrate" label="Bitrate" :options="bitrateOptions" />
        <div flex items-end pb-1>
          <n-checkbox v-model:checked="trimEnabled">
            Cắt (trim) theo thời gian
          </n-checkbox>
        </div>
      </div>
      <div v-if="trimEnabled" grid grid-cols-1 mt-3 gap-4 md:grid-cols-2>
        <c-input-text v-model:value="trimStart" label="Bắt đầu (giây hoặc mm:ss, vd 0:30)" placeholder="0" />
        <c-input-text v-model:value="trimEnd" label="Kết thúc (để trống = hết file)" placeholder="1:00" />
      </div>
      <div mt-3>
        <n-checkbox v-model:checked="mergeMode">
          Nối (merge) tất cả thành 1 file theo thứ tự danh sách
        </n-checkbox>
      </div>
      <div mt-4 flex flex-wrap gap-2>
        <c-button type="primary" :disabled="!items.length || isWorking || isLoading" @click="convertAll">
          {{ isLoading ? 'Đang tải ffmpeg (~30MB lần đầu)...' : isWorking ? `Đang xử lý ${(progress * 100).toFixed(0)}%...` : `Convert ${items.length} file → ${targetFormat.toUpperCase()}` }}
        </c-button>
      </div>
      <div v-if="loadError" mt-2 text-sm text-red-500>
        Lỗi tải ffmpeg: {{ loadError }} — thử reload hoặc kiểm tra mạng/CDN jsdelivr.
      </div>
      <c-alert mt-3 type="info">
        Chạy 100% local bằng ffmpeg.wasm. Lần đầu tải core ~30MB từ CDN, các lần sau cache lại. File lớn &gt; 500MB nên dùng backend.
      </c-alert>
    </c-card>

    <c-card v-if="items.length" title="3. Danh sách & kết quả">
      <div flex flex-col gap-3>
        <div v-for="it in items" :key="it.id" border rounded p-3>
          <div flex items-center justify-between gap-2>
            <div truncate font-medium>
              {{ it.file.name }} • {{ formatBytes(it.file.size) }} <span v-if="it.duration">• {{ formatTime(it.duration) }}</span>
            </div>
            <div text-sm>
              {{ it.status }}
            </div>
          </div>
          <audio :src="it.url" controls mt-2 w-full />
          <div v-if="it.outUrl" mt-2>
            <div mb-1 text-sm>
              Kết quả: {{ formatBytes(it.outSize ?? 0) }}
            </div>
            <audio :src="it.outUrl" controls w-full />
            <div mt-2 flex gap-2>
              <c-button size="small" type="primary" @click="downloadOne(it)">
                Tải xuống
              </c-button>
            </div>
          </div>
          <div v-if="it.error" mt-1 text-sm text-red-500>
            {{ it.error }}
          </div>
        </div>
      </div>
      <pre v-if="log" mt-3 overflow-auto rounded bg-gray-100 p-2 text-xs dark:bg-gray-800>{{ log }}</pre>
    </c-card>
  </div>
</template>
