import { OpenAPI, type ManagerAuthStatusResponse, type ManagerStorefrontListResponse, type InstallerWorkDetail, type InstallerWorksResponse } from '../client';
import { request } from '../client/core/request';

export type { InstallerCollection, InstallerEquipment, InstallerWorkSummary, InstallerWorkDetail, InstallerWorksResponse } from '../client';
export type InstallerWorkBucket = 'today' | 'upcoming' | 'unscheduled' | 'all';
// Only these allowlisted installer projections enter the personal work screen.
export const installerWorkspaceApi = {
  me: () => request<ManagerAuthStatusResponse>(OpenAPI, { method: 'GET', url: '/api/installer/me' }),
  storefronts: () => request<ManagerStorefrontListResponse>(OpenAPI, { method: 'GET', url: '/api/installer/storefronts' }),
  works: (page = 1, bucket: InstallerWorkBucket = 'all') => request<InstallerWorksResponse>(OpenAPI, { method: 'GET', url: '/api/installer/works', query: { page, limit: 30, bucket } }),
  detail: (id: number) => request<InstallerWorkDetail>(OpenAPI, { method: 'GET', url: `/api/installer/works/${id}` }),
};

export const loadInstallerMaterial = async (url: string): Promise<Blob> => {
  if (!/^\/api\/installer\/works\/[1-9]\d*\/materials\/[1-9]\d*\/content$/.test(url)) throw new Error('Недоступный адрес материала');
  const options = { method: 'GET' as const, url };
  const configured = typeof OpenAPI.HEADERS === 'function' ? await OpenAPI.HEADERS(options) : OpenAPI.HEADERS;
  const token = typeof OpenAPI.TOKEN === 'function' ? await OpenAPI.TOKEN(options) : OpenAPI.TOKEN;
  const headers = new Headers(configured);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(`${OpenAPI.BASE}${url}`, { headers, credentials: OpenAPI.WITH_CREDENTIALS ? OpenAPI.CREDENTIALS : 'same-origin' });
  if (!response.ok) throw new Error(`Материал недоступен (${response.status})`);
  const mime = (response.headers.get('content-type') || '').split(';')[0] ?? '';
  if (!['application/pdf', 'image/jpeg', 'image/png', 'image/webp'].includes(mime)) throw new Error('Формат материала не поддерживается');
  return response.blob();
};
