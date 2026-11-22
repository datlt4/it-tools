import { Video } from '@vicons/tabler';
import { defineTool } from '../tool';

export const tool = defineTool({
  name: 'Video converter',
  path: '/video-converter',
  description: 'Convert mp4/webm/mkv, cắt đoạn, tách mp3, tạo GIF — job chạy dưới backend.',
  keywords: ['video', 'converter', 'mp4', 'webm', 'gif', 'mp3', 'trim', 'cut video'],
  component: () => import('./video-converter.vue'),
  icon: Video,
  createdAt: new Date('2026-11-09'),
});
