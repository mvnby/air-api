import { mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { registerUnsavedNavigationGuard } from '../src/services/unsaved-navigation-guard';
import ManagerStorefrontSwitcher from '../src/components/manager/ManagerStorefrontSwitcher.vue';
import type { ManagerStorefrontResponse } from '../src/client';
import {
  MANAGER_STOREFRONT_HEADER,
  MANAGER_TENANT_HEADER,
  ManagerContextError,
  ManagerStorefrontSelection,
  createManagerStorefrontHeaderResolver,
  getManagerStorefrontRequestHeaders,
  installManagerStorefrontFetchScope,
  managerStorefrontSelection,
  managerContextStorageKey,
} from '../src/services/manager-storefront-selection';

type AuthIdentity = {
  tenant_id: number;
  staff_user_id: number | null;
  username: string;
};

const mainStorefront: ManagerStorefrontResponse = {
  slug: 'main',
  display_name: 'MVN Витебск',
  city: 'Витебск',
  default_locale: 'ru-BY',
  currency: 'BYN',
  is_default: true,
  is_current: true,
};

const orshaStorefront: ManagerStorefrontResponse = {
  ...mainStorefront,
  slug: 'orsha',
  display_name: 'MVN Орша',
  city: 'Орша',
  is_default: false,
  is_current: false,
};

const minskStorefront: ManagerStorefrontResponse = {
  ...mainStorefront,
  slug: 'minsk',
  display_name: 'MVN Минск',
  city: 'Минск',
  is_default: false,
  is_current: false,
};

const auth: AuthIdentity = {
  tenant_id: 7,
  staff_user_id: 42,
  username: 'manager',
};

const createStorage = () => {
  const values = new Map<string, string>();
  return {
    values,
    storage: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    },
  };
};

const mountedWrappers: VueWrapper[] = [];

afterEach(() => {
  for (const wrapper of mountedWrappers.splice(0)) wrapper.unmount();
  managerStorefrontSelection.prepareAuthentication();
  vi.restoreAllMocks();
});

describe('manager storefront request scope', () => {
  it('adds the selection only to Manager API routes', async () => {
    expect(getManagerStorefrontRequestHeaders('/api/manager/orders', 'orsha')).toEqual({
      [MANAGER_STOREFRONT_HEADER]: 'orsha',
    });
    expect(getManagerStorefrontRequestHeaders('https://api.mvn.by/api/manager/orders/5', 'orsha')).toEqual({
      [MANAGER_STOREFRONT_HEADER]: 'orsha',
    });

    for (const url of [
      '/api/v1/products',
      '/api/internal/bot/v1/events',
      '/api/system/rebuild-web',
      '/api/manager/media/worker/jobs/claim',
      '/login/access-token',
      '/api/managerial/report',
    ]) {
      expect(getManagerStorefrontRequestHeaders(url, 'orsha')).toEqual({});
    }
    expect(getManagerStorefrontRequestHeaders('/api/manager/orders', 'BAD / SLUG')).toEqual({});

    managerStorefrontSelection.selectedSlug.value = 'orsha';
    const resolver = createManagerStorefrontHeaderResolver(async () => ({ 'X-Existing': 'kept' }));
    const headers = typeof resolver === 'function'
      ? await resolver({ method: 'GET', url: '/api/manager/orders' })
      : resolver;
    expect(headers).toEqual({
      'X-Existing': 'kept',
      [MANAGER_STOREFRONT_HEADER]: 'orsha',
    });
  });

  it('scopes direct fetch calls without leaking into public or worker routes', async () => {
    managerStorefrontSelection.selectedSlug.value = 'orsha';
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    const host = { fetch: fetchMock as unknown as typeof fetch };

    installManagerStorefrontFetchScope(host);
    const installedFetch = host.fetch;
    installManagerStorefrontFetchScope(host);
    expect(host.fetch).toBe(installedFetch);

    await host.fetch('/api/manager/orders');
    await host.fetch('/api/manager/orders/7', {
      headers: {
        [MANAGER_STOREFRONT_HEADER]: 'explicit-scope',
        'X-Existing': 'kept',
      },
    });
    await host.fetch('/api/v1/products');
    await host.fetch('/api/internal/bot/v1/events');
    await host.fetch('/api/manager/media/worker/jobs/claim');

    const scopedHeaders = new Headers(fetchMock.mock.calls[0]?.[1]?.headers);
    expect(scopedHeaders.get(MANAGER_STOREFRONT_HEADER)).toBe('orsha');

    const explicitHeaders = new Headers(fetchMock.mock.calls[1]?.[1]?.headers);
    expect(explicitHeaders.get(MANAGER_STOREFRONT_HEADER)).toBe('explicit-scope');
    expect(explicitHeaders.get('X-Existing')).toBe('kept');

    expect(fetchMock.mock.calls[2]).toEqual(['/api/v1/products', undefined]);
    expect(fetchMock.mock.calls[3]).toEqual(['/api/internal/bot/v1/events', undefined]);
    expect(fetchMock.mock.calls[4]).toEqual(['/api/manager/media/worker/jobs/claim', undefined]);
  });

  it('reports Manager 401 responses but ignores dedicated worker and public 401 responses', async () => {
    const onUnauthorized = vi.fn();
    const fetchMock = vi.fn().mockImplementation(async () => new Response('', { status: 401 }));
    const host = { fetch: fetchMock as unknown as typeof fetch };
    installManagerStorefrontFetchScope(host, onUnauthorized);

    await host.fetch('/api/manager/orders/7');
    await host.fetch('/api/manager/media/worker/jobs/claim');
    await host.fetch('/api/v1/products');

    expect(onUnauthorized).toHaveBeenCalledTimes(1);
    expect(onUnauthorized.mock.calls[0]?.[0]).toMatchObject({
      url: '/api/manager/orders/7',
      response: expect.objectContaining({ status: 401 }),
    });
  });
});

