import { Music } from '@vicons/tabler';
import { defineTool } from '../tool';

export const tool = defineTool({
  name: 'Audio converter',
  path: '/audio-converter',
  description: 'Convert mp3/wav/ogg/m4a/flac, cắt và nối audio — ffmpeg.wasm client-side.',
  keywords: ['audio', 'converter', 'mp3', 'wav', 'ogg', 'flac', 'cut', 'merge', 'trim'],
  component: () => import('./audio-converter.vue'),
  icon: Music,
  createdAt: new Date('2026-11-09'),
});
