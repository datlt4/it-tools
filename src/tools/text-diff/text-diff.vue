<script setup lang="ts">
import { diffLines } from 'diff';

interface Hunk {
  id: number
  oldStart: number // 1-based
  oldLines: string[]
  newStart: number // 1-based
  newLines: string[]
}

const diffEditor = ref<{ getOriginalValue: () => string
  getModifiedValue: () => string
  setOriginalValue: (v: string) => void
  setModifiedValue: (v: string) => void } | null>(null);

const hunks = ref<Hunk[]>([]);
const leftLineCount = ref(0);
const rightLineCount = ref(0);

function splitLines(text: string): string[] {
  return text === '' ? [] : text.split('\n');
}

function refresh() {
  const left = diffEditor.value?.getOriginalValue() ?? '';
  const right = diffEditor.value?.getModifiedValue() ?? '';
  const leftLines = splitLines(left);
  const rightLines = splitLines(right);
  leftLineCount.value = leftLines.length;
  rightLineCount.value = rightLines.length;

  const parts = diffLines(left, right);
  const out: Hunk[] = [];
  let o = 0;
  let n = 0;
  let cur: Hunk | null = null;
  const flush = () => {
    if (cur && (cur.oldLines.length || cur.newLines.length)) {
      out.push(cur);
    }
    cur = null;
  };
  parts.forEach((p) => {
    const lines = splitLines(p.value.replace(/\n$/, ''));
    if (!p.added && !p.removed) {
      flush();
      o += lines.length;
      n += lines.length;
      return;
    }
    if (!cur) {
      cur = { id: out.length, oldStart: o + 1, oldLines: [], newStart: n + 1, newLines: [] };
    }
    if (p.removed) {
      cur.oldLines.push(...lines);
      o += lines.length;
    }
    else {
      cur.newLines.push(...lines);
      n += lines.length;
    }
  });
  flush();
  hunks.value = out;
}

function applyMerge(h: Hunk, dir: 'left' | 'right') {
  const left = splitLines(diffEditor.value?.getOriginalValue() ?? '');
  const right = splitLines(diffEditor.value?.getModifiedValue() ?? '');
  if (dir === 'left') {
    // lấy bên trái sang phải: thay đoạn new bằng old
    right.splice(h.newStart - 1, h.newLines.length, ...h.oldLines);
    diffEditor.value?.setModifiedValue(right.join('\n'));
  }
  else {
    // lấy bên phải sang trái
    left.splice(h.oldStart - 1, h.oldLines.length, ...h.newLines);
    diffEditor.value?.setOriginalValue(left.join('\n'));
  }
  // đợi editor cập nhật rồi tính lại
  setTimeout(refresh, 50);
}

function mergeAll(dir: 'left' | 'right') {
  const left = splitLines(diffEditor.value?.getOriginalValue() ?? '');
  if (dir === 'left') {
    diffEditor.value?.setModifiedValue(left.join('\n'));
  }
  else {
    const right = splitLines(diffEditor.value?.getModifiedValue() ?? '');
    diffEditor.value?.setOriginalValue(right.join('\n'));
  }
  setTimeout(refresh, 50);
}

onMounted(() => {
  // editor tạo model async ở mounted con -> đợi 1 nhịp rồi quét
  setTimeout(refresh, 300);
});
</script>

<template>
  <c-card w-full important:flex-1 important:pa-0>
    <c-diff-editor ref="diffEditor" />
  </c-card>

  <c-card title="Merge từng change">
    <div mb-3 flex flex-wrap items-center gap-2>
      <c-button size="small" type="primary" @click="refresh">
        Quét changes ({{ hunks.length }} change, trái {{ leftLineCount }} dòng / phải {{ rightLineCount }} dòng)
      </c-button>
      <c-button size="small" :disabled="!hunks.length" @click="mergeAll('left')">
        Lấy hết bên trái →
      </c-button>
      <c-button size="small" :disabled="!hunks.length" @click="mergeAll('right')">
        ← Lấy hết bên phải
      </c-button>
    </div>

    <div v-if="!hunks.length" text-sm op-60>
      Hai bên giống nhau — không có change nào để merge. Sửa text ở editor phía trên rồi bấm Quét changes.
    </div>

    <div flex flex-col gap-3>
      <div v-for="h in hunks" :key="h.id" border rounded p-3>
        <div mb-2 text-sm font-medium>
          Change {{ h.id + 1 }} — trái dòng {{ h.oldStart }}{{ h.oldLines.length > 1 ? `–${h.oldStart + h.oldLines.length - 1}` : '' }} / phải dòng {{ h.newStart }}{{ h.newLines.length > 1 ? `–${h.newStart + h.newLines.length - 1}` : '' }}
        </div>
        <div grid grid-cols-1 gap-2 md:grid-cols-2>
          <pre max-h-200px overflow-auto rounded bg-red-100 p-2 text-xs dark:bg-red-950>{{ h.oldLines.join('\n') || '(trống)' }}</pre>
          <pre max-h-200px overflow-auto rounded bg-green-100 p-2 text-xs dark:bg-green-950>{{ h.newLines.join('\n') || '(trống)' }}</pre>
        </div>
        <div mt-2 flex flex-wrap gap-2>
          <c-button size="small" type="primary" @click="applyMerge(h, 'left')">
            Merge → (lấy trái)
          </c-button>
          <c-button size="small" type="primary" @click="applyMerge(h, 'right')">
            ← Merge (lấy phải)
          </c-button>
        </div>
      </div>
    </div>
  </c-card>
</template>
