export function getConverterApiBase(): string {
  const fromEnv = (import.meta as any)?.env?.VITE_CONVERTER_API_URL as string | undefined;
  if (fromEnv && fromEnv.trim() !== '') {
    return fromEnv.replace(/\/$/, '');
  }
  // Mặc định: cùng origin qua /api (nginx proxy sang converter).
  // Không lo mixed-content/TLS/port khi mở web qua domain hay LAN/WG.
  // Dev local (vite :5173, không có proxy) thì localhost:8000.
  if (typeof window !== 'undefined' && window.location?.hostname) {
    const h = window.location.hostname;
    if (h && h !== 'localhost' && h !== '127.0.0.1') {
      return `${window.location.origin}/api`;
    }
  }
  return 'http://localhost:8000';
}

export async function convertViaBackend(opts: {
  endpoint: string
  files: File[]
  fields?: Record<string, string>
  outFilename?: string
}): Promise<Blob> {
  const base = getConverterApiBase();
  const fd = new FormData();
  for (const f of opts.files) {
    fd.append('files', f, f.name);
  }
  if (opts.fields) {
    for (const [k, v] of Object.entries(opts.fields)) {
      fd.append(k, v);
    }
  }
  const res = await fetch(`${base}${opts.endpoint}`, { method: 'POST', body: fd });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Backend error ${res.status}: ${text.slice(0, 500)}`);
  }
  return await res.blob();
}

export async function checkBackendHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${getConverterApiBase()}/health`, { method: 'GET' });
    return res.ok;
  }
  catch {
    return false;
  }
}

// ------------------------- jobs (long-running ffmpeg) ---

export interface ConverterJob {
  id: string
  name: string
  format: string
  status: 'queued' | 'running' | 'paused' | 'done' | 'error' | 'canceled'
  progress: number
  created_at: number
  error: string | null
  out_filename: string | null
  out_size: number | null
}

export async function startMediaJob(opts: {
  files: File[]
  format: string
  crf?: number
  resolution?: string
  trimStart?: string
  trimDuration?: string
  merge?: boolean
}): Promise<ConverterJob> {
  const fd = new FormData();
  for (const f of opts.files) {
    fd.append('files', f, f.name);
  }
  fd.append('format', opts.format);
  fd.append('crf', String(opts.crf ?? 23));
  fd.append('resolution', opts.resolution ?? 'original');
  fd.append('trim_start', opts.trimStart ?? '');
  fd.append('trim_duration', opts.trimDuration ?? '');
  fd.append('merge', opts.merge ? 'true' : 'false');
  const res = await fetch(`${getConverterApiBase()}/jobs/media`, { method: 'POST', body: fd });
  if (!res.ok) {
    throw new Error(`Backend error ${res.status}: ${(await res.text().catch(() => '')).slice(0, 300)}`);
  }
  return await res.json();
}

export async function listJobs(): Promise<ConverterJob[]> {
  const res = await fetch(`${getConverterApiBase()}/jobs`);
  if (!res.ok) {
    throw new Error(`Backend error ${res.status}`);
  }
  return await res.json();
}

export async function pauseJob(id: string): Promise<ConverterJob> {
  const res = await fetch(`${getConverterApiBase()}/jobs/${id}/pause`, { method: 'POST' });
  if (!res.ok) {
    throw new Error(`Pause failed: ${res.status}`);
  }
  return await res.json();
}

export async function resumeJob(id: string): Promise<ConverterJob> {
  const res = await fetch(`${getConverterApiBase()}/jobs/${id}/resume`, { method: 'POST' });
  if (!res.ok) {
    throw new Error(`Resume failed: ${res.status}`);
  }
  return await res.json();
}

export async function cancelJob(id: string): Promise<ConverterJob> {
  const res = await fetch(`${getConverterApiBase()}/jobs/${id}/cancel`, { method: 'POST' });
  if (!res.ok) {
    throw new Error(`Cancel failed: ${res.status}`);
  }
  return await res.json();
}

export async function deleteJob(id: string): Promise<void> {
  await fetch(`${getConverterApiBase()}/jobs/${id}`, { method: 'DELETE' }).catch(() => {});
}

export function jobDownloadUrl(id: string): string {
  return `${getConverterApiBase()}/jobs/${id}/download`;
}
