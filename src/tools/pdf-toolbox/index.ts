import { Files } from '@vicons/tabler';
import { defineTool } from '../tool';

export const tool = defineTool({
  name: 'PDF toolbox',
  path: '/pdf-toolbox',
  description: 'Gộp, tách, xoay PDF và tạo PDF từ ảnh — 100% client-side.',
  keywords: ['pdf', 'merge', 'split', 'rotate', 'images to pdf', 'gop pdf', 'tach pdf'],
  component: () => import('./pdf-toolbox.vue'),
  icon: Files,
  createdAt: new Date('2026-11-09'),
});
