<script setup lang="ts">
import { downloadBlob, getBaseName, uid } from '@/utils/media';
import { formatBytes } from '@/utils/convert';

interface PdfFile { id: string; file: File }
type Tab = 'merge' | 'split' | 'rotate' | 'img2pdf';

const activeTab = ref<Tab>('merge');
const pdfs = ref<PdfFile[]>([]);
const isWorking = ref(false);
const error = ref('');
const resultUrl = ref<string | null>(null);
const resultName = ref('output.pdf');
const resultSize = ref<number | null>(null);
let resultBlob: Blob | null = null;

const splitRange = ref('1-3');
const rotateDeg = ref<90 | 180 | 270>(90);

const tabOptions = [
  { label: 'Gộp PDF', value: 'merge' },
  { label: 'Tách / trích trang', value: 'split' },
  { label: 'Xoay', value: 'rotate' },
  { label: 'Ảnh → PDF', value: 'img2pdf' },
];
const rotateOptions = [
  { label: '90°', value: 90 },
  { label: '180°', value: 180 },
  { label: '270°', value: 270 },
];

function onPdfFiles(files: File[]) {
  for (const f of files) {
    if (!f.name.toLowerCase().endsWith('.pdf')) {
      continue;
    }
    pdfs.value.push({ id: uid(), file: f });
  }
}
function onSingle(f: File) {
  onPdfFiles([f]);
}
function clearPdfs() {
  pdfs.value = [];
  clearResult();
}
function clearResult() {
  if (resultUrl.value) {
    URL.revokeObjectURL(resultUrl.value);
  }
  resultUrl.value = null;
  resultBlob = null;
  resultSize.value = null;
}
function move(idx: number, dir: -1 | 1) {
  const j = idx + dir;
  if (j < 0 || j >= pdfs.value.length) {
    return;
  }
  const arr = [...pdfs.value];
  const [x] = arr.splice(idx, 1);
  arr.splice(j, 0, x);
  pdfs.value = arr;
}

function parseRanges(input: string, max: number): number[] {
  const out = new Set<number>();
  for (const part of input.split(',').map(s => s.trim()).filter(Boolean)) {
    const m = part.match(/^(\d+)\s*-\s*(\d+)$/);
    if (m) {
      let a = Number(m[1]);
      let b = Number(m[2]);
      if (a > b) {
        [a, b] = [b, a];
      }
      for (let i = a; i <= b; i++) {
        if (i >= 1 && i <= max) {
          out.add(i);
        }
      }
    }
    else {
      const n = Number(part);
      if (Number.isInteger(n) && n >= 1 && n <= max) {
        out.add(n);
      }
    }
  }
  return [...out].sort((a, b) => a - b);
}

async function getPdfLib() {
  return await import('pdf-lib');
}

function setResult(blob: Blob, name: string) {
  clearResult();
  resultBlob = blob;
  resultUrl.value = URL.createObjectURL(blob);
  resultName.value = name;
  resultSize.value = blob.size;
}

async function runMerge() {
  error.value = '';
  if (pdfs.value.length < 1) {
    error.value = 'Chọn ít nhất 1 file PDF.';
    return;
  }
  isWorking.value = true;
  try {
    const { PDFDocument } = await getPdfLib();
    const merged = await PDFDocument.create();
    for (const p of pdfs.value) {
      const buf = await p.file.arrayBuffer();
      const doc = await PDFDocument.load(buf, { ignoreEncryption: true });
      const pages = await merged.copyPages(doc, doc.getPageIndices());
      for (const pg of pages) {
        merged.addPage(pg);
      }
    }
    const bytes = await merged.save({ useObjectStreams: true });
    setResult(new Blob([bytes.buffer as ArrayBuffer], { type: 'application/pdf' }), 'merged.pdf');
  }
  catch (e: any) {
    error.value = e?.message ?? String(e);
  }
  finally {
    isWorking.value = false;
  }
}

