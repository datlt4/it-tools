import { Photo } from '@vicons/tabler';
import { defineTool } from '../tool';

export const tool = defineTool({
  name: 'Image converter',
  path: '/image-converter',
  description: 'Convert ảnh PNG/JPG/WEBP/GIF/BMP, resize, nén, xoay — 100% client-side.',
  keywords: ['image', 'converter', 'png', 'jpg', 'webp', 'resize', 'compress', 'rotate', 'convert anh'],
  component: () => import('./image-converter.vue'),
  icon: Photo,
  createdAt: new Date('2026-11-09'),
});
