import type { OrderProductLineResponse } from '../../../client';
import type {
  LogisticsComponentKind,
  OrderLogisticsComponent,
  ProductLogisticsTemplateComponent,
  WaybillProductLine,
} from './document-types';

const LOGISTICS_COMPONENT_KINDS = new Set(['indoor', 'outdoor', 'accessory', 'other']);

export const hasUsableWaybillProductLine = (line: WaybillProductLine) => (
  String(line.product_query || '').trim().length > 0
  && Number(line.quantity || 0) > 0
);

export const mapOrderProductLineToWaybillLine = (line: OrderProductLineResponse): WaybillProductLine => ({
  id: line.id,
  proposal_id: line.proposal_id,
  product_id: line.product_id,
  product_query: line.product_title || '',
  quantity: Number(line.quantity || 0),
  price: Number(line.price || 0),
  cost: Number(line.cost || 0),
  product_country: (line as any).product_country || null,
  product_logistics_components: Array.isArray((line as any).product_logistics_components)
    ? ((line as any).product_logistics_components as ProductLogisticsTemplateComponent[])
    : [],
  logistics_components: Array.isArray((line as any).logistics_components) && (line as any).logistics_components.length
    ? ((line as any).logistics_components as OrderLogisticsComponent[])
    : null,
});

export const cloneWaybillProductLine = (line: WaybillProductLine): WaybillProductLine => ({
  ...line,
  product_logistics_components: (line.product_logistics_components || []).map((component) => ({ ...component })),
  logistics_components: line.logistics_components?.length
    ? line.logistics_components.map((component) => ({ ...component }))
    : null,
});

const normalizeLogisticsKind = (value: unknown): LogisticsComponentKind => {
  const raw = String(value || '').trim();
  return LOGISTICS_COMPONENT_KINDS.has(raw) ? (raw as LogisticsComponentKind) : 'other';
};

const normalizePositiveInteger = (value: unknown, fallback = 1) => {
  const parsed = Math.trunc(Number(value));
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
};

const normalizePositiveNumber = (value: unknown, fallback = 0) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
};

const roundToNearest10 = (value: number) => Math.floor((Number(value || 0) + 5) / 10) * 10;
const roundMoney = (value: number) => Number(Number(value || 0).toFixed(2));

const allocateLogisticsPrices = (templates: ProductLogisticsTemplateComponent[], price: number): OrderLogisticsComponent[] => {
  if (!templates.length) return [];
  const weights = templates.map((item) => Math.max(0, Number(item.price_weight ?? 1)));
  const totalWeight = weights.some((item) => item > 0)
    ? weights.reduce((sum, item) => sum + item, 0)
    : templates.length;
  let remaining = Number(price || 0);
  return templates.map((item, index) => {
    const quantityPerParent = normalizePositiveInteger(item.quantity_per_parent, 1);
    const componentTotal = index === templates.length - 1
      ? remaining
      : roundToNearest10(Number(price || 0) * ((weights[index] || 1) / totalWeight));
    if (index !== templates.length - 1) remaining -= componentTotal;
    return {
      title: item.title,
      country: item.country || 'Китай',
      unit: item.unit || 'шт.',
      quantity_per_parent: quantityPerParent,
      unit_price: roundMoney(componentTotal / quantityPerParent),
      kind: normalizeLogisticsKind(item.kind),
    };
  });
};

const createDefaultWaybillSplit = (line: WaybillProductLine): OrderLogisticsComponent[] => {
  const title = String(line.product_query || '').trim();
  const country = line.product_country || 'Китай';
  return allocateLogisticsPrices([
    { title: title ? `Внутренний блок ${title}` : 'Внутренний блок', country, unit: 'шт.', quantity_per_parent: 1, price_weight: 1, kind: 'indoor' },
    { title: title ? `Наружный блок ${title}` : 'Наружный блок', country, unit: 'шт.', quantity_per_parent: 1, price_weight: 2, kind: 'outdoor' },
  ], Number(line.price || 0));
};

export const ensureWaybillComponents = (line: WaybillProductLine) => {
  if (line.logistics_components?.length) return;
  line.logistics_components = line.product_logistics_components?.length
    ? allocateLogisticsPrices(line.product_logistics_components, Number(line.price || 0))
    : createDefaultWaybillSplit(line);
};

