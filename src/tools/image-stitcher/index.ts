import { LayersDifference } from '@vicons/tabler';
import { defineTool } from '../tool';

export const tool = defineTool({
  name: 'Image stitcher',
  path: '/image-stitcher',
  description: 'Ghép screenshot cuộn dọc thành ảnh dài hoặc panorama — job backend OpenCV.',
  keywords: ['stitch', 'panorama', 'screenshot', 'ghep anh', 'long screenshot', 'opencv'],
  component: () => import('./image-stitcher.vue'),
  icon: LayersDifference,
  createdAt: new Date('2026-11-22'),
});
