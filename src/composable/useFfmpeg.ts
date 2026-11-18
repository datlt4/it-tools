import { ref } from 'vue';

let ffmpegInstance: any | null = null;
let loadingPromise: Promise<any> | null = null;

const CORE_VERSION = '0.12.6';
const CORE_BASE = `https://cdn.jsdelivr.net/npm/@ffmpeg/core@${CORE_VERSION}/dist/esm`;

export function isFfmpegSupported() {
  return typeof window !== 'undefined' && typeof WebAssembly !== 'undefined' && !!window.Worker;
}

async function loadFfmpeg(progressCb?: (ratio: number) => void) {
  if (ffmpegInstance) {
    return ffmpegInstance;
  }

  if (loadingPromise) {
    return loadingPromise;
  }

  loadingPromise = (async () => {
    const [{ FFmpeg }, { toBlobURL, fetchFile: _fetchFile }] = await Promise.all([
      import('@ffmpeg/ffmpeg'),
      import('@ffmpeg/util'),
    ]);

    const ffmpeg = new FFmpeg();
    ffmpeg.on('progress', ({ progress }: { progress: number }) => progressCb?.(progress));

    const [coreURL, wasmURL] = await Promise.all([
      toBlobURL(`${CORE_BASE}/ffmpeg-core.js`, 'text/javascript'),
      toBlobURL(`${CORE_BASE}/ffmpeg-core.wasm`, 'application/wasm'),
    ]);

    await ffmpeg.load({ coreURL, wasmURL });
    ffmpegInstance = ffmpeg;
    void _fetchFile;
    return ffmpeg;
  })();

  return loadingPromise;
}

export function useFfmpeg() {
  const isLoaded = ref(false);
  const isLoading = ref(false);
  const loadError = ref<string | null>(null);
  const progress = ref(0);

  async function ensureLoaded() {
    if (ffmpegInstance) {
      isLoaded.value = true;
      return ffmpegInstance;
    }
    isLoading.value = true;
    loadError.value = null;
    try {
      const inst = await loadFfmpeg(r => (progress.value = r));
      isLoaded.value = true;
      return inst;
    }
    catch (e: any) {
      loadError.value = e?.message ?? String(e);
      throw e;
    }
    finally {
      isLoading.value = false;
    }
  }

  return { ensureLoaded, isLoaded, isLoading, loadError, progress, isSupported: isFfmpegSupported() };
}

export async function readFfmpegFile(file: File): Promise<Uint8Array> {
  const { fetchFile } = await import('@ffmpeg/util');
  return await fetchFile(file);
}
