import type { ManagerTariffResponse, ManagerTariffServiceKind } from '../../client';
import type { OrderWorkflowType } from './order-workspace';

export const SERVICE_KINDS: Array<{ value: ManagerTariffServiceKind; label: string }> = [
  { value: 'installation', label: 'Монтаж' },
  { value: 'maintenance', label: 'Обслуживание' },
  { value: 'dismantling', label: 'Демонтаж' },
  { value: 'pre_install', label: 'Закладка трассы' },
  { value: 'repair', label: 'Ремонт' },
];

export const preferredServiceKind = (workflow: OrderWorkflowType): ManagerTariffServiceKind => (
  workflow === 'maintenance' ? 'maintenance' : workflow === 'repair' ? 'repair' : 'installation'
);

export const orderedServiceKinds = (workflow: OrderWorkflowType) => {
  const preferred = preferredServiceKind(workflow);
  return [...SERVICE_KINDS].sort((a, b) => Number(b.value === preferred) - Number(a.value === preferred));
};

export const serviceCategories = (tariffs: ManagerTariffResponse[], kind: ManagerTariffServiceKind) => (
  [...new Set(tariffs.filter((tariff) => tariff.service_kind === kind)
    .map((tariff) => tariff.category.trim()).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, 'ru'))
);