const componentPerParentTotal = (component: OrderLogisticsComponent) => (
  normalizePositiveNumber(component.unit_price, 0) * normalizePositiveInteger(component.quantity_per_parent, 1)
);

export const lineLogisticsPerParentTotal = (line: WaybillProductLine) => (
  (line.logistics_components || []).reduce((sum, component) => sum + componentPerParentTotal(component), 0)
);

const chooseBalanceComponentIndex = (components: OrderLogisticsComponent[], changedIndex: number | null) => {
  if (!components.length) return -1;
  if (components.length === 1) return 0;
  const changedKind = changedIndex === null ? null : normalizeLogisticsKind(components[changedIndex]?.kind);
  const preferredKind = changedKind === 'outdoor' ? 'indoor' : 'outdoor';
  const preferred = components.findIndex((component, index) => index !== changedIndex && normalizeLogisticsKind(component.kind) === preferredKind);
  if (preferred >= 0) return preferred;
  const outdoor = components.findIndex((component, index) => index !== changedIndex && normalizeLogisticsKind(component.kind) === 'outdoor');
  if (outdoor >= 0) return outdoor;
  return components.findIndex((_, index) => index !== changedIndex);
};

const setComponentTotal = (component: OrderLogisticsComponent, total: number) => {
  const quantityPerParent = normalizePositiveInteger(component.quantity_per_parent, 1);
  component.unit_price = roundMoney(Math.max(0, total) / quantityPerParent);
};

export const rebalanceWaybillLine = (line: WaybillProductLine, changedIndex: number | null = null) => {
  const components = line.logistics_components || [];
  if (!components.length) return;
  const targetIndex = chooseBalanceComponentIndex(components, changedIndex);
  if (targetIndex < 0) return;
  const target = components[targetIndex];
  if (!target) return;
  const linePrice = Number(line.price || 0);

  if (changedIndex !== null && components[changedIndex]) {
    const fixedWithoutTargetAndChanged = components.reduce((sum, component, index) => (
      index === targetIndex || index === changedIndex ? sum : sum + componentPerParentTotal(component)
    ), 0);
    const maxChangedTotal = Math.max(0, linePrice - fixedWithoutTargetAndChanged);
    const changed = components[changedIndex]!;
    if (componentPerParentTotal(changed) > maxChangedTotal) setComponentTotal(changed, maxChangedTotal);
  }

  const fixedWithoutTarget = components.reduce((sum, component, index) => (
    index === targetIndex ? sum : sum + componentPerParentTotal(component)
  ), 0);
  setComponentTotal(target, linePrice - fixedWithoutTarget);
};

export const updateWaybillUnitPrice = (line: WaybillProductLine, componentIndex: number, value: unknown) => {
  const component = line.logistics_components?.[componentIndex];
  if (!component) return;
  component.unit_price = normalizePositiveNumber(value, 0);
  rebalanceWaybillLine(line, componentIndex);
};

export const updateWaybillQuantity = (line: WaybillProductLine, componentIndex: number, value: unknown) => {
  const component = line.logistics_components?.[componentIndex];
  if (!component) return;
  component.quantity_per_parent = normalizePositiveInteger(value, 1);
  rebalanceWaybillLine(line, componentIndex);
};

export const addWaybillComponent = (line: WaybillProductLine) => {
  ensureWaybillComponents(line);
  line.logistics_components = [
    ...(line.logistics_components || []),
    { title: '', country: line.product_country || 'Китай', unit: 'шт.', quantity_per_parent: 1, unit_price: 0, kind: 'other' },
  ];
  rebalanceWaybillLine(line, null);
};

export const removeWaybillComponent = (line: WaybillProductLine, componentIndex: number) => {
  if (!line.logistics_components) return;
  line.logistics_components.splice(componentIndex, 1);
  if (!line.logistics_components.length) {
    line.logistics_components = null;
    return;
  }
  rebalanceWaybillLine(line, null);
};

export const lineLogisticsHasMismatch = (line: WaybillProductLine) => (
  Boolean(line.logistics_components?.length) && Math.abs(lineLogisticsPerParentTotal(line) - Number(line.price || 0)) >= 0.01
);
