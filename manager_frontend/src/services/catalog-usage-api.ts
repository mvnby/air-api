import { OpenAPI } from '../client/core/OpenAPI';
import type { CancelablePromise } from '../client/core/CancelablePromise';
import { request } from '../client/core/request';

export const CATALOG_USAGE_LAYOUT_VERSION = 'catalog_workspace_v1' as const;

export const CATALOG_USAGE_ACTIONS = [
  'product_open', 'filter_apply', 'filter_zero_results', 'edit_basics',
  'edit_pricing', 'edit_specifications', 'edit_gallery', 'edit_features',
  'bulk_edit', 'gallery_quick_exit', 'media_load',
] as const;
export const CATALOG_USAGE_OUTCOMES = ['success', 'cancelled', 'failed', 'zero_results', 'quick_exit'] as const;
export const CATALOG_USAGE_DURATION_BUCKETS = ['none', 'under_1s', '1_3s', '3_10s', '10_30s', 'over_30s'] as const;

export type CatalogUsageAction = typeof CATALOG_USAGE_ACTIONS[number];
export type CatalogUsageOutcome = typeof CATALOG_USAGE_OUTCOMES[number];
export type CatalogUsageDurationBucket = typeof CATALOG_USAGE_DURATION_BUCKETS[number];
export type CatalogUsageDevice = 'mobile' | 'tablet' | 'desktop';
export type CatalogUsageEvent = {
  device: CatalogUsageDevice;
  action: CatalogUsageAction;
  outcome: CatalogUsageOutcome;
  duration_bucket: CatalogUsageDurationBucket;
};
export type CatalogUsageReportItem = CatalogUsageEvent & {
  day: string;
  layout_version: typeof CATALOG_USAGE_LAYOUT_VERSION;
  count: number;
};
export type CatalogUsageReport = {
  days: number;
  since: string;
  through: string;
  timezone: 'Europe/Minsk';
  items: CatalogUsageReportItem[];
};
export type CatalogUsageReportQuery = {
  days: 7 | 30 | 90;
  layout_version?: typeof CATALOG_USAGE_LAYOUT_VERSION;
  device?: CatalogUsageDevice;
  action?: CatalogUsageAction;
  outcome?: CatalogUsageOutcome;
};

export const catalogUsageApi = {
  record(events: CatalogUsageEvent[]): CancelablePromise<{ accepted: number }> {
    return request(OpenAPI, {
      method: 'POST', url: '/api/manager/catalog-usage/batch', mediaType: 'application/json',
      body: { layout_version: CATALOG_USAGE_LAYOUT_VERSION, pilot_opt_in: true, events },
      errors: { 422: 'Validation Error' },
    });
  },

  daily(query: CatalogUsageReportQuery): CancelablePromise<CatalogUsageReport> {
    return request(OpenAPI, {
      method: 'GET', url: '/api/manager/catalog-usage/daily',
      query,
      errors: { 422: 'Validation Error' },
    });
  },
};
