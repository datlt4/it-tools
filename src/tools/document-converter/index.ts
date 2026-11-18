import { FileText } from '@vicons/tabler';
import { defineTool } from '../tool';

export const tool = defineTool({
  name: 'Document converter',
  path: '/document-converter',
  description: 'Text/MD → PDF local, Office → PDF và PDF → text/ảnh qua backend.',
  keywords: ['doc', 'pdf', 'docx', 'office', 'convert', 'libreoffice', 'pdf to text'],
  component: () => import('./document-converter.vue'),
  icon: FileText,
  createdAt: new Date('2026-11-09'),
});
