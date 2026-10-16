import { ref } from 'vue';
import { managerCompaniesApi, type CompanyChoice, type CompanyChoices } from './manager-companies';
import { runGuardedNavigation } from './unsaved-navigation-guard';

import {
  ManagerService,
  OpenAPI,
  type ManagerAuthStatusResponse,
  type ManagerStorefrontResponse,
  type OpenAPIConfig,
} from '../client';
import type { ApiRequestOptions } from '../client/core/ApiRequestOptions';

export const MANAGER_STOREFRONT_HEADER = 'X-MVN-Manager-Storefront';
export const MANAGER_TENANT_HEADER = 'X-MVN-Manager-Tenant';
const STORAGE_KEY_PREFIX = 'mvn_manager_context_v2';
const STOREFRONT_SLUG_PATTERN = /^[a-z0-9][a-z0-9-]{0,63}$/;

type ReloadPage = () => void;
type StorefrontStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
type HeaderResolver = NonNullable<OpenAPIConfig['HEADERS']>;

const normalizedSlug = (value: unknown): string | null => {
  const slug = typeof value === 'string' ? value.trim().toLowerCase() : '';
  return STOREFRONT_SLUG_PATTERN.test(slug) ? slug : null;
};

const requestPath = (url: string): string => {
  try {
    return new URL(url, 'https://manager.invalid').pathname;
  } catch {
    return url.split(/[?#]/, 1)[0] || '';
  }
};

export const isManagerApiRequest = (url: string): boolean => {
  const path = requestPath(url);
  const isManagerPath = path === '/api/manager' || path.startsWith('/api/manager/');
  const isDedicatedWorkerPath = (
    path === '/api/manager/media/worker'
    || path.startsWith('/api/manager/media/worker/')
  );
  const personal = /^\/api\/manager\/account(?:\/|$)/.test(path);
  return isManagerPath && !isDedicatedWorkerPath && !personal;
};

export const managerContextStorageKey = (
  auth: Pick<ManagerAuthStatusResponse, 'tenant_id' | 'staff_user_id' | 'username'>,
): string => {
  const userKey = auth.staff_user_id
    ? `staff-${auth.staff_user_id}`
    : `user-${encodeURIComponent(auth.username.trim().toLowerCase())}`;
  return `${STORAGE_KEY_PREFIX}:${userKey}`;
};

// Business-view cache keys must retain company scope even though the tab selector is person-scoped.
export const managerStorefrontStorageKey = (auth: Pick<ManagerAuthStatusResponse, 'tenant_id' | 'staff_user_id' | 'username'>): string => {
  const userKey = auth.staff_user_id ? `staff-${auth.staff_user_id}` : `user-${encodeURIComponent(auth.username.trim().toLowerCase())}`;
  return `mvn_manager_storefront_v1:${auth.tenant_id}:${userKey}`;
};

const browserStorage = (): StorefrontStorage | null => {
  try {
    return typeof window === 'undefined' ? null : window.sessionStorage;
  } catch {
    return null;
  }
};

const browserReload: ReloadPage = () => window.location.reload();

const storageGet = (storage: StorefrontStorage | null, key: string): string | null => {
  try {
    return storage?.getItem(key) ?? null;
  } catch {
    return null;
  }
};

const storageSet = (storage: StorefrontStorage | null, key: string, value: string): boolean => {
  if (!storage) return false;
  try {
    storage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
};

const storageRemove = (storage: StorefrontStorage | null, key: string): void => {
  try {
    storage?.removeItem(key);
  } catch {
    // Ignore unavailable browser storage and keep the request scope fail-safe.
  }
};

export class ManagerContextError extends Error {
  constructor(message: string) { super(message); this.name = 'ManagerContextError'; }
}

export class ManagerStorefrontSelection {
  readonly companies = ref<CompanyChoice[]>([]);
  readonly selectedTenantId = ref<number | null>(null);
  readonly storefronts = ref<ManagerStorefrontResponse[]>([]);
  readonly selectedSlug = ref<string | null>(null);
  readonly loading = ref(false);
  readonly switching = ref(false);
  readonly error = ref('');
  private identity: Pick<ManagerAuthStatusResponse, 'tenant_id' | 'staff_user_id' | 'username'> | null = null;
  private readonly storage: () => StorefrontStorage | null;
  private readonly reloadPage: ReloadPage;
  constructor(storage: () => StorefrontStorage | null = browserStorage, reloadPage: ReloadPage = browserReload) {
    this.storage = storage; this.reloadPage = reloadPage;
  }
  prepareAuthentication(): void {
    this.identity = null; this.companies.value = []; this.selectedTenantId.value = null;
    this.storefronts.value = []; this.selectedSlug.value = null;
    this.loading.value = false; this.switching.value = false; this.error.value = '';
  }
  async initializeContext(
    loadCompanies: (page?: number) => PromiseLike<CompanyChoices> = managerCompaniesApi.choices,
    loadSites: () => PromiseLike<{ items?: ManagerStorefrontResponse[] }> = () => ManagerService.listManagerStorefronts(),
    search = typeof window === 'undefined' ? '' : window.location.search,
  ): Promise<void> {
    this.loading.value = true;
    try {
      const response = await loadCompanies(1);
      const companies = [...response.items];
      for (let page = 2; companies.length < response.total; page++) {
        const more = await loadCompanies(page);
        if (!more.items.length) break;
        companies.push(...more.items);
      }
      this.companies.value = companies;
      this.identity = { staff_user_id: response.staff_user_id, username: response.username, tenant_id: response.default_tenant_id ?? 0 };
      const query = new URLSearchParams(search);
      const explicitCompany = query.has('company');
      const explicitSite = query.has('site');
      const rawCompany = query.get('company');
      const rawSite = query.get('site');
      if (query.getAll('company').length > 1 || query.getAll('site').length > 1) throw new ManagerContextError('Ссылка содержит несколько компаний или сайтов');
      const key = managerContextStorageKey(this.identity);
      let stored: { tenant_id?: number; site?: string } = {};
      try { const value = JSON.parse(storageGet(this.storage(), key) || '{}'); stored = value && typeof value === 'object' ? value : {}; } catch { storageRemove(this.storage(), key); }
      if (explicitCompany && (!/^[1-9]\d*$/.test(rawCompany || '') || !Number.isSafeInteger(Number(rawCompany)))) throw new ManagerContextError('Некорректная компания в ссылке');
      if (explicitSite && (!normalizedSlug(rawSite) || rawSite !== normalizedSlug(rawSite))) throw new ManagerContextError('Некорректный сайт в ссылке');
      const requestedId = explicitCompany ? Number(rawCompany) : stored.tenant_id;
      const selected = companies.find(company => company.tenant_id === requestedId)
        ?? (!explicitCompany ? companies.find(company => company.tenant_id === response.default_tenant_id) ?? companies[0] : undefined);
      if (!selected) throw new ManagerContextError(companies.length ? 'Нет доступа к компании из ссылки' : 'У вас пока нет доступа к компании. Откройте приглашение от владельца.');
      this.selectedTenantId.value = selected.tenant_id;
      // Only a validated company is sent to business endpoints. Views stay unmounted until sites and /me succeed.
      const sites = await loadSites();
      this.storefronts.value = (sites.items ?? []).map(site => ({ ...site, is_current: false }));
      const requestedSite = explicitSite ? rawSite : stored.tenant_id === selected.tenant_id ? normalizedSlug(stored.site) : null;
      const current = this.storefronts.value.find(site => site.slug === requestedSite)
        ?? (!explicitSite ? this.storefronts.value.find(site => site.slug === selected.default_storefront_slug)
          ?? this.storefronts.value.find(site => site.is_default) ?? this.storefronts.value[0] : undefined);
      if (!current) throw new ManagerContextError(explicitSite ? 'Нет доступа к сайту из ссылки' : 'У компании нет доступных сайтов');
      this.selectedSlug.value = current.slug;
      this.storefronts.value = this.storefronts.value.map(site => ({ ...site, is_current: site.slug === current.slug }));
      storageSet(this.storage(), key, JSON.stringify({ tenant_id: selected.tenant_id, site: current.slug }));
    } catch (error) {
      this.selectedTenantId.value = null; this.selectedSlug.value = null;
      if ((error as { status?: number })?.status === 403) throw new ManagerContextError('Нет доступа к выбранной компании или сайту');
      throw error;
    } finally { this.loading.value = false; }
  }
  private async switchContext(tenantId: number, site: string | null): Promise<boolean> {
    if (!this.identity || this.switching.value) return false;
    let saved = false;
    await runGuardedNavigation(() => {
      if (!storageSet(this.storage(), managerContextStorageKey(this.identity!), JSON.stringify({ tenant_id: tenantId, site }))) {
        this.error.value = 'Браузер не разрешил сохранить выбранную компанию и сайт'; return;
      }
      saved = true; this.switching.value = true;
      if (typeof window !== 'undefined') {
        const url = new URL(window.location.href); url.searchParams.delete('company'); url.searchParams.delete('site');
        window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`);
      }
      // Keep the old live headers until the new page has bootstrapped successfully.
      this.reloadPage();
    });
    return saved;
  }
  switchTo(rawSlug: string): Promise<boolean> {
    const slug = normalizedSlug(rawSlug);
    if (!slug || !this.selectedTenantId.value || slug === this.selectedSlug.value || !this.storefronts.value.some(site => site.slug === slug)) return Promise.resolve(false);
    return this.switchContext(this.selectedTenantId.value, slug);
  }
  switchCompany(tenantId: number): Promise<boolean> {
    const company = this.companies.value.find(item => item.tenant_id === tenantId);
    if (!company || company.tenant_id === this.selectedTenantId.value) return Promise.resolve(false);
    return this.switchContext(company.tenant_id, company.default_storefront_slug);
  }
}

export const managerStorefrontSelection = new ManagerStorefrontSelection();

export const getManagerStorefrontRequestHeaders = (
  url: string,
  slug = managerStorefrontSelection.selectedSlug.value,
): Record<string, string> => {
  const selectedSlug = normalizedSlug(slug);
  if (!isManagerApiRequest(url)) return {};
  const tenantId = managerStorefrontSelection.selectedTenantId.value;
  return { ...(selectedSlug ? { [MANAGER_STOREFRONT_HEADER]: selectedSlug } : {}), ...(tenantId ? { [MANAGER_TENANT_HEADER]: String(tenantId) } : {}) };
};

const resolveExistingHeaders = async (
  headers: HeaderResolver | undefined,
  options: ApiRequestOptions,
): Promise<Record<string, string>> => {
  if (!headers) return {};
  if (typeof headers === 'function') return await headers(options);
  return headers;
};

export const createManagerStorefrontHeaderResolver = (
  existingHeaders?: HeaderResolver,
): HeaderResolver => async (options) => ({
  ...await resolveExistingHeaders(existingHeaders, options),
  ...getManagerStorefrontRequestHeaders(options.url),
});

const installedConfigs = new WeakSet<object>();

export const installManagerStorefrontHeaderResolver = (
  config: OpenAPIConfig = OpenAPI,
): void => {
  if (installedConfigs.has(config)) return;
  config.HEADERS = createManagerStorefrontHeaderResolver(config.HEADERS);
  installedConfigs.add(config);
};

type FetchHost = { fetch: typeof fetch };
type ManagerUnauthorizedContext = Readonly<{
  url: string;
  response: Response;
}>;
type ManagerUnauthorizedCallback = (
  context: ManagerUnauthorizedContext,
) => unknown | PromiseLike<unknown>;
const installedFetchHosts = new WeakSet<object>();

export const installManagerStorefrontFetchScope = (
  host: FetchHost = window,
  onUnauthorized?: ManagerUnauthorizedCallback,
): void => {
  if (installedFetchHosts.has(host)) return;
  const originalFetch = host.fetch.bind(host);
  host.fetch = async (input, init) => {
    const url = typeof input === 'string'
      ? input
      : input instanceof URL
        ? input.href
        : input.url;
    const isManagerRequest = isManagerApiRequest(url);
    const scopedHeaders = getManagerStorefrontRequestHeaders(url);
    let requestInit = init;
    if (Object.keys(scopedHeaders).length) {
      const headers = new Headers(
        init?.headers ?? (input instanceof Request ? input.headers : undefined),
      );
      for (const [name, value] of Object.entries(scopedHeaders)) {
        if (!headers.has(name)) headers.set(name, value);
      }
      requestInit = { ...init, headers };
    }

    const response = await originalFetch(input, requestInit);
    if (isManagerRequest && response.status === 401 && onUnauthorized) {
      try {
        void Promise.resolve(onUnauthorized({ url, response })).catch(() => undefined);
      } catch {
        // Session recovery must never replace the original HTTP response.
      }
    }
    return response;
  };
  installedFetchHosts.add(host);
};
