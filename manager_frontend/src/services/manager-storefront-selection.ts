import { ref } from 'vue';

import {
  ManagerService,
  OpenAPI,
  type ManagerAuthStatusResponse,
  type ManagerStorefrontListResponse,
  type ManagerStorefrontResponse,
  type OpenAPIConfig,
} from '../client';
import type { ApiRequestOptions } from '../client/core/ApiRequestOptions';

export const MANAGER_STOREFRONT_HEADER = 'X-MVN-Manager-Storefront';
const STORAGE_KEY_PREFIX = 'mvn_manager_storefront_v1';
const STOREFRONT_SLUG_PATTERN = /^[a-z0-9][a-z0-9-]{0,63}$/;

type StorefrontListLoader = () => PromiseLike<ManagerStorefrontListResponse>;
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
  return isManagerPath && !isDedicatedWorkerPath;
};

export const managerStorefrontStorageKey = (
  auth: Pick<ManagerAuthStatusResponse, 'tenant_id' | 'staff_user_id' | 'username'>,
): string => {
  const userKey = auth.staff_user_id
    ? `staff-${auth.staff_user_id}`
    : `user-${encodeURIComponent(auth.username.trim().toLowerCase())}`;
  return `${STORAGE_KEY_PREFIX}:${auth.tenant_id}:${userKey}`;
};

const errorStatus = (error: unknown): number | null => {
  const status = Number((error as { status?: unknown } | null)?.status);
  return Number.isInteger(status) ? status : null;
};

const isSelectionAccessError = (error: unknown): boolean => {
  const status = errorStatus(error);
  return status === 401 || status === 403;
};

const browserStorage = (): StorefrontStorage | null => {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
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

export class ManagerStorefrontSelection {
  readonly storefronts = ref<ManagerStorefrontResponse[]>([]);
  readonly selectedSlug = ref<string | null>(null);
  readonly loading = ref(false);
  readonly switching = ref(false);
  readonly error = ref('');

  private identity: Pick<ManagerAuthStatusResponse, 'tenant_id' | 'staff_user_id' | 'username'> | null = null;
  private readonly storage: () => StorefrontStorage | null;
  private readonly reloadPage: ReloadPage;

  constructor(
    storage: () => StorefrontStorage | null = browserStorage,
    reloadPage: ReloadPage = browserReload,
  ) {
    this.storage = storage;
    this.reloadPage = reloadPage;
  }

  prepareAuthentication(): void {
    this.identity = null;
    this.storefronts.value = [];
    this.selectedSlug.value = null;
    this.loading.value = false;
    this.switching.value = false;
    this.error.value = '';
  }

  async initialize(
    auth: Pick<ManagerAuthStatusResponse, 'tenant_id' | 'staff_user_id' | 'username'>,
    loadStorefronts: StorefrontListLoader = () => ManagerService.listManagerStorefronts(),
  ): Promise<void> {
    this.identity = auth;
    this.storefronts.value = [];
    this.error.value = '';
    this.loading.value = true;

    const key = managerStorefrontStorageKey(auth);
    const storage = this.storage();
    const storedValue = storageGet(storage, key);
    const storedSlug = normalizedSlug(storedValue);
    if (storedValue && !storedSlug) {
      storageRemove(storage, key);
    }
    this.selectedSlug.value = storedSlug;

    try {
      let response: ManagerStorefrontListResponse;
      try {
        response = await loadStorefronts();
      } catch (error) {
        if (!storedSlug || !isSelectionAccessError(error)) throw error;
        storageRemove(storage, key);
        this.selectedSlug.value = null;
        response = await loadStorefronts();
      }

      const seen = new Set<string>();
      const storefronts = (response.items ?? []).flatMap((storefront) => {
        const slug = normalizedSlug(storefront.slug);
        if (!slug || seen.has(slug)) return [];
        seen.add(slug);
        return [{ ...storefront, slug }];
      });
      this.storefronts.value = storefronts;

      const current = storefronts.find((storefront) => storefront.is_current)
        ?? storefronts.find((storefront) => storefront.is_default)
        ?? storefronts[0]
        ?? null;
      this.selectedSlug.value = current?.slug ?? null;
      if (current) storageSet(storage, key, current.slug);
      else storageRemove(storage, key);
    } catch (error) {
      this.selectedSlug.value = null;
      storageRemove(storage, key);
      if (isSelectionAccessError(error)) throw error;
      this.error.value = 'Не удалось загрузить доступные витрины';
    } finally {
      this.loading.value = false;
    }
  }

  switchTo(rawSlug: string): boolean {
    const slug = normalizedSlug(rawSlug);
    const allowed = slug && this.storefronts.value.some((storefront) => storefront.slug === slug);
    if (!slug || !allowed || !this.identity || slug === this.selectedSlug.value || this.switching.value) {
      return false;
    }

    if (!storageSet(this.storage(), managerStorefrontStorageKey(this.identity), slug)) {
      this.error.value = 'Браузер не разрешил сохранить выбранную витрину';
      return false;
    }
    this.selectedSlug.value = slug;
    this.switching.value = true;
    this.reloadPage();
    return true;
  }
}

export const managerStorefrontSelection = new ManagerStorefrontSelection();

export const getManagerStorefrontRequestHeaders = (
  url: string,
  slug = managerStorefrontSelection.selectedSlug.value,
): Record<string, string> => {
  const selectedSlug = normalizedSlug(slug);
  if (!selectedSlug || !isManagerApiRequest(url)) return {};
  return { [MANAGER_STOREFRONT_HEADER]: selectedSlug };
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
