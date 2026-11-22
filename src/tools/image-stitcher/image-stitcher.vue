<script setup lang="ts">
import { useJobStore } from '@/stores/job.store';
import { checkBackendHealth, startStitchJob } from '@/utils/converterApi';
import { formatBytes } from '@/utils/convert';
import { getBaseName, uid } from '@/utils/media';

interface StitchFile {
  id: string
  file: File
  url: string
}

const jobStore = useJobStore();

const mode = ref<'scroll' | 'panorama'>('scroll');
const order = ref<'name' | 'upload' | 'reverse'>('name');
const format = ref<'jpg' | 'png'>('jpg');

const modeOptions = [
  { label: 'Cuộn dọc (screenshot dài)', value: 'scroll' },
  { label: 'Panorama (ảnh chụp)', value: 'panorama' },
];
const orderOptions = [
  { label: 'Theo tên file', value: 'name' },
  { label: 'Theo thứ tự chọn', value: 'upload' },
  { label: 'Ngược lại', value: 'reverse' },
];
const formatOptions = [
  { label: 'JPG (nhẹ)', value: 'jpg' },
  { label: 'PNG (nét)', value: 'png' },
];

const files = ref<StitchFile[]>([]);
const isWorking = ref(false);
const backendOk = ref<boolean | null>(null);
const log = ref('');

function onFiles(list: File[]) {
  for (const f of list) {
    if (!f.type.startsWith('image/')) {
      continue;
    }
    files.value.push({ id: uid(), file: f, url: URL.createObjectURL(f) });
  }
}
function onSingle(f: File) {
  onFiles([f]);
}
function removeFile(id: string) {
  const idx = files.value.findIndex(x => x.id === id);
  if (idx === -1) {
    return;
  }
  const [rm] = files.value.splice(idx, 1);
  URL.revokeObjectURL(rm.url);
}
function clearAll() {
  for (const f of files.value) {
    URL.revokeObjectURL(f.url);
  }
  files.value = [];
}
function move(idx: number, dir: -1 | 1) {
  const j = idx + dir;
  if (j < 0 || j >= files.value.length) {
    return;
  }
  const arr = [...files.value];
  const [x] = arr.splice(idx, 1);
  arr.splice(j, 0, x);
  files.value = arr;
}

async function sendJob() {
  if (files.value.length < 2) {
    log.value = 'Cần ít nhất 2 ảnh.';
    return;
  }
  isWorking.value = true;
  log.value = '';
  try {
    const ok = await checkBackendHealth();
    backendOk.value = ok;
    if (!ok) {
      log.value = 'Backend đang offline — kiểm tra converter đã chạy chưa.';
      return;
    }
    const job = await startStitchJob({
      files: files.value.map(f => f.file),
      mode: mode.value,
      order: order.value,
      format: format.value,
    });
    jobStore.track(job.id, `Stitch ${files.value.length} ảnh (${getBaseName(files.value[0].file.name)}…)`);
    log.value = `Đã gửi job stitch #${job.id}\n`;
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
    <c-card title="1. Chọn ảnh (2–50 ảnh)">
      <c-file-upload multiple accept="image/*" title="Kéo thả ảnh cần ghép (screenshot cuộn dọc hoặc ảnh panorama)" @files-upload="onFiles" @file-upload="onSingle" />
      <div v-if="files.length" mt-3 flex flex-col gap-2>
        <div v-for="(f, i) in files" :key="f.id" flex items-center justify-between gap-2 border rounded px-3 py-2>
          <div flex items-center gap-2 truncate>
            <img :src="f.url" alt="" h-40px w-40px rounded object-cover>
            <span truncate>{{ i + 1 }}. {{ f.file.name }} • {{ formatBytes(f.file.size) }}</span>
          </div>
          <div flex shrink-0 gap-1>
            <c-button size="small" :disabled="i === 0" @click="move(i, -1)">
              ↑
            </c-button>
            <c-button size="small" :disabled="i === files.length - 1" @click="move(i, 1)">
              ↓
            </c-button>
            <c-button size="small" @click="removeFile(f.id)">
              Xóa
            </c-button>
          </div>
        </div>
        <c-button v-if="files.length" size="small" @click="clearAll">
          Xóa tất cả ({{ files.length }})
        </c-button>
      </div>
    </c-card>

    <c-card title="2. Tùy chọn ghép">
      <div grid grid-cols-1 gap-4 md:grid-cols-3>
        <c-select v-model:value="mode" label="Chế độ" :options="modeOptions" />
        <c-select v-model:value="order" label="Thứ tự ghép" :options="orderOptions" />
        <c-select v-model:value="format" label="Định dạng ra" :options="formatOptions" />
      </div>
      <div mt-4 flex gap-2>
        <c-button type="primary" :disabled="files.length < 2 || isWorking" @click="sendJob">
          {{ isWorking ? 'Đang gửi...' : `Ghép ${files.length} ảnh` }}
        </c-button>
      </div>
      <c-alert mt-3 type="info">
        Job chạy dưới backend (OpenCV): cuộn dọc tìm overlap bằng template-match, panorama dùng Stitcher. Theo dõi tiến độ / hủy ở nút Job trên navbar. Chọn "Theo thứ tự chọn" rồi dùng ↑ ↓ để sắp xếp tay.
      </c-alert>
      <div v-if="backendOk === false" mt-2 text-sm text-red-500>
        Backend đang offline.
      </div>
      <pre v-if="log" mt-3 overflow-auto rounded bg-gray-100 p-2 text-xs dark:bg-gray-800>{{ log }}</pre>
    </c-card>
  </div>
</template>
