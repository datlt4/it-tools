<script setup lang="ts">
import { checkBackendHealth, convertViaBackend, getConverterApiBase } from '@/utils/converterApi';
import { downloadBlob, getBaseName } from '@/utils/media';
import { formatBytes } from '@/utils/convert';

type Tab = 'text2pdf' | 'office2pdf' | 'pdf2other';

const activeTab = ref<Tab>('text2pdf');
const tabOptions = [
  { label: 'Text/Markdown → PDF (local)', value: 'text2pdf' },
  { label: 'Office → PDF (backend)', value: 'office2pdf' },
  { label: 'PDF → khác (backend)', value: 'pdf2other' },
];

const mdText = ref('# Tiêu đề\n\nNhập text/markdown ở đây rồi bấm tạo PDF...\n');
const pdfTitle = ref('document');
const isWorking = ref(false);
const error = ref('');
const backendOk = ref<boolean | null>(null);
const apiBase = ref(getConverterApiBase());

const officeFiles = ref<File[]>([]);
const pdfFile = ref<File | null>(null);
const pdfJob = ref<'text' | 'images'>('text');
const resultUrl = ref<string | null>(null);
const resultName = ref('');
const resultSize = ref<number | null>(null);
let resultBlob: Blob | null = null;

async function ping() {
  backendOk.value = await checkBackendHealth();
}
onMounted(ping);

function onOffice(files: File[]) {
  officeFiles.value.push(...files);
}
function onPdf(f: File) {
  pdfFile.value = f;
}

function clearResult() {
  if (resultUrl.value)
    URL.revokeObjectURL(resultUrl.value);
  resultUrl.value = null;
  resultBlob = null;
  resultSize.value = null;
}

async function textToPdf() {
  error.value = '';
  clearResult();
  isWorking.value = true;
  try {
    const { PDFDocument, StandardFonts } = await import('pdf-lib');
    const doc = await PDFDocument.create();
    const font = await doc.embedFont(StandardFonts.Helvetica);
    const fontSize = 12;
    const margin = 50;
    let page = doc.addPage();
    let { width, height } = page.getSize();
    let y = height - margin;
    const maxWidth = width - margin * 2;

    const lines: string[] = [];
    for (const raw of mdText.value.split('\n')) {
      const words = raw.split(' ');
      let cur = '';
      for (const w of words) {
        const test = cur ? `${cur} ${w}` : w;
        if (font.widthOfTextAtSize(test, fontSize) > maxWidth && cur) {
          lines.push(cur);
          cur = w;
        }
        else {
          cur = test;
        }
      }
      lines.push(cur);
    }

    for (const line of lines) {
      if (y < margin + 20) {
        page = doc.addPage();
        ({ width, height } = page.getSize());
        y = height - margin;
      }
      page.drawText(line, { x: margin, y, size: fontSize, font });
      y -= fontSize + 4;
    }
    const bytes = await doc.save({ useObjectStreams: true });
    const blob = new Blob([bytes.buffer as ArrayBuffer], { type: 'application/pdf' });
    resultBlob = blob;
    resultUrl.value = URL.createObjectURL(blob);
    resultName.value = `${pdfTitle.value || 'document'}.pdf`;
    resultSize.value = blob.size;
  }
  catch (e: any) {
    error.value = e?.message ?? String(e);
  }
  finally {
    isWorking.value = false;
  }
}

async function officeToPdf() {
  error.value = '';
  clearResult();
  if (!officeFiles.value.length) {
    error.value = 'Chọn ít nhất 1 file docx/pptx/xlsx/md/html/txt.';
    return;
  }
  isWorking.value = true;
  try {
    const blob = await convertViaBackend({ endpoint: '/convert/office-to-pdf', files: officeFiles.value });
    resultBlob = blob;
    resultUrl.value = URL.createObjectURL(blob);
    resultName.value = officeFiles.value.length === 1 ? `${getBaseName(officeFiles.value[0].name)}.pdf` : 'converted.pdf';
    if (blob.type === 'application/zip' && officeFiles.value.length > 1)
      resultName.value = 'converted.zip';
    resultSize.value = blob.size;
  }
  catch (e: any) {
    error.value = `${e?.message ?? String(e)} — kiểm tra backend ${apiBase.value} đã chạy chưa (docker compose up server).`;
  }
  finally {
    isWorking.value = false;
  }
}

async function pdfToOther() {
  error.value = '';
  clearResult();
  if (!pdfFile.value) {
    error.value = 'Chọn 1 file PDF.';
    return;
  }
  isWorking.value = true;
  try {
    const endpoint = pdfJob.value === 'text' ? '/convert/pdf-to-text' : '/convert/pdf-to-images';
    const blob = await convertViaBackend({ endpoint, files: [pdfFile.value] });
    if (pdfJob.value === 'text') {
      const text = await blob.text();
      const out = new Blob([text], { type: 'text/plain' });
      resultBlob = out;
      resultName.value = `${getBaseName(pdfFile.value.name)}.txt`;
      resultSize.value = out.size;
    }
    else {
      resultBlob = blob;
      resultName.value = `${getBaseName((pdfFile.value as File).name)}-images.zip`;
      resultSize.value = blob.size;
    }
    if (resultBlob)
      resultUrl.value = URL.createObjectURL(resultBlob);
  }
  catch (e: any) {
    error.value = `${e?.message ?? String(e)} — kiểm tra backend.`;
  }
  finally {
    isWorking.value = false;
  }
}

