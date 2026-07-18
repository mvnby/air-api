export type CatalogQualityCategory = 'all' | 'media' | 'identity' | 'specs' | 'commerce' | 'supplier';
export type CatalogQualitySeverity = 'all' | 'critical' | 'warning' | 'info';
export type CatalogQualityViewMode = 'cards' | 'table';
export type CatalogQualitySort = 'priority' | 'score_asc' | 'critical' | 'stock' | 'newest' | 'title' | 'brand' | 'series';
export type CatalogQualityGroup = 'none' | 'brand' | 'series' | 'supplier' | 'equipment_type';

export interface CatalogQualityFilterState {
  q: string;
  equipmentType: string;
  equipmentSubtype: string;
  brandId: string;
  seriesId: string;
  seriesState: '' | 'assigned' | 'missing';
  supplierId: string;
  supplierState: '' | 'mapped' | 'in_stock' | 'unmapped' | 'multiple';
  publication: '' | 'published' | 'hidden';
  availability: '' | 'in_stock' | 'out_of_stock';
  priority: '' | 'high' | 'medium' | 'low';
  scoreMin: string;
  scoreMax: string;
  category: CatalogQualityCategory;
  severity: CatalogQualitySeverity;
  issueCode: string;
  onlyProblems: boolean;
  onlyFixable: boolean;
  sortBy: CatalogQualitySort;
  groupBy: CatalogQualityGroup;
  view: CatalogQualityViewMode;
  page: number;
  limit: 25 | 50 | 100;
}

export interface CatalogQualitySavedView {
  id: string;
  name: string;
  filters: Partial<CatalogQualityFilterState>;
  builtin?: boolean;
}

export const CATALOG_QUALITY_SAVED_VIEWS_KEY = 'manager:catalog-quality:saved-views:v1';

export const createDefaultCatalogQualityState = (): CatalogQualityFilterState => ({
  q: '',
  equipmentType: '',
  equipmentSubtype: '',
  brandId: '',
  seriesId: '',
  seriesState: '',
  supplierId: '',
  supplierState: '',
  publication: '',
  availability: '',
  priority: '',
  scoreMin: '',
  scoreMax: '',
  category: 'all',
  severity: 'all',
  issueCode: '',
  onlyProblems: true,
  onlyFixable: false,
  sortBy: 'priority',
  groupBy: 'none',
  view: 'cards',
  page: 1,
  limit: 50,
});

const enumValue = <T extends string, F extends string>(
  value: string | null,
  allowed: readonly T[],
  fallback: F,
): T | F => allowed.includes(value as T) ? value as T : fallback;

const positiveInteger = (value: string | null, fallback: number) => {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
};

export const parseCatalogQualityState = (search: string): CatalogQualityFilterState => {
  const defaults = createDefaultCatalogQualityState();
  const params = new URLSearchParams(search);
  const rawLimit = positiveInteger(params.get('limit'), defaults.limit);
  return {
    q: params.get('q') ?? defaults.q,
    equipmentType: params.get('equipmentType') ?? defaults.equipmentType,
    equipmentSubtype: params.get('equipmentSubtype') ?? defaults.equipmentSubtype,
    brandId: params.get('brandId') ?? defaults.brandId,
    seriesId: params.get('seriesId') ?? defaults.seriesId,
    seriesState: enumValue(params.get('seriesState'), ['assigned', 'missing'] as const, defaults.seriesState),
    supplierId: params.get('supplierId') ?? defaults.supplierId,
    supplierState: enumValue(params.get('supplierState'), ['mapped', 'in_stock', 'unmapped', 'multiple'] as const, defaults.supplierState),
    publication: enumValue(params.get('publication'), ['published', 'hidden'] as const, defaults.publication),
    availability: enumValue(params.get('availability'), ['in_stock', 'out_of_stock'] as const, defaults.availability),
    priority: enumValue(params.get('priority'), ['high', 'medium', 'low'] as const, defaults.priority),
    scoreMin: params.get('scoreMin') ?? defaults.scoreMin,
    scoreMax: params.get('scoreMax') ?? defaults.scoreMax,
    category: enumValue(params.get('category'), ['all', 'media', 'identity', 'specs', 'commerce', 'supplier'] as const, defaults.category),
    severity: enumValue(params.get('severity'), ['all', 'critical', 'warning', 'info'] as const, defaults.severity),
    issueCode: params.get('issueCode') ?? defaults.issueCode,
    onlyProblems: params.get('onlyProblems') !== 'false',
    onlyFixable: params.get('onlyFixable') === 'true',
    sortBy: enumValue(params.get('sortBy'), ['priority', 'score_asc', 'critical', 'stock', 'newest', 'title', 'brand', 'series'] as const, defaults.sortBy),
    groupBy: enumValue(params.get('groupBy'), ['none', 'brand', 'series', 'supplier', 'equipment_type'] as const, defaults.groupBy),
    view: enumValue(params.get('view'), ['cards', 'table'] as const, defaults.view),
    page: positiveInteger(params.get('page'), defaults.page),
    limit: ([25, 50, 100].includes(rawLimit) ? rawLimit : defaults.limit) as 25 | 50 | 100,
  };
};

export const serializeCatalogQualityState = (state: CatalogQualityFilterState) => {
  const defaults = createDefaultCatalogQualityState();
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(state)) {
    const defaultValue = defaults[key as keyof CatalogQualityFilterState];
    if (value === defaultValue || value === '') continue;
    params.set(key, String(value));
  }
  const query = params.toString();
  return query ? `?${query}` : '';
};

export const applyCatalogQualityView = (
  current: CatalogQualityFilterState,
  filters: Partial<CatalogQualityFilterState>,
): CatalogQualityFilterState => ({
  ...createDefaultCatalogQualityState(),
  view: current.view,
  limit: current.limit,
  ...filters,
  page: 1,
});

export const catalogQualityBuiltinViews: CatalogQualitySavedView[] = [
  {
    id: 'critical-published',
    name: 'Критичные на сайте',
    builtin: true,
    filters: { publication: 'published', severity: 'critical', onlyProblems: true, sortBy: 'critical' },
  },
  {
    id: 'stock-media',
    name: 'В наличии: плохие фото',
    builtin: true,
    filters: { availability: 'in_stock', category: 'media', onlyProblems: true, sortBy: 'priority' },
  },
  {
    id: 'household-no-series',
    name: 'Бытовые без серии',
    builtin: true,
    filters: { equipmentType: 'cat-household', seriesState: 'missing', onlyProblems: false, sortBy: 'brand' },
  },
  {
    id: 'supplier-unmapped',
    name: 'Без маппинга прайсов',
    builtin: true,
    filters: { supplierState: 'unmapped', category: 'supplier', onlyProblems: true, sortBy: 'priority' },
  },
];

export const readCatalogQualitySavedViews = (storage: Pick<Storage, 'getItem'>): CatalogQualitySavedView[] => {
  try {
    const raw = storage.getItem(CATALOG_QUALITY_SAVED_VIEWS_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((item) => item?.id && item?.name && item?.filters) : [];
  } catch {
    return [];
  }
};

export const writeCatalogQualitySavedViews = (
  storage: Pick<Storage, 'setItem'>,
  views: CatalogQualitySavedView[],
) => storage.setItem(CATALOG_QUALITY_SAVED_VIEWS_KEY, JSON.stringify(views));
