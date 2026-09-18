import { ManagerCatalogManagementService } from '../client';
import type { CatalogManagementFilters } from '../client';
import type { CatalogDecisionFilters } from './catalog-decision-api';

export type CatalogManagementFilterState = CatalogDecisionFilters & {
  supplierId?: number;
  categoryMissing?: boolean;
  missing?: 'brand' | 'series' | 'image' | 'price';
  featureId?: number;
  hasFeature?: boolean;
  inYandexFeed?: boolean;
};
type CatalogManagementRequestFilters = CatalogManagementFilters & {
  feature_id?: number;
  has_feature?: boolean;
  in_yandex_feed?: boolean;
};
export type CatalogManagementSort = 'recommended' | 'newest' | 'price_asc' | 'price_desc' | 'title';
export const defaultManagementFilters = (): CatalogManagementFilterState => ({ includeOrderable: true });

export const managementFilterPayload = (state: CatalogManagementFilterState): CatalogManagementRequestFilters => ({
  search: state.search?.trim() || undefined,
  brand_ids: state.brandIds ?? [], series_ids: state.seriesIds ?? [], supplier_id: state.supplierId,
  category: state.category, category_missing: Boolean(state.categoryMissing),
  cooling_btu_classes: (state.coolingBtuClasses ?? []) as NonNullable<CatalogManagementFilters['cooling_btu_classes']>,
  cooling_min_kw: state.coolingMinKw, cooling_max_kw: state.coolingMaxKw,
  retail_min_byn: state.retailMinByn, retail_max_byn: state.retailMaxByn,
  area_min: state.areaMin, area_max: state.areaMax,
  indoor_form_factor: state.indoorFormFactor, heating_min: state.heatingMin,
  is_inverter: state.isInverter, wifi: state.wifi,
  availability: state.includeOrderable ? undefined : 'in_stock',
  is_published: state.isPublished, missing: state.missing,
  feature_id: state.featureId,
  has_feature: state.featureId ? state.hasFeature : undefined,
  in_yandex_feed: state.inYandexFeed,
});

export const catalogManagementApi = {
  list: (filters: CatalogManagementFilterState, page = 1, sort: CatalogManagementSort = 'recommended') => ManagerCatalogManagementService.queryManagerCatalog({ filters: managementFilterPayload(filters), page, limit: 40, sort }),
  selection: (filters: CatalogManagementFilterState) => ManagerCatalogManagementService.selectManagerCatalog(managementFilterPayload(filters)),
};
