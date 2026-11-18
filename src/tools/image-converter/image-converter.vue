<script setup lang="ts">
import { downloadBlob, getBaseName, uid } from '@/utils/media';
import { formatBytes } from '@/utils/convert';

type OutFormat = 'png' | 'jpeg' | 'webp';

interface Item {
  id: string
  file: File
  src: string
  width: number
  height: number
  outUrl: string | null
  outSize: number | null
  outBlob: Blob | null
  status: 'ready' | 'converting' | 'done' | 'error'
  error?: string
}

const targetFormat = ref<OutFormat>('webp');
const quality = ref(0.85);
const maxSize = ref(1920);
const rotation = ref<0 | 90 | 180 | 270>(0);
const background = ref('#ffffff');

const items = ref<Item[]>([]);
const isConverting = ref(false);

const formatOptions = [
  { label: 'WEBP (khuyên dùng)', value: 'webp' },
  { label: 'JPEG', value: 'jpeg' },
  { label: 'PNG', value: 'png' },
];

const rotationOptions = [
  { label: '0°', value: 0 },
  { label: '90°', value: 90 },
  { label: '180°', value: 180 },
  { label: '270°', value: 270 },
];

function onFiles(files: File[]) {
  for (const file of files) {
    if (!file.type.startsWith('image/')) {
      continue;
    }
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      items.value.push({
        id: uid(),
        file,
        src: url,
        width: img.naturalWidth,
        height: img.naturalHeight,
        outUrl: null,
        outSize: null,
        outBlob: null,
        status: 'ready',
      });
    };
    img.src = url;
  }
}
function onSingle(file: File) {
  onFiles([file]);
}

function clearAll() {
  for (const it of items.value) {
    URL.revokeObjectURL(it.src);
    if (it.outUrl) {
      URL.revokeObjectURL(it.outUrl);
    }
  }
  items.value = [];
}

function removeItem(id: string) {
  const idx = items.value.findIndex(i => i.id === id);
  if (idx !== -1) {
    const [rm] = items.value.splice(idx, 1);
    URL.revokeObjectURL(rm.src);
    if (rm.outUrl) {
      URL.revokeObjectURL(rm.outUrl);
    }
  }
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
}

async function convertOne(item: Item): Promise<void> {
  item.status = 'converting';
  try {
    const img = await loadImage(item.src);
    let { width, height } = { width: img.naturalWidth, height: img.naturalHeight };

    const max = maxSize.value;
    if (max > 0 && Math.max(width, height) > max) {
      const ratio = max / Math.max(width, height);
      width = Math.round(width * ratio);
      height = Math.round(height * ratio);
    }

    const rot = rotation.value;
    const swap = rot === 90 || rot === 270;
    const canvas = document.createElement('canvas');
    canvas.width = swap ? height : width;
    canvas.height = swap ? width : height;
    const ctx = canvas.getContext('2d')!;

    if (targetFormat.value === 'jpeg') {
      ctx.fillStyle = background.value;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    }

    ctx.save();
    ctx.translate(canvas.width / 2, canvas.height / 2);
    ctx.rotate((rot * Math.PI) / 180);
    ctx.drawImage(img, -width / 2, -height / 2, width, height);
    ctx.restore();

    const mime = targetFormat.value === 'png' ? 'image/png' : targetFormat.value === 'jpeg' ? 'image/jpeg' : 'image/webp';
    const blob: Blob | null = await new Promise(resolve =>
      canvas.toBlob(b => resolve(b), mime, targetFormat.value === 'png' ? undefined : quality.value),
    );
    if (!blob) {
      throw new Error('Canvas export failed');
    }

    if (item.outUrl) {
      URL.revokeObjectURL(item.outUrl);
    }
    item.outUrl = URL.createObjectURL(blob);
    item.outBlob = blob;
    item.outSize = blob.size;
    item.status = 'done';
  }
  catch (e: any) {
    item.status = 'error';
    item.error = e?.message ?? String(e);
  }
}

async function convertAll() {
  if (!items.value.length) {
    return;
  }
  isConverting.value = true;
  for (const it of items.value) {
    await convertOne(it);
  }
  isConverting.value = false;
}

function downloadOne(item: Item) {
  if (!item.outBlob) {
    return;
  }
  const ext = targetFormat.value === 'jpeg' ? 'jpg' : targetFormat.value;
  downloadBlob(item.outBlob, `${getBaseName(item.file.name)}.${ext}`);
}

