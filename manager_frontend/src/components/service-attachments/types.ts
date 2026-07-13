export const SERVICE_ATTACHMENT_CATEGORIES = [
  { value: 'nameplate', label: 'Шильдик' },
  { value: 'before_work', label: 'До работ' },
  { value: 'after_work', label: 'После работ' },
  { value: 'installation_result', label: 'Результат монтажа' },
  { value: 'defect', label: 'Дефект' },
  { value: 'service', label: 'Обслуживание' },
  { value: 'document', label: 'Документ' },
  { value: 'other', label: 'Другое' },
] as const;

export type ServiceAttachmentCategory = (typeof SERVICE_ATTACHMENT_CATEGORIES)[number]['value'];
export type ServiceAttachmentVariant = 'preview' | 'original';

export type ServiceAttachmentItem = {
  id: number;
  file_kind: string;
  category: string;
  filename: string;
  mime_type: string;
  size_bytes: number | null;
  caption: string | null;
  transcript: string | null;
  source: string;
  processing_status: string;
  processing_error: string | null;
  captured_at: string | null;
  created_at: string;
  preview_available: boolean;
};

export type ServiceAttachmentListResponse = {
  items: ServiceAttachmentItem[];
  total: number;
};

export type ServiceAttachmentAccessResponse = {
  url: string;
  expires_at: string;
};

export type ServiceAttachmentUpdatePayload = {
  category?: ServiceAttachmentCategory | string;
  caption?: string | null;
  equipment_id?: number | null;
  component_id?: number | null;
};

export type ServiceAttachmentComponentOption = {
  id: number;
  label: string;
};

export type ServiceAttachmentEquipmentOption = {
  id: number;
  label: string;
  components?: ServiceAttachmentComponentOption[];
};

export const getAttachmentCategoryLabel = (category: string) => (
  SERVICE_ATTACHMENT_CATEGORIES.find((item) => item.value === category)?.label || category || 'Другое'
);

export const isImageAttachment = (item: ServiceAttachmentItem) => (
  item.file_kind === 'image' || item.mime_type.startsWith('image/')
);

export const isPdfAttachment = (item: ServiceAttachmentItem) => (
  item.file_kind === 'pdf' || item.mime_type === 'application/pdf'
);

export const isAudioAttachment = (item: ServiceAttachmentItem) => (
  item.file_kind === 'audio' || item.mime_type.startsWith('audio/')
);

export const formatAttachmentSize = (size: number | null | undefined) => {
  if (!size || size < 1) return '';
  if (size < 1024) return `${size} Б`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} КБ`;
  return `${(size / (1024 * 1024)).toFixed(size < 10 * 1024 * 1024 ? 1 : 0)} МБ`;
};

export const formatAttachmentDate = (value: string | null | undefined) => {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed);
};
