import { buildApiUrl } from '../utils/yandex-business-feed';

export type YandexBusinessFeedSettings = {
  selection_mode: 'all_published' | 'curated_collections';
  include_services: boolean;
  require_ready_image: boolean;
  require_in_stock: boolean;
};

export type YandexBusinessFeedExclusion = {
  product_id: number;
  product_title: string;
  reason: string;
};

export type YandexBusinessFeedPreview = {
  product_offer_count: number;
  product_picture_count: number;
  service_offer_count: number;
  excluded_product_count: number;
  excluded_products: YandexBusinessFeedExclusion[];
  collection_conflicts: unknown[];
  categories_below_minimum_pictures: unknown[];
  editorial_categories: Array<{ category_id: number; title: string; offer_count: number; picture_count: number }>;
  settings: YandexBusinessFeedSettings;
};

const endpoint = '/api/manager/yandex-business/settings';

const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(buildApiUrl(path), {
    credentials: 'include',
    headers: { Accept: 'application/json', ...(init?.body ? { 'Content-Type': 'application/json' } : {}) },
    ...init,
  });
  if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`);
  return response.json() as Promise<T>;
};

export const getYandexBusinessFeedSettings = () => request<YandexBusinessFeedSettings>(endpoint);

export const previewYandexBusinessFeedSettings = (settings: YandexBusinessFeedSettings) => (
  request<YandexBusinessFeedPreview>(`${endpoint}/preview`, {
    method: 'POST',
    body: JSON.stringify(settings),
  })
);

export const updateYandexBusinessFeedSettings = (settings: YandexBusinessFeedSettings) => (
  request<YandexBusinessFeedSettings>(endpoint, {
    method: 'PUT',
    body: JSON.stringify(settings),
  })
);