const choices = { ...auth, is_platform_owner: false, default_tenant_id: 7, items: [
  { tenant_id: 7, slug: 'first', display_name: 'Первая', role: 'owner', membership_id: 1, access_kind: 'membership' as const, is_system: false, demo_read_only: false, default_storefront_slug: 'main' },
  { tenant_id: 8, slug: 'second', display_name: 'Вторая', role: 'manager', membership_id: 2, access_kind: 'membership' as const, is_system: false, demo_read_only: false, default_storefront_slug: 'minsk' },
], total: 2, page: 1, limit: 100 };
const sites = async () => ({ items: [mainStorefront, orshaStorefront].map((site, id) => ({ ...site, id, status: 'active', city: site.city || null, domains: [] })) });

describe('company and site bootstrap', () => {
  it('uses a person-scoped tab choice after validating it against available companies and sites', async () => {
    const { storage, values } = createStorage();
    values.set(managerContextStorageKey(auth), JSON.stringify({ tenant_id: 7, site: 'orsha' }));
    const selection = new ManagerStorefrontSelection(() => storage, vi.fn());
    await selection.initializeContext(async () => choices, sites, '');
    expect(selection.selectedTenantId.value).toBe(7); expect(selection.selectedSlug.value).toBe('orsha');
    expect(managerContextStorageKey({ ...auth, tenant_id: 999 })).toBe(managerContextStorageKey(auth));
    expect(managerContextStorageKey({ ...auth, staff_user_id: 43 })).not.toBe(managerContextStorageKey(auth));
  });
  it.each(['?company=999', '?company=0', '?company=7x', '?company=7&company=8', '?company=7&site=main&site=orsha', '?company=99999999999999999', '?company=7&site=foreign', '?company=7&site=MAIN', '?site=bad%2Fslug'])('denies explicit invalid context %s', async query => {
    const selection = new ManagerStorefrontSelection(() => createStorage().storage, vi.fn());
    await expect(selection.initializeContext(async () => choices, sites, query)).rejects.toBeInstanceOf(ManagerContextError);
    expect(selection.selectedTenantId.value).toBeNull(); expect(selection.selectedSlug.value).toBeNull();
  });
  it('does not call a business endpoint for a forbidden explicit company', async () => {
    const loadSites = vi.fn(sites), selection = new ManagerStorefrontSelection();
    await expect(selection.initializeContext(async () => choices, loadSites, '?company=999')).rejects.toThrow('Нет доступа');
    expect(loadSites).not.toHaveBeenCalled();
  });
  it('recovers stale storage but never rewrites an explicit invalid URL to the default', async () => {
    const { storage, values } = createStorage(), selection = new ManagerStorefrontSelection(() => storage);
    values.set(managerContextStorageKey(auth), JSON.stringify({ tenant_id: 999, site: 'foreign' }));
    await selection.initializeContext(async () => choices, sites, '');
    expect(selection.selectedTenantId.value).toBe(7); expect(selection.selectedSlug.value).toBe('main');
  });
  it('keeps a zero-membership person outside business screens', async () => {
    const selection = new ManagerStorefrontSelection(), loadSites = vi.fn(sites);
    await expect(selection.initializeContext(async () => ({ ...choices, items: [], total: 0, default_tenant_id: null }), loadSites, '')).rejects.toThrow('приглашение');
    expect(loadSites).not.toHaveBeenCalled();
  });
  it('checks unsaved edits before changing storage or URL and preserves old live context until reload', async () => {
    const { storage, values } = createStorage(), reload = vi.fn(), selection = new ManagerStorefrontSelection(() => storage, reload);
    window.history.replaceState({}, '', '/manager/orders?company=7&site=main&tab=active');
    await selection.initializeContext(async () => choices, sites, window.location.search);
    const snapshot = values.get(managerContextStorageKey(auth));
    const unregister = registerUnsavedNavigationGuard(() => false);
    expect(await selection.switchTo('orsha')).toBe(false); expect(values.get(managerContextStorageKey(auth))).toBe(snapshot); expect(window.location.search).toContain('company=7'); expect(reload).not.toHaveBeenCalled(); unregister();
    expect(await selection.switchTo('orsha')).toBe(true);
    expect(selection.selectedSlug.value).toBe('main'); expect(selection.selectedTenantId.value).toBe(7);
    expect(JSON.parse(values.get(managerContextStorageKey(auth))!)).toEqual({ tenant_id: 7, site: 'orsha' });
    expect(window.location.search).toBe('?tab=active'); expect(reload).toHaveBeenCalledOnce();
    expect(await selection.switchCompany(8)).toBe(false);
  });
  it('never includes business context on personal or public requests', () => {
    managerStorefrontSelection.selectedTenantId.value = 7; managerStorefrontSelection.selectedSlug.value = 'main';
    expect(getManagerStorefrontRequestHeaders('/api/manager/orders')).toEqual({ [MANAGER_TENANT_HEADER]: '7', [MANAGER_STOREFRONT_HEADER]: 'main' });
    for (const url of ['/api/manager/account/companies', '/api/manager/account/profile/avatar', '/api/manager/account/telegram/link-challenges', '/api/account/invitations/accept']) expect(getManagerStorefrontRequestHeaders(url)).toEqual({});
  });
});

