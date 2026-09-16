import { defaultCatalogDecisionFilters, type CatalogDecisionFilters, type CatalogDecisionSort } from './catalog-decision-api';

export type CatalogDecisionQuery = {
  filters: CatalogDecisionFilters;
  sort: CatalogDecisionSort;
  direction: 'asc' | 'desc';
  page: number;
};
const sorts: CatalogDecisionSort[] = ['title', 'retail_price', 'purchase_cost', 'rrc', 'margin_abs', 'margin_pct', 'availability', 'cooling_power'];
const numericKeys = ['retailMinByn', 'retailMaxByn', 'coolingMinKw', 'coolingMaxKw'] as const;
const listKeys = ['coolingBtuClasses', 'brandIds', 'seriesIds'] as const;
const queryKeys = ['q', 'form', 'wifi', 'inverter', 'orderable', 'heating', 'sort', 'direction', 'page', ...numericKeys, ...listKeys];
const forms = ['wall', 'cassette', 'duct', 'floor_ceiling', 'column', 'console'];
const powers = [7, 9, 12, 18, 24, 30, 36, 42, 60];

/** Only catalog criteria are read; order/proposal navigation parameters stay untouched. */
export const readCatalogDecisionQuery = (search: string): CatalogDecisionQuery => {
  const params = new URLSearchParams(search);
  const filters = defaultCatalogDecisionFilters();
  const q = params.get('q')?.trim().slice(0, 200);
  if (q) filters.search = q;
  const form = params.get('form');
  if (form && forms.includes(form)) filters.indoorFormFactor = form as CatalogDecisionFilters['indoorFormFactor'];
  const wifi = params.get('wifi');
  if (wifi === 'builtin' || wifi === 'ready' || wifi === 'none') filters.wifi = wifi;
  if (params.get('inverter') === '1') filters.isInverter = true;
  if (params.get('orderable') === '1') filters.includeOrderable = true;
  const heating = Number(params.get('heating'));
  if (heating === -20 || heating === -25 || heating === -30) filters.heatingMin = heating;
  for (const key of numericKeys) {
    const raw = params.get(key);
    const value = Number(raw);
    if (raw && Number.isFinite(value) && value >= 0) filters[key] = value;
  }
  for (const [min, max] of [['retailMinByn', 'retailMaxByn'], ['coolingMinKw', 'coolingMaxKw']] as const) {
    if (filters[min] !== undefined && filters[max] !== undefined && filters[min]! > filters[max]!) {
      delete filters[min]; delete filters[max];
    }
  }
  for (const key of listKeys) {
    const values = [...new Set((params.get(key) || '').split(',').map(Number))]
      .filter(value => Number.isSafeInteger(value) && value > 0 && (key !== 'coolingBtuClasses' || powers.includes(value)))
      .slice(0, 100);
    if (values.length) filters[key] = values;
  }
  if (!filters.brandIds?.length) delete filters.seriesIds;
  const sort = params.get('sort') as CatalogDecisionSort;
  const page = Number(params.get('page'));
  return {
    filters,
    sort: sorts.includes(sort) ? sort : 'title',
    direction: params.get('direction') === 'desc' ? 'desc' : 'asc',
    page: Number.isSafeInteger(page) && page > 0 ? page : 1,
  };
};

export const writeCatalogDecisionQuery = (search: string, state: CatalogDecisionQuery): string => {
  const params = new URLSearchParams(search);
  queryKeys.forEach(key => params.delete(key));
  const { filters, sort, direction, page } = state;
  if (filters.search?.trim()) params.set('q', filters.search.trim());
  if (filters.indoorFormFactor) params.set('form', filters.indoorFormFactor);
  if (filters.wifi) params.set('wifi', filters.wifi);
  if (filters.isInverter) params.set('inverter', '1');
  if (filters.includeOrderable) params.set('orderable', '1');
  if (filters.heatingMin) params.set('heating', String(filters.heatingMin));
  for (const key of numericKeys) if (filters[key] !== undefined) params.set(key, String(filters[key]));
  for (const key of listKeys) if (filters[key]?.length) params.set(key, filters[key]!.join(','));
  if (sort !== 'title') params.set('sort', sort);
  if (direction !== 'asc') params.set('direction', direction);
  if (page > 1) params.set('page', String(page));
  const query = params.toString();
  return query ? `?${query}` : '';
};

export type CatalogDecisionChip = { key: string; label: string; remove: () => CatalogDecisionFilters };
export const catalogDecisionChips = (
  filters: CatalogDecisionFilters,
  brands: Array<{ id: number; title: string }>,
  series: Array<{ id: number; title: string; brandId?: number | null }>,
): CatalogDecisionChip[] => {
  const chips: CatalogDecisionChip[] = [];
  const add = (key: keyof CatalogDecisionFilters, label: string) => chips.push({ key, label, remove: () => ({ ...filters, [key]: undefined }) });
  const formLabels: Record<string, string> = { wall: 'Настенный', cassette: 'Кассетный', duct: 'Канальный', floor_ceiling: 'Напольно-потолочный', console: 'Консольный', column: 'Колонный' };
  if (filters.search) add('search', `Поиск: ${filters.search}`);
  if (filters.indoorFormFactor) add('indoorFormFactor', formLabels[filters.indoorFormFactor]!);
  if (filters.isInverter) add('isInverter', 'Только инвертор');
  if (filters.wifi) add('wifi', `Wi-Fi: ${filters.wifi === 'builtin' ? 'встроенный' : filters.wifi === 'ready' ? 'опция' : 'нет'}`);
  if (filters.heatingMin) add('heatingMin', `Обогрев до ${filters.heatingMin} °C`);
  if (filters.retailMinByn !== undefined) add('retailMinByn', `Цена от ${filters.retailMinByn.toLocaleString('ru-BY')} BYN`);
  if (filters.retailMaxByn !== undefined) add('retailMaxByn', `Цена до ${filters.retailMaxByn.toLocaleString('ru-BY')} BYN`);
  if (filters.coolingMinKw !== undefined) add('coolingMinKw', `От ${filters.coolingMinKw} кВт`);
  if (filters.coolingMaxKw !== undefined) add('coolingMaxKw', `До ${filters.coolingMaxKw} кВт`);
  if (!filters.includeOrderable) chips.push({ key: 'stock', label: 'В наличии', remove: () => ({ ...filters, includeOrderable: true }) });
  for (const key of listKeys) {
    for (const id of filters[key] || []) {
      const label = key === 'coolingBtuClasses' ? `${id} тыс. БТЕ/ч`
        : (key === 'brandIds' ? brands : series).find(item => item.id === id)?.title || `${key === 'brandIds' ? 'Бренд' : 'Серия'} #${id}`;
      chips.push({ key: `${key}-${id}`, label, remove: () => {
        const next = { ...filters, [key]: filters[key]?.filter(value => value !== id) };
        if (key === 'brandIds') next.seriesIds = filters.seriesIds?.filter(value => {
          const owner = series.find(item => item.id === value)?.brandId;
          return owner != null && next.brandIds?.includes(owner);
        });
        return next;
      } });
    }
  }
  return chips;
};
