<script setup lang="ts">
import { useJobStore } from '@/stores/job.store';
import { formatBytes } from '@/utils/convert';
import { checkBackendHealth, startMediaJob } from '@/utils/converterApi';
import { formatTime, parseTimeToSeconds, uid } from '@/utils/media';

type AudioFmt = 'mp3' | 'wav' | 'ogg' | 'm4a' | 'flac';

interface AudioItem {
  id: string
  file: File
  url: string
  duration: number | null
  sentKey: string | null
}

const jobStore = useJobStore();
const backendOk = ref<boolean | null>(null);

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
    items.value.push({ id: uid(), file: f, url, duration, sentKey: null });
  }
}
function onSingle(f: File) {
  onFiles([f]);
}
function clearAll() {
  for (const it of items.value) {
    URL.revokeObjectURL(it.url);
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
}

function currentKey() {
  return `${targetFormat.value}|${bitrate.value}|${trimEnabled.value ? `${trimStart.value}>${trimEnd.value}` : ''}`;
}

async function sendJobs() {
  if (!items.value.length) {
    return;
  }
  isWorking.value = true;
  log.value = '';
  try {
    if (backendOk.value === null) {
      backendOk.value = await checkBackendHealth();
    }
    if (!backendOk.value) {
      log.value = 'Backend đang offline — kiểm tra converter đã chạy chưa.';
      return;
    }
    if (mergeMode.value && items.value.length > 1) {
      const job = await startMediaJob({
        files: items.value.map(i => i.file),
        format: targetFormat.value,
        bitrate: bitrate.value,
        trimStart: trimEnabled.value ? trimStart.value : '',
        trimDuration: trimEnabled.value && trimEnd.value ? trimEnd.value : '',
        merge: true,
      });
      const key = currentKey();
      for (const it of items.value) {
        it.sentKey = key;
      }
      jobStore.track(job.id, `Nối ${items.value.length} audio → ${targetFormat.value.toUpperCase()}`);
      log.value = `Đã gửi job nối #${job.id}\n`;
    }
    else {
      const key = currentKey();
      const pending = items.value.filter(it => it.sentKey !== key);
      if (!pending.length) {
        log.value = 'Tất cả file đã được gửi job với tùy chọn hiện tại rồi (xem Job Center). Đổi tùy chọn, xóa bớt hoặc thêm file mới để gửi tiếp.';
        return;
      }
      for (const it of pending) {
        // backend nhận duration: end - start
        let dur = '';
        if (trimEnabled.value && trimEnd.value.trim() !== '') {
          const ss = parseTimeToSeconds(trimStart.value);
          const to = parseTimeToSeconds(trimEnd.value);
          if (ss !== null && to !== null && to > ss) {
            dur = String(to - ss);
          }
          else if (to !== null) {
            dur = String(to);
          }
        }
        const job = await startMediaJob({
          files: [it.file],
          format: targetFormat.value,
          bitrate: bitrate.value,
          trimStart: trimEnabled.value ? trimStart.value : '',
          trimDuration: dur,
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
</script>

<template>
  <div flex flex-col gap-4>
    <c-card title="1. Chọn file audio">
      <c-file-upload multiple accept="audio/*,video/*,.mkv,.flac,.m4a,.ogg,.wav,.mp3" title="Kéo thả audio (mp3/wav/ogg/m4a/flac, hoặc video để tách tiếng)" @files-upload="onFiles" @file-upload="onSingle" />
      <div mt-2 flex gap-2>
        <c-button v-if="items.length" size="small" @click="clearAll">
          Xóa tất cả
        </c-button>
      </div>
    </c-card>

    <c-card title="2. Tùy chọn (chạy dưới backend)">
      <div grid grid-cols-1 gap-4 md:grid-cols-3>
        <c-select v-model:value="targetFormat" label="Định dạng" :options="formatOptions" />
        <c-select v-model:value="bitrate" label="Bitrate" :options="bitrateOptions" />
        <div flex items-end pb-1>
          <n-checkbox v-model:checked="trimEnabled" :disabled="mergeMode">
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
      <div v-if="backendOk === false" mt-2>
        <c-alert type="warning">
          Backend đang offline — kiểm tra converter đã chạy chưa.
        </c-alert>
      </div>
      <div mt-4 flex flex-wrap gap-2>
        <c-button type="primary" :disabled="!items.length || isWorking" @click="sendJobs">
          {{ isWorking ? 'Đang gửi job...' : mergeMode && items.length > 1 ? `Gửi job nối ${items.length} file → ${targetFormat.toUpperCase()}` : `Gửi job ${items.length} file → ${targetFormat.toUpperCase()}` }}
        </c-button>
      </div>
      <c-alert mt-3 type="info">
        Job chạy dưới backend (ffmpeg server), có thanh tiến độ / tạm dừng / hủy ở nút Job trên navbar.
      </c-alert>
    </c-card>

    <c-card v-if="items.length" title="3. Danh sách">
      <div flex flex-col gap-3>
        <div v-for="(it, i) in items" :key="it.id" border rounded p-3>
          <div flex items-center justify-between gap-2>
            <div truncate font-medium>
              {{ i + 1 }}. {{ it.file.name }} • {{ formatBytes(it.file.size) }} <span v-if="it.duration">• {{ formatTime(it.duration) }}</span>
              <n-tag v-if="it.sentKey" size="small" type="success" ml-1>
                đã gửi job
              </n-tag>
            </div>
            <c-button size="small" @click="removeItem(it.id)">
              Xóa
            </c-button>
          </div>
          <audio :src="it.url" controls mt-2 w-full />
        </div>
      </div>
      <pre v-if="log" mt-3 overflow-auto rounded bg-gray-100 p-2 text-xs dark:bg-gray-800>{{ log }}</pre>
    </c-card>
  </div>
</template>
