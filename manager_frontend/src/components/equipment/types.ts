import type {
  ManagerEquipmentItemResponse,
  ManagerEquipmentListResponse,
} from '../../client';

export const EQUIPMENT_ATTENTION_FILTERS = [
  'all',
  'needs_decision',
  'maintenance_due_soon',
  'maintenance_overdue',
  'warranty_expiring',
  'warranty_expired',
] as const;

export type EquipmentAttentionFilter = typeof EQUIPMENT_ATTENTION_FILTERS[number];
export type EquipmentAttentionReason = Exclude<EquipmentAttentionFilter, 'all'>;

export type EquipmentRegistryItem = ManagerEquipmentItemResponse & {
  customer_name?: string | null;
  customer_phone?: string | null;
  branch_name?: string | null;
  branch_address?: string | null;
  service_contact_name?: string | null;
  service_contact_phone?: string | null;
  last_service_at?: string | null;
  next_maintenance_due_at?: string | null;
  attention_reasons: string[];
};

export type EquipmentRegistryListResponse = Omit<ManagerEquipmentListResponse, 'items'> & {
  items: EquipmentRegistryItem[];
};

export type EquipmentRegistryQuery = {
  page: number;
  limit: number;
  q?: string;
  attention?: EquipmentAttentionFilter;
};
