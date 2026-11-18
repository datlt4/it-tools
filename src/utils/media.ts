export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, 500);
}

export function downloadUrl(url: string, filename: string) {
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

export function getBaseName(filename: string) {
  const idx = filename.lastIndexOf('.');
  return idx === -1 ? filename : filename.slice(0, idx);
}

export function getExtension(filename: string) {
  const idx = filename.lastIndexOf('.');
  return idx === -1 ? '' : filename.slice(idx + 1).toLowerCase();
}

export function formatTime(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0)
    return '0:00';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function parseTimeToSeconds(input: string): number | null {
  const v = input.trim().replace(',', '.');
  if (v === '')
    return null;
  if (/^\d+(\.\d+)?$/.test(v))
    return Number.parseFloat(v);
  const parts = v.split(':').map(Number);
  if (parts.some(n => Number.isNaN(n)))
    return null;
  let total = 0;
  for (const p of parts)
    total = total * 60 + p;
  return total;
}

export function uid() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}
