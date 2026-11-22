<script setup lang="ts">
import { useJobStore } from '@/stores/job.store';
import { formatBytes } from '@/utils/convert';
import { checkBackendHealth, startMediaJob } from '@/utils/converterApi';
import { uid } from '@/utils/media';

type VideoFmt = 'mp4' | 'webm' | 'mp3' | 'gif';

interface VItem {
  id: string
  file: File
  url: string
  sentKey: string | null
}

const jobStore = useJobStore();
const backendOk = ref<boolean | null>(null);

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
    items.value.push({ id: uid(), file: f, url, sentKey: null });
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

function currentKey() {
  return `${targetFormat.value}|${resolution.value}|${crf.value}|${fps.value}x${gifWidth.value}|${trimEnabled.value ? `${trimStart.value}>${trimDuration.value}` : ''}`;
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
        crf: crf.value,
        resolution: resolution.value,
        fps: fps.value,
        gifWidth: gifWidth.value,
        merge: true,
      });
      for (const it of items.value) {
        it.sentKey = currentKey();
      }
      jobStore.track(job.id, `Gộp ${items.value.length} video → ${targetFormat.value.toUpperCase()}`);
      log.value = `Đã gửi job gộp #${job.id}\n`;
    }
    else {
      const key = currentKey();
      const pending = items.value.filter(it => it.sentKey !== key);
      if (!pending.length) {
        log.value = 'Tất cả file đã được gửi job với tùy chọn hiện tại rồi (xem Job Center). Đổi tùy chọn, xóa bớt hoặc thêm file mới để gửi tiếp.';
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
          fps: fps.value,
          gifWidth: gifWidth.value,
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
    <c-card title="1. Chọn video">
      <c-file-upload multiple accept="video/*,audio/*,.mkv,.mov,.avi,.mp4,.webm" title="Kéo thả video (mp4/webm/mkv/mov/avi...)" @files-upload="onFiles" @file-upload="onSingle" />
      <div mt-2>
        <c-button v-if="items.length" size="small" @click="clearAll">
          Xóa tất cả
        </c-button>
      </div>
    </c-card>

    <c-card title="2. Tùy chọn (chạy dưới backend)">
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
      <div v-if="backendOk === false" mt-2>
        <c-alert type="warning">
          Backend đang offline — kiểm tra converter đã chạy chưa.
        </c-alert>
      </div>
      <div mt-4 flex gap-2>
        <c-button type="primary" :disabled="!items.length || isWorking" @click="sendJobs">
          {{ isWorking ? 'Đang gửi job...' : mergeMode && items.length > 1 ? `Gửi job gộp ${items.length} video → ${targetFormat.toUpperCase()}` : `Gửi job → ${targetFormat.toUpperCase()}` }}
        </c-button>
      </div>
      <c-alert mt-3 type="info">
        Job chạy dưới backend (ffmpeg server), có thanh tiến độ / tạm dừng / hủy ở nút Job trên navbar. GIF chỉ nên cắt đoạn ngắn &lt; 10s.
      </c-alert>
    </c-card>

    <c-card v-if="items.length" title="3. Danh sách">
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
        </div>
      </div>
      <pre v-if="log" mt-3 overflow-auto rounded bg-gray-100 p-2 text-xs dark:bg-gray-800>{{ log }}</pre>
    </c-card>
  </div>
</template>
