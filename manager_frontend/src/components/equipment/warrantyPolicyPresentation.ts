import type { ManagerWarrantyPolicyResponse } from '../../client';

export const warrantyDurationLabel = (months?: number | null) => {
  if (!months) return 'Срок не задан';
  if (months % 12) return `${months} мес.`;
  const years = months / 12;
  const lastTwo = years % 100;
  const ending = lastTwo >= 11 && lastTwo <= 14 ? 'лет'
    : years % 10 === 1 ? 'год' : years % 10 >= 2 && years % 10 <= 4 ? 'года' : 'лет';
  return `${years} ${ending}`;
};

export const warrantySeriesIds = (policy: ManagerWarrantyPolicyResponse | null): number[] => (
  policy?.series_ids?.length ? [...policy.series_ids] : policy?.series_id ? [policy.series_id] : []
);

export const warrantyScopeLabel = (policy: ManagerWarrantyPolicyResponse) => {
  const parts: string[] = [];
  if (policy.supplier_id) parts.push(policy.supplier_name || `Поставщик #${policy.supplier_id}`);
  if (policy.brand_id) parts.push(policy.brand_title || `Бренд #${policy.brand_id}`);
  if (policy.product_id) parts.push(policy.product_title || `Товар #${policy.product_id}`);
  else {
    const ids = warrantySeriesIds(policy);
    if (ids.length) parts.push(ids.map((id, index) => (
      policy.series_titles?.[index] || (id === policy.series_id ? policy.series_title : null) || `Серия #${id}`
    )).join(', '));
    else if (policy.brand_id) parts.push('Все серии');
  }
  return parts.join(' · ') || 'Область не указана';
};
