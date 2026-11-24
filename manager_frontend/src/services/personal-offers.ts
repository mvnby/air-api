import { OpenAPI } from '../client';
import { request } from '../client/core/request';

export const personalOffersPath = '/manager/personal-offers';
export type InstallationMode = 'none' | 'unknown' | 'fixed';
export type OfferSelectionMode = 'choice' | 'package';
export type Installation = { mode: InstallationMode; price_byn: string | null; description: string | null };
export type DraftOption = { product_id: number; price_byn: string; note: string | null };
export type DraftRoom = {
  title: string | null;
  selection_mode?: OfferSelectionMode;
  show_total?: boolean;
  installation: Installation;
  options: DraftOption[];
};
export type Draft = { order_id: number | null; expires_at: string; rooms: DraftRoom[] };

export type PersonalOffer = Draft & {
  id: number;
  version: number;
  published: { url: string; expires_at: string } | null;
};

export type PublicOption = {
  title: string;
  slug: string | null;
  main_image: string | null;
  price_byn: string;
  original_price_byn: string | null;
  total_price_byn: string | null;
  note: string | null;
  cooling_power_kw: number | null;
  noise_indoor_min_db: number | null;
  is_inverter: boolean | null;
  wifi: 'builtin' | 'ready' | 'none' | null;
};

export type PersonalOfferPreview = {
  expires_at: string;
  rooms: Array<{
    title: string;
    selection_mode?: OfferSelectionMode;
    equipment_total_byn?: string | null;
    total_with_installation_byn?: string | null;
    installation: Installation;
    options: PublicOption[];
  }>;
};

const apiPath = '/api/manager/personal-offers';
const offerUrl = (id: number) => apiPath + '/' + id;
const writeOffer = <T>(method: 'POST' | 'PUT', url: string, body?: unknown) =>
  request<T>(OpenAPI, { method, url, body, mediaType: 'application/json' });

export const personalOffersApi = {
  list: (orderId?: number, beforeId?: number) => request<{ items: PersonalOffer[]; has_more: boolean }>(OpenAPI, {
    method: 'GET', url: apiPath, query: { order_id: orderId, before_id: beforeId, limit: 20 },
  }),
  get: (id: number) => request<PersonalOffer>(OpenAPI, { method: 'GET', url: offerUrl(id) }),
  create: (draft: Draft) => writeOffer<PersonalOffer>('POST', apiPath, draft),
  update: (id: number, draft: Draft, version: number) => writeOffer<PersonalOffer>('PUT', offerUrl(id), { ...draft, expected_version: version }),
  preview: (id: number) => writeOffer<PersonalOfferPreview>('POST', offerUrl(id) + '/preview'),
  publish: (id: number, version: number, requestId: string) => writeOffer<PersonalOffer>('POST', offerUrl(id) + '/publish', { expected_version: version, request_id: requestId }),
  revoke: (id: number, version: number) => writeOffer<PersonalOffer>('POST', offerUrl(id) + '/revoke', { expected_version: version }),
};

export const newPersonalOfferRoom = (): DraftRoom => ({
  title: null,
  selection_mode: 'choice',
  show_total: false,
  installation: { mode: 'none', price_byn: null, description: null },
  options: [],
});

export function personalOfferRoomName(index: number, count: number, mode?: OfferSelectionMode) {
  if (mode === 'package') return count > 1 ? 'Комплект ' + (index + 1) : 'Комплект оборудования';
  return count > 1 ? 'Помещение ' + (index + 1) : 'Подбор кондиционера';
}

export function personalOfferSelectionUrl(productIds: number[], orderId?: number) {
  const query = new URLSearchParams(productIds.length ? { products: productIds.join(',') } : { new: '1' });
  if (orderId) query.set('orderId', String(orderId));
  return personalOffersPath + '?' + query;
}

export function positiveId(value: string | null) {
  const number = Number(value);
  return Number.isSafeInteger(number) && number > 0 ? number : undefined;
}

export function personalOfferMoney(value: string | null) {
  const amount = value?.trim().replace(',', '.') ?? '';
  return /^\d+(\.\d{1,2})?$/.test(amount) ? amount : null;
}

export function localOfferDate(date: Date) {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

export const formatOfferDate = (date: string) =>
  new Intl.DateTimeFormat('ru-BY', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(date));

export const formatOfferMoney = (value: string) =>
  new Intl.NumberFormat('ru-BY', { style: 'currency', currency: 'BYN', maximumFractionDigits: 2 }).format(Number(value));
