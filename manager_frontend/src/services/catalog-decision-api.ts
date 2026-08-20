import {
  ManagerCatalogDecisionService,
  type CatalogDecisionListResponse,
  type CatalogDecisionProductResponse,
} from '../client';

export type CatalogDecisionItem = CatalogDecisionProductResponse;
export type CatalogDecisionSort = 'retail_price' | 'purchase_cost' | 'rrc' | 'margin_abs' | 'margin_pct' | 'availability' | 'cooling_power' | 'title';
export type CatalogDecisionFilters = {
  search?: string;
  coolingMinKw?: number;
  coolingMaxKw?: number;
  areaMin?: number;
  areaMax?: number;
  category?: 'household' | 'multi' | 'semi_industrial';
  indoorFormFactor?: 'wall' | 'cassette' | 'duct' | 'floor_ceiling' | 'column';
  isInverter?: boolean;
  wifi?: 'builtin' | 'ready' | 'none';
  availability?: 'in_stock' | 'out_of_stock';
  isPublished?: boolean;
};

export const catalogDecisionApi = {
  list(page: number, limit: number, filters: CatalogDecisionFilters, sort: CatalogDecisionSort, direction: 'asc' | 'desc'): Promise<CatalogDecisionListResponse> {
    return ManagerCatalogDecisionService.listManagerCatalogDecisionProducts(
      page, limit, filters.search, filters.coolingMinKw, filters.coolingMaxKw,
      filters.areaMin, filters.areaMax, filters.category, filters.indoorFormFactor,
      undefined, undefined, filters.isInverter, filters.wifi, filters.availability,
      filters.isPublished, sort, direction,
    );
  },
};
