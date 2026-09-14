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
  site: settings.site,
  services: settings.services,
  version: settings.version,
});

export const storefrontSettingsApi = {
  get: () => call<StorefrontSettings>('GET', '/api/manager/storefront-settings'),
  save: (settings: StorefrontSettings) => call<StorefrontSettings>('PUT', '/api/manager/storefront-settings', savePayload(settings)),
  previewTemplate: () => call<ServiceCatalogTemplatePreview>('GET', '/api/manager/service-catalog/template-preview'),
  cloneTemplate: (expected_fingerprint: string) => call<ServiceCatalogCloneResult>('POST', '/api/manager/service-catalog/clone-template', { expected_fingerprint }),
};
