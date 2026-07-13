import type {
  EquipmentAttentionFilter,
  EquipmentAttentionReason,
  EquipmentRegistryItem,
} from './types';
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

export const equipmentTitle = (item: EquipmentRegistryItem) => (
  compactText(item.display_name)
  || [compactText(item.brand), compactText(item.model)].filter(Boolean).join(' ')
  || compactText(item.equipment_type)
  || `Оборудование #${item.id}`
);

export const equipmentSubtitle = (item: EquipmentRegistryItem) => {
  const identity = [compactText(item.brand), compactText(item.model)].filter(Boolean).join(' ');
  if (identity && identity.toLocaleLowerCase() !== compactText(item.display_name).toLocaleLowerCase()) {
    return identity;
  }
  return compactText(item.equipment_type);
};

export const equipmentIdentifiers = (item: EquipmentRegistryItem) => [
  compactText(item.serial) ? `S/N ${compactText(item.serial)}` : '',
  compactText(item.inventory_number) ? `Инв. ${compactText(item.inventory_number)}` : '',
].filter(Boolean).join(' · ');

export const equipmentLocation = (item: EquipmentRegistryItem) => [
  compactText(item.branch_name),
  compactText(item.branch_address) || compactText(item.location_hint),
].filter(Boolean).join(' · ');

export const serviceContactName = (item: EquipmentRegistryItem) => (
  compactText(item.service_contact_name) || compactText(item.customer_name)
);

export const serviceContactPhone = (item: EquipmentRegistryItem) => (
  compactText(item.service_contact_phone) || compactText(item.customer_phone)
);

export const hasDistinctServiceContact = (item: EquipmentRegistryItem) => {
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

export const equipmentWarrantyDate = (item: EquipmentRegistryItem) => {
  const summary = equipmentWarrantySummary(item);
  if (summary.expiresAt) return formatEquipmentDate(summary.expiresAt);
  if (hasAttentionReason(item, 'warranty_expiring') || hasAttentionReason(item, 'warranty_expired')) {
    return 'См. покрытие';
  }
  return summary.status === 'unknown' ? 'Уточнить' : '—';
};

export const hasAttentionReason = (item: EquipmentRegistryItem, reason: EquipmentAttentionReason) => (
  item.attention_reasons?.includes(reason) ?? false
);

export const sortAttentionReasons = (reasons: string[]) => [...new Set(reasons)]
  .sort((left, right) => {
    const leftPriority = ATTENTION_PRIORITY[left as EquipmentAttentionReason] ?? 99;
    const rightPriority = ATTENTION_PRIORITY[right as EquipmentAttentionReason] ?? 99;
    return leftPriority - rightPriority || left.localeCompare(right);
  });

export const maintenanceDateClass = (item: EquipmentRegistryItem) => {
  if (hasAttentionReason(item, 'maintenance_overdue')) return 'text-red-700 dark:text-red-300';
  if (hasAttentionReason(item, 'maintenance_due_soon')) return 'text-amber-700 dark:text-amber-300';
  return 'text-gray-800 dark:text-slate-200';
};

export const warrantyDateClass = (item: EquipmentRegistryItem) => {
  if (hasAttentionReason(item, 'warranty_expired')) return 'text-red-700 dark:text-red-300';
  if (hasAttentionReason(item, 'warranty_expiring')) return 'text-amber-700 dark:text-amber-300';
  return 'text-gray-800 dark:text-slate-200';
};