async function runSplit() {
  error.value = '';
  if (pdfs.value.length !== 1) {
    error.value = 'Chế độ tách chỉ dùng 1 file PDF. Hãy xóa bớt, chỉ giữ 1 file.';
    return;
  }
  isWorking.value = true;
  try {
    const { PDFDocument } = await getPdfLib();
    const buf = await pdfs.value[0].file.arrayBuffer();
    const src = await PDFDocument.load(buf, { ignoreEncryption: true });
    const total = src.getPageCount();
    const pages = parseRanges(splitRange.value, total);
    if (!pages.length) {
      throw new Error(`Range không hợp lệ. File có ${total} trang. VD: 1-3,5`);
    }
    const out = await PDFDocument.create();
    const copied = await out.copyPages(src, pages.map(n => n - 1));
    for (const pg of copied) {
      out.addPage(pg);
    }
    const bytes = await out.save({ useObjectStreams: true });
    setResult(new Blob([bytes.buffer as ArrayBuffer], { type: 'application/pdf' }), `${getBaseName(pdfs.value[0].file.name)}-p${pages[0]}-p${pages[pages.length - 1]}.pdf`);
  }
  catch (e: any) {
    error.value = e?.message ?? String(e);
  }
  finally {
    isWorking.value = false;
  }
}

async function runRotate() {
  error.value = '';
  if (pdfs.value.length !== 1) {
    error.value = 'Chế độ xoay chỉ dùng 1 file PDF.';
    return;
  }
  isWorking.value = true;
  try {
    const { PDFDocument, degrees } = await getPdfLib();
    const buf = await pdfs.value[0].file.arrayBuffer();
    const doc = await PDFDocument.load(buf, { ignoreEncryption: true });
    for (const pg of doc.getPages()) {
      pg.setRotation(degrees((pg.getRotation().angle + rotateDeg.value) % 360));
    }
    const bytes = await doc.save({ useObjectStreams: true });
    setResult(new Blob([bytes.buffer as ArrayBuffer], { type: 'application/pdf' }), `${getBaseName(pdfs.value[0].file.name)}-rotated.pdf`);
  }
  catch (e: any) {
    error.value = e?.message ?? String(e);
  }
  finally {
    isWorking.value = false;
  }
}

const imgFiles = ref<File[]>([]);
function onImgFiles(files: File[]) {
  imgFiles.value.push(...files.filter(f => f.type.startsWith('image/')));
}
function clearImgs() {
  imgFiles.value = [];
}

async function runImg2Pdf() {
  error.value = '';
  if (!imgFiles.value.length) {
    error.value = 'Chọn ít nhất 1 ảnh.';
    return;
  }
  isWorking.value = true;
  try {
    const { PDFDocument } = await getPdfLib();
    const doc = await PDFDocument.create();
    for (const f of imgFiles.value) {
      const buf = new Uint8Array(await f.arrayBuffer());
      let img: any;
      if (f.type === 'image/png') {
        img = await doc.embedPng(buf);
      }
      else if (f.type === 'image/jpeg' || f.type === 'image/jpg') {
        img = await doc.embedJpg(buf);
      }
      else {
        const bmp = await createImageBitmap(new Blob([buf.buffer as ArrayBuffer], { type: f.type }));
        const canvas = document.createElement('canvas');
        canvas.width = bmp.width;
        canvas.height = bmp.height;
        canvas.getContext('2d')!.drawImage(bmp, 0, 0);
        const jpgBlob: Blob | null = await new Promise((resolve) => {
          canvas.toBlob(b => resolve(b), 'image/jpeg', 0.85);
        });
        if (!jpgBlob) {
          throw new Error('Convert ảnh thất bại');
        }
        img = await doc.embedJpg(new Uint8Array(await jpgBlob.arrayBuffer()));
      }
      const page = doc.addPage([img.width, img.height]);
      page.drawImage(img, { x: 0, y: 0, width: img.width, height: img.height });
    }
    const bytes = await doc.save({ useObjectStreams: true });
    setResult(new Blob([bytes.buffer as ArrayBuffer], { type: 'application/pdf' }), 'images.pdf');
  }
  catch (e: any) {
    error.value = e?.message ?? String(e);
  }
  finally {
    isWorking.value = false;
  }
}