function downloadAll() {
  for (const it of items.value) {
    if (it.outBlob) {
      downloadOne(it);
    }
  }
}

const totalSaved = computed(() => {
  const orig = items.value.reduce((s, i) => s + i.file.size, 0);
  const out = items.value.reduce((s, i) => s + (i.outSize ?? 0), 0);
  return { orig, out, ratio: orig ? Math.round((1 - out / orig) * 100) : 0 };
});
</script>

<template>
  <div flex flex-col gap-4>
    <c-card title="1. Chọn ảnh">
      <c-file-upload multiple accept="image/*" title="Kéo thả ảnh vào đây (PNG/JPG/WEBP/GIF/BMP...)" @files-upload="onFiles" @file-upload="onSingle" />
      <div mt-2 flex flex-wrap gap-2>
        <c-button v-if="items.length" size="small" @click="clearAll">
          Xóa tất cả ({{ items.length }})
        </c-button>
        <span v-if="items.length" text-sm op-70>
          {{ formatBytes(totalSaved.orig) }} → {{ totalSaved.out ? formatBytes(totalSaved.out) : '...' }}
          <span v-if="totalSaved.out"> ({{ totalSaved.ratio > 0 ? `giảm ${totalSaved.ratio}%` : 'tăng size' }})</span>
        </span>
      </div>
    </c-card>

    <c-card title="2. Tùy chọn convert">
      <div grid grid-cols-1 gap-4 md:grid-cols-2>
        <c-select v-model:value="targetFormat" label="Định dạng đầu ra" :options="formatOptions" />
        <c-select v-model:value="rotation" label="Xoay" :options="rotationOptions" />
      </div>
      <div grid grid-cols-1 mt-4 gap-4 md:grid-cols-2>
        <div>
          <label mb-1 block text-sm>Chất lượng (JPEG/WEBP): {{ Math.round(quality * 100) }}%</label>
          <n-slider v-model:value="quality" :min="0.1" :max="1" :step="0.01" />
        </div>
        <div>
          <label mb-1 block text-sm>Cạnh dài tối đa (px, 0 = giữ gốc): {{ maxSize }}</label>
          <n-slider v-model:value="maxSize" :min="0" :max="4096" :step="16" />
        </div>
      </div>
      <div mt-4 flex flex-wrap gap-3>
        <c-button type="primary" :disabled="!items.length || isConverting" @click="convertAll">
          {{ isConverting ? 'Đang convert...' : `Convert ${items.length} ảnh → ${targetFormat.toUpperCase()}` }}
        </c-button>
        <c-button :disabled="!items.some(i => i.status === 'done')" @click="downloadAll">
          Tải tất cả
        </c-button>
      </div>
      <c-alert mt-3 type="info">
        Xử lý 100% trên trình duyệt (Canvas API), không upload server. Ảnh không bị giảm chất lượng ngoài ý muốn — chỉnh quality/resize tùy nhu cầu web, in ấn.
      </c-alert>
    </c-card>

    <c-card v-if="items.length" title="3. Kết quả">
      <div grid grid-cols-1 gap-3 md:grid-cols-2>
        <div v-for="it in items" :key="it.id" flex flex-col gap-2 border rounded p-3>
          <div flex items-center justify-between gap-2>
            <div truncate font-medium>
              {{ it.file.name }}
            </div>
            <c-button size="small" @click="removeItem(it.id)">
              Xóa
            </c-button>
          </div>
          <div text-xs op-70>
            {{ it.width }}×{{ it.height }} • {{ formatBytes(it.file.size) }}
            <span v-if="it.outSize"> → {{ formatBytes(it.outSize) }}</span>
          </div>
          <div grid grid-cols-2 gap-2>
            <img :src="it.src" alt="original" max-h-160px w-full rounded bg-gray-100 object-contain>
            <img v-if="it.outUrl" :src="it.outUrl" alt="converted" max-h-160px w-full rounded bg-gray-100 object-contain>
            <div v-else max-h-160px min-h-100px flex items-center justify-center rounded bg-gray-50 text-sm op-60>
              {{ it.status === 'converting' ? 'Đang convert...' : it.status === 'error' ? `Lỗi: ${it.error}` : 'Chưa convert' }}
            </div>
          </div>
          <div flex gap-2>
            <c-button size="small" @click="convertOne(it)">
              Convert
            </c-button>
            <c-button size="small" type="primary" :disabled="!it.outBlob" @click="downloadOne(it)">
              Tải xuống
            </c-button>
          </div>
        </div>
      </div>
    </c-card>
  </div>
</template>