function downloadResult() {
  if (resultBlob)
    downloadBlob(resultBlob, resultName.value);
}

function printHtml() {
  window.print();
}
</script>

<template>
  <div flex flex-col gap-4>
    <c-card title="Document converter">
      <c-buttons-select v-model:value="activeTab" :options="tabOptions" />
      <div mt-2 text-sm op-70>
        API backend: <code>{{ apiBase }}</code> •
        <span v-if="backendOk === true" text-green-600>online</span>
        <span v-else-if="backendOk === false" text-red-500>offline — text→PDF local vẫn chạy, Office/PDF→cần docker compose up</span>
        <span v-else>đang kiểm tra...</span>
        <c-button size="small" ml-2 @click="ping">
          Kiểm tra lại
        </c-button>
      </div>
      <div text-xs op-60 mt-1>
        Đổi endpoint bằng biến môi trường <code>VITE_CONVERTER_API_URL</code> khi build.
      </div>
    </c-card>

    <c-card v-if="activeTab === 'text2pdf'" title="Text / Markdown → PDF (local)">
      <c-input-text v-model:value="pdfTitle" label="Tên file" placeholder="document" />
      <c-input-text v-model:value="mdText" label="Nội dung" multiline rows="12" placeholder="# Hello" mt-3 />
      <div flex gap-2 mt-3>
        <c-button type="primary" :disabled="isWorking" @click="textToPdf">
          {{ isWorking ? 'Đang tạo...' : 'Tạo PDF' }}
        </c-button>
        <c-button v-if="resultUrl" @click="downloadResult">
          Tải {{ resultName }} {{ resultSize ? `(${formatBytes(resultSize)})` : '' }}
        </c-button>
      </div>
      <iframe v-if="resultUrl" :src="resultUrl" w-full h-500px mt-3 border rounded />
      <c-alert mt-3 type="info">
        Bản local chỉ render text đơn giản (chưa hỗ trợ tiếng Việt có dấu đầy đủ với font Helvetica — backend LibreOffice sẽ giữ font tốt hơn). Muốn giữ format đẹp: dùng tab Office→PDF với file .md/.html.
      </c-alert>
    </c-card>

    <c-card v-if="activeTab === 'office2pdf'" title="Office / HTML / MD → PDF (backend LibreOffice)">
      <c-file-upload multiple accept=".docx,.doc,.pptx,.ppt,.xlsx,.xls,.odt,.ods,.odp,.html,.htm,.md,.txt,.rtf" title="Kéo thả docx/pptx/xlsx/md/html..." @files-upload="onOffice" />
      <div v-if="officeFiles.length" mt-2 text-sm>
        <div v-for="(f, i) in officeFiles" :key="i">
          {{ f.name }} • {{ formatBytes(f.size) }}
        </div>
        <c-button size="small" mt-2 @click="officeFiles = []">
          Xóa
        </c-button>
      </div>
      <div flex gap-2 mt-3>
        <c-button type="primary" :disabled="isWorking || !officeFiles.length" @click="officeToPdf">
          {{ isWorking ? 'Backend đang convert...' : 'Convert → PDF' }}
        </c-button>
        <c-button v-if="resultUrl" @click="downloadResult">
          Tải {{ resultName }}
        </c-button>
        <c-button @click="printHtml">
          Hoặc: In trang hiện tại ra PDF
        </c-button>
      </div>
    </c-card>

    <c-card v-if="activeTab === 'pdf2other'" title="PDF → Text / Ảnh (backend)">
      <c-file-upload accept=".pdf" title="Chọn 1 file PDF" @file-upload="onPdf" />
      <div v-if="pdfFile" mt-2 text-sm>
        {{ pdfFile.name }} • {{ formatBytes(pdfFile.size) }}
      </div>
      <div mt-3>
        <c-buttons-select v-model:value="pdfJob" :options="[{ label: 'Trích text', value: 'text' }, { label: 'Xuất ảnh từng trang (zip)', value: 'images' }]" />
      </div>
      <div flex gap-2 mt-3>
        <c-button type="primary" :disabled="isWorking || !pdfFile" @click="pdfToOther">
          {{ isWorking ? 'Đang xử lý...' : 'Chạy' }}
        </c-button>
        <c-button v-if="resultUrl" @click="downloadResult">
          Tải {{ resultName }}
        </c-button>
      </div>
    </c-card>

    <c-alert v-if="error" type="error">
      {{ error }}
    </c-alert>
  </div>
</template>