describe('ManagerStorefrontSwitcher', () => {
  const mountSwitcher = (storefronts: ManagerStorefrontResponse[], selectedSlug = storefronts[0]?.slug ?? null) => {
    const wrapper = mount(ManagerStorefrontSwitcher, {
      props: { storefronts, selectedSlug },
    });
    mountedWrappers.push(wrapper);
    return wrapper;
  };

  it('shows one storefront context without an unnecessary selector', () => {
    const wrapper = mountSwitcher([mainStorefront]);
    expect(wrapper.text()).toContain('MVN Витебск');
    expect(wrapper.text()).toContain('Витебск');
    expect(wrapper.find('button').exists()).toBe(false);
    expect(wrapper.find('select').exists()).toBe(false);
  });

  it('uses two direct keyboard-accessible choices for exactly two storefronts', async () => {
    const wrapper = mountSwitcher([mainStorefront, orshaStorefront]);
    const buttons = wrapper.findAll('button');
    expect(buttons).toHaveLength(2);
    expect(buttons[0]?.attributes('aria-pressed')).toBe('true');
    expect(buttons[1]?.attributes('aria-label')).toContain('MVN Орша, Орша');
    await buttons[1]?.trigger('click');
    expect(wrapper.emitted('select')).toEqual([['orsha']]);
  });

  it('keeps direct choices and never falls back to a dropdown for more storefronts', async () => {
    const wrapper = mountSwitcher([mainStorefront, orshaStorefront, minskStorefront]);
    const buttons = wrapper.findAll('button');
    expect(buttons).toHaveLength(3);
    expect(wrapper.find('select').exists()).toBe(false);
    expect(buttons[2]?.attributes('aria-label')).toContain('MVN Минск, Минск');
    await buttons[2]?.trigger('click');
    expect(wrapper.emitted('select')).toEqual([['minsk']]);
  });

  it('keeps current storefront context visible in the collapsed desktop sidebar', () => {
    const wrapper = mount(ManagerStorefrontSwitcher, {
      props: {
        storefronts: [mainStorefront, orshaStorefront],
        selectedSlug: 'orsha',
        collapsed: true,
      },
    });
    mountedWrappers.push(wrapper);

    const badge = wrapper.get('[data-testid="collapsed-storefront-badge"]');
    expect(badge.text()).toBe('ОР');
    expect(badge.attributes('title')).toBe('Сайт: MVN Орша, Орша');
    expect(badge.attributes('aria-label')).toBe('Текущий сайт: MVN Орша, Орша');
    expect(badge.classes()).toContain('md:flex');
  });
});
