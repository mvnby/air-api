import { OpenAPI } from '../client';

export const YANDEX_BUSINESS_PUBLIC_FEED_PATH = '/api/v1/feeds/yandex-business.yml';
export const YANDEX_BUSINESS_MANAGER_DOWNLOAD_PATH =
  '/api/manager/yandex-business/price-list.yml';

export const buildApiUrl = (path: string): string => {
  const runtimeOrigin = window.location.origin;
  const configuredBase = String(OpenAPI.BASE || '').trim();
  const apiOrigin = configuredBase
    ? new URL(configuredBase, runtimeOrigin).origin
    : runtimeOrigin;
  return new URL(path, apiOrigin).toString();
};
