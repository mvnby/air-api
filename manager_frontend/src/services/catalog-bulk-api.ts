import type { CancelablePromise } from '../client/core/CancelablePromise';
import { OpenAPI } from '../client/core/OpenAPI';
import { request } from '../client/core/request';

export type CatalogBulkKind = 'relations' | 'specs' | 'features' | 'publication' | 'category';
export type CatalogBulkChange = {
  kind: CatalogBulkKind;
  brand_id?: number | null;
  series_id?: number | null;
  specs?: Record<string, string>;
  spec_mode?: 'set' | 'fill_empty' | 'remove';
  feature_ids?: number[];
  feature_mode?: 'add' | 'hide' | 'inherit';
  is_published?: boolean;
  category?: 'cat-household' | 'cat-multi' | 'cat-industrial' | null;
};
export type CatalogBulkPreviewItem = {
  product_id: number;
  title: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  changed: boolean;
};
export type CatalogBulkPreview = {
  token: string;
  items: CatalogBulkPreviewItem[];
  changed_count: number;
  expires_in_seconds: number;
};
export type CatalogBulkApplyResult = { updated: number; product_ids: number[] };

export const catalogBulkApi = {
  preview(productIds: number[], change: CatalogBulkChange): CancelablePromise<CatalogBulkPreview> {
    return request(OpenAPI, {
      method: 'POST', url: '/api/manager/catalog-management/bulk/preview', mediaType: 'application/json',
      body: { product_ids: productIds, change },
      errors: { 409: 'Conflict', 422: 'Validation Error' },
    });
  },
  apply(token: string): CancelablePromise<CatalogBulkApplyResult> {
    return request(OpenAPI, {
      method: 'POST', url: '/api/manager/catalog-management/bulk/apply', mediaType: 'application/json',
      body: { token }, errors: { 409: 'Conflict', 422: 'Validation Error' },
    });
  },
};
