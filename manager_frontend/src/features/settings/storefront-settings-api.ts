import { OpenAPI } from '../../client';
import { ApiError } from '../../client/core/ApiError';
import { request } from '../../client/core/request';

export type StorefrontSiteSettings = {
  display_name: string;
  city: string;
  phone: string;
  email: string;
  address: string;
  work_hours: string;
  support_telegram_url: string;
  logo_asset_id: number | null;
  compact_logo_asset_id: number | null;
  logo_url?: string | null;
  compact_logo_url?: string | null;
};

export type StorefrontServiceSettings = {
  key: 'installation' | 'pre_install' | 'dismantling' | 'maintenance' | 'repair';
  title: string;
  description: string;
  enabled: boolean;
};

export type StorefrontSettings = {
  site: StorefrontSiteSettings;
  services: StorefrontServiceSettings[];
  version: number;
  updated_at: string | null;
};

export type ServiceCatalogTemplatePreview = {
  source_counts: { services: number; tariffs: number; tariff_rules: number; installation_rates: number };
  source_fingerprint: string;
  target_counts: { services: number; tariffs: number; tariff_rules: number; installation_rates: number };
  can_clone: boolean;
};

export type ServiceCatalogCloneResult = {
  status: 'cloned' | 'already_cloned';
  cloned_counts: ServiceCatalogTemplatePreview['source_counts'];
  source_fingerprint: string;
};

export class StorefrontSettingsApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'StorefrontSettingsApiError';
    this.status = status;
  }
}

const call = async <T>(method: 'GET' | 'PUT' | 'POST', url: string, body?: unknown): Promise<T> => {
  try {
    return await request<T>(OpenAPI, { method, url, body, mediaType: body === undefined ? undefined : 'application/json', errors: { 409: 'Conflict' } });
  } catch (error) {
    if (error instanceof ApiError) {
      const detail = error.body && typeof error.body === 'object' ? error.body.detail : null;
      throw new StorefrontSettingsApiError(typeof detail === 'string' ? detail : error.message, error.status);
    }
    throw error;
  }
};

const savePayload = (settings: StorefrontSettings) => ({
  site: Object.fromEntries(Object.entries(settings.site).filter(([key]) => key !== 'logo_url' && key !== 'compact_logo_url')),
  services: settings.services,
  version: settings.version,
});

export const storefrontSettingsApi = {
  get: () => call<StorefrontSettings>('GET', '/api/manager/storefront-settings'),
  save: (settings: StorefrontSettings) => call<StorefrontSettings>('PUT', '/api/manager/storefront-settings', savePayload(settings)),
  brand: () => call<{ display_name: string; logo_url: string | null; compact_logo_url: string | null }>('GET', '/api/manager/storefront-settings/brand'),
  uploadLogo: async (file: File) => {
    const result = await request<{ items: Array<{ id: number; url: string }> }>(OpenAPI, {
      method: 'POST', url: '/api/manager/storefront-settings/logo', formData: { file }, mediaType: 'multipart/form-data',
    });
    if (!result.items[0]?.id || !result.items[0]?.url) throw new Error('Загрузка завершилась без логотипа');
    return result.items[0];
  },
  previewTemplate: () => call<ServiceCatalogTemplatePreview>('GET', '/api/manager/service-catalog/template-preview'),
  cloneTemplate: (expected_fingerprint: string) => call<ServiceCatalogCloneResult>('POST', '/api/manager/service-catalog/clone-template', { expected_fingerprint }),
};