async function run() {
  if (activeTab.value === 'merge') {
    await runMerge();
  }
  else if (activeTab.value === 'split') {
    await runSplit();
  }
  else if (activeTab.value === 'rotate') {
    await runRotate();
  }
  else { await runImg2Pdf(); }
}

function downloadResult() {
  if (resultBlob) {
    downloadBlob(resultBlob, resultName.value);
  }
}
</script>

<template>
  <div flex flex-col gap-4>
    <c-card title="PDF Toolbox — gộp / tách / xoay / ảnh→PDF (client-side)">
      <c-buttons-select v-model:value="activeTab" :options="tabOptions" />
      <div v-if="activeTab !== 'img2pdf'" mt-4>
        <c-file-upload multiple accept=".pdf,application/pdf" title="Kéo thả PDF vào đây" @files-upload="onPdfFiles" @file-upload="onSingle" />
        <div v-if="pdfs.length" mt-3 flex flex-col gap-2>
          <div v-for="(p, i) in pdfs" :key="p.id" flex items-center justify-between gap-2 border rounded px-3 py-2>
            <div truncate>
              {{ i + 1 }}. {{ p.file.name }} • {{ formatBytes(p.file.size) }}
            </div>
            <div flex shrink-0 gap-1>
              <c-button size="small" :disabled="i === 0" @click="move(i, -1)">
                ↑
              </c-button>
              <c-button size="small" :disabled="i === pdfs.length - 1" @click="move(i, 1)">
                ↓
              </c-button>
              <c-button size="small" @click="pdfs.splice(i, 1)">
                Xóa
              </c-button>
            </div>
          </div>
          <c-button size="small" @click="clearPdfs">
            Xóa tất cả
          </c-button>
        </div>
      </div>
      <div v-else mt-4>
        <c-file-upload multiple accept="image/*" title="Kéo thả ảnh để tạo PDF" @files-upload="onImgFiles" />
        <div v-if="imgFiles.length" mt-2 text-sm>
          {{ imgFiles.length }} ảnh: {{ imgFiles.map(f => f.name).join(', ').slice(0, 200) }}
          <c-button size="small" ml-2 @click="clearImgs">
            Xóa
          </c-button>
        </div>
      </div>

      <div grid grid-cols-1 mt-4 gap-4 md:grid-cols-2>
        <c-input-text v-if="activeTab === 'split'" v-model:value="splitRange" label="Trang cần trích (vd 1-3,5,8-10)" placeholder="1-3" />
        <c-select v-if="activeTab === 'rotate'" v-model:value="rotateDeg" label="Góc xoay" :options="rotateOptions" />
      </div>

      <div mt-4 flex gap-2>
        <c-button type="primary" :disabled="isWorking" @click="run">
          {{ isWorking ? 'Đang xử lý...' : activeTab === 'merge' ? 'Gộp PDF' : activeTab === 'split' ? 'Tách PDF' : activeTab === 'rotate' ? 'Xoay PDF' : 'Tạo PDF từ ảnh' }}
        </c-button>
        <c-button v-if="resultUrl" @click="downloadResult">
          Tải {{ resultName }} {{ resultSize ? `(${formatBytes(resultSize)})` : '' }}
        </c-button>
      </div>
      <div v-if="error" mt-2 text-sm text-red-500>
        {{ error }}
      </div>
      <c-alert mt-3 type="info">
        Gộp/tách/xoay/ảnh→PDF chạy local bằng pdf-lib, không giới hạn số trang ở mức vừa phải. PDF scan nặng, mã hóa, hoặc cần OCR/nén mạnh → dùng backend.
      </c-alert>
      <iframe v-if="resultUrl" :src="resultUrl" mt-3 h-500px w-full border rounded />
    </c-card>
  </div>
</template>
