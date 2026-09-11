import type {
  EquipmentAttentionFilter,
  EquipmentAttentionReason,
} from './types';
import type { ManagerEquipmentItemResponse } from '../../client';
import { equipmentWarrantySummary } from './equipmentWarrantySummary';

export const ATTENTION_FILTER_OPTIONS: ReadonlyArray<{
  value: EquipmentAttentionFilter;
  label: string;
}> = [
  { value: 'all', label: 'Все' },
  { value: 'needs_decision', label: 'Требует решения' },
  { value: 'maintenance_due_soon', label: 'ТО скоро' },
  { value: 'maintenance_overdue', label: 'ТО просрочено' },
  { value: 'warranty_expiring', label: 'Гарантия истекает' },
  { value: 'warranty_expired', label: 'Гарантия истекла' },
];

const ATTENTION_PRIORITY: Record<EquipmentAttentionReason, number> = {
  needs_decision: 0,
  maintenance_overdue: 1,
  warranty_expired: 2,
  maintenance_due_soon: 3,
  warranty_expiring: 4,
};

const DATE_FORMATTER = new Intl.DateTimeFormat('ru-BY', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
});

const compactText = (value: string | null | undefined) => value?.trim() || '';

export const equipmentTitle = (item: ManagerEquipmentItemResponse) => (
  compactText(item.display_name)
  || [compactText(item.brand), compactText(item.model)].filter(Boolean).join(' ')
  || compactText(item.equipment_type)
  || `Оборудование #${item.id}`
);

export const equipmentSubtitle = (item: ManagerEquipmentItemResponse) => {
  const title = equipmentTitle(item).toLocaleLowerCase();
  const model = compactText(item.model);
  const brand = compactText(item.brand);
  const parts = [brand, model].filter((value) => value && !title.includes(value.toLocaleLowerCase()));
  return parts.filter((value, index) => !parts.some((other, otherIndex) => otherIndex !== index && other.toLocaleLowerCase().includes(value.toLocaleLowerCase()))).join(' ');
};

export const equipmentIdentifiers = (item: ManagerEquipmentItemResponse) => [
  compactText(item.serial) ? `S/N ${compactText(item.serial)}` : '',
  compactText(item.inventory_number) ? `Инв. ${compactText(item.inventory_number)}` : '',
].filter(Boolean).join(' · ');

export const equipmentLocation = (item: ManagerEquipmentItemResponse) => [
  compactText(item.branch_name),
  compactText(item.branch_address) || compactText(item.location_hint),
].filter(Boolean).join(' · ');

export const serviceContactName = (item: ManagerEquipmentItemResponse) => (
  compactText(item.service_contact_name) || compactText(item.customer_name)
);

export const serviceContactPhone = (item: ManagerEquipmentItemResponse) => (
  compactText(item.service_contact_phone) || compactText(item.customer_phone)
);

export const hasDistinctServiceContact = (item: ManagerEquipmentItemResponse) => {
  const contactName = serviceContactName(item).toLocaleLowerCase();
  const customerName = compactText(item.customer_name).toLocaleLowerCase();
  const contactPhone = serviceContactPhone(item).replace(/\D/g, '');
  const customerPhone = compactText(item.customer_phone).replace(/\D/g, '');
  return Boolean(
    (contactName && contactName !== customerName)
    || (contactPhone && contactPhone !== customerPhone)
  );
};

export const phoneHref = (phone: string | null | undefined) => {
  const normalized = compactText(phone).replace(/[^+\d]/g, '');
  return normalized ? `tel:${normalized}` : '';
};

export const formatEquipmentDate = (value: string | null | undefined) => {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : DATE_FORMATTER.format(date);
};

export const equipmentWarrantyDate = (item: ManagerEquipmentItemResponse) => {
  const summary = equipmentWarrantySummary(item);
  if (summary.status === 'none') return 'Без гарантии';
  if (summary.expiresAt) return formatEquipmentDate(summary.expiresAt);
  if (hasAttentionReason(item, 'warranty_expiring') || hasAttentionReason(item, 'warranty_expired')) {
    return 'См. покрытие';
  }
  return summary.status === 'unknown' ? 'Уточнить' : '—';
};

export const hasAttentionReason = (item: ManagerEquipmentItemResponse, reason: EquipmentAttentionReason) => (
  item.attention_reasons?.includes(reason) ?? false
);

export const sortAttentionReasons = (reasons: string[]) => [...new Set(reasons)]
  .sort((left, right) => {
    const leftPriority = ATTENTION_PRIORITY[left as EquipmentAttentionReason] ?? 99;
    const rightPriority = ATTENTION_PRIORITY[right as EquipmentAttentionReason] ?? 99;
    return leftPriority - rightPriority || left.localeCompare(right);
  });

export const maintenanceDateClass = (item: ManagerEquipmentItemResponse) => {
  if (hasAttentionReason(item, 'maintenance_overdue')) return 'text-red-700 dark:text-red-300';
  if (hasAttentionReason(item, 'maintenance_due_soon')) return 'text-amber-700 dark:text-amber-300';
  return 'text-gray-800 dark:text-slate-200';
};

export const warrantyDateClass = (item: ManagerEquipmentItemResponse) => {
  if (hasAttentionReason(item, 'warranty_expired')) return 'text-red-700 dark:text-red-300';
  if (hasAttentionReason(item, 'warranty_expiring')) return 'text-amber-700 dark:text-amber-300';
  return 'text-gray-800 dark:text-slate-200';
};
