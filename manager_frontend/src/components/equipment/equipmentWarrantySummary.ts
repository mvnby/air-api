import type {
  ManagerEquipmentItemResponse,
  ManagerEquipmentWarrantyCoverageResponse,
} from '../../client';

export type EquipmentWarrantySummary = {
  status: 'active' | 'attention' | 'expired' | 'scheduled' | 'unknown';
  label: string;
  expiresAt: string | null;
};

const earliestDate = (values: Array<string | null | undefined>) => (
  values.filter((value): value is string => Boolean(value)).sort()[0] || null
);

export const equipmentWarrantySummary = (
  item: Pick<ManagerEquipmentItemResponse, 'warranty_status' | 'warranty_expires_at'>,
  coverages?: ManagerEquipmentWarrantyCoverageResponse[],
): EquipmentWarrantySummary => {
  if (coverages !== undefined) {
    if (!coverages.length) return { status: 'unknown', label: 'Гарантию нужно уточнить', expiresAt: null };

    const available = coverages.filter((coverage) => coverage.decision_status !== 'voided');
    const active = available.filter((coverage) => coverage.time_status === 'active');
    if (active.length) {
      const overdue = active.some((coverage) => coverage.maintenance_status === 'overdue');
      const dueSoon = active.some((coverage) => coverage.maintenance_status === 'due_soon');
      return {
        status: overdue ? 'attention' : 'active',
        label: overdue
          ? 'Гарантия: ТО просрочено'
          : dueSoon
            ? 'Гарантия действует · ТО скоро'
            : active.length > 1 ? 'Покрытия действуют' : 'Гарантия действует',
        expiresAt: earliestDate(active.map((coverage) => coverage.expires_at)),
      };
    }

    const scheduled = available.filter((coverage) => coverage.time_status === 'scheduled');
    if (scheduled.length) {
      return {
        status: 'scheduled',
        label: 'Гарантия начнется',
        expiresAt: earliestDate(scheduled.map((coverage) => coverage.expires_at)),
      };
    }

    const expired = available.filter((coverage) => coverage.time_status === 'expired');
    if (expired.length) {
      return {
        status: 'expired',
        label: 'Гарантия истекла',
        expiresAt: earliestDate(expired.map((coverage) => coverage.expires_at)),
      };
    }

    if (!available.length) return { status: 'expired', label: 'Снято с гарантии', expiresAt: null };
    return { status: 'unknown', label: 'Гарантию нужно уточнить', expiresAt: null };
  }

  const legacyStatus = item.warranty_status || 'unknown';
  if (legacyStatus === 'active') return { status: 'active', label: 'Гарантия действует', expiresAt: item.warranty_expires_at || null };
  if (legacyStatus === 'expired') return { status: 'expired', label: 'Гарантия истекла', expiresAt: item.warranty_expires_at || null };
  if (legacyStatus === 'scheduled') return { status: 'scheduled', label: 'Гарантия начнется', expiresAt: item.warranty_expires_at || null };
  return { status: 'unknown', label: 'Гарантию нужно уточнить', expiresAt: null };
};
