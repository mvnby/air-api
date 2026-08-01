import { mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ManagerStorefrontSwitcher from '../src/components/manager/ManagerStorefrontSwitcher.vue';
import type { ManagerStorefrontResponse } from '../src/client';
import {
  MANAGER_STOREFRONT_HEADER,
  ManagerStorefrontSelection,
  createManagerStorefrontHeaderResolver,
  getManagerStorefrontRequestHeaders,
  installManagerStorefrontFetchScope,
  managerStorefrontSelection,
  managerStorefrontStorageKey,
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
});

describe('ManagerStorefrontSelection', () => {
  it('isolates persisted choices by tenant and authenticated user', async () => {
    const { storage, values } = createStorage();
    const selection = new ManagerStorefrontSelection(() => storage, vi.fn());
    const firstKey = managerStorefrontStorageKey(auth);
    const otherUser = { ...auth, staff_user_id: 43, username: 'other-manager' };
    const otherKey = managerStorefrontStorageKey(otherUser);
    values.set(firstKey, 'orsha');
    values.set(otherKey, 'minsk');

    await selection.initialize(auth, async () => ({
      items: [
        { ...mainStorefront, is_current: false },
        { ...orshaStorefront, is_current: true },
      ],
    }));
    expect(selection.selectedSlug.value).toBe('orsha');

    selection.prepareAuthentication();
    await selection.initialize(otherUser, async () => ({
      items: [
        { ...mainStorefront, is_current: false },
        { ...minskStorefront, is_current: true },
      ],
    }));
    expect(selection.selectedSlug.value).toBe('minsk');
    expect(firstKey).not.toBe(otherKey);
    expect(values.get(firstKey)).toBe('orsha');
  });

  it('drops malformed storage before discovery', async () => {
    const { storage, values } = createStorage();
    const selection = new ManagerStorefrontSelection(() => storage, vi.fn());
    const key = managerStorefrontStorageKey(auth);
    values.set(key, 'BAD / SLUG');
    const selectedDuringLoad: Array<string | null> = [];

    await selection.initialize(auth, async () => {
      selectedDuringLoad.push(selection.selectedSlug.value);
      return { items: [mainStorefront] };
    });

    expect(selectedDuringLoad).toEqual([null]);
    expect(selection.selectedSlug.value).toBe('main');
    expect(values.get(key)).toBe('main');
  });

  it.each([401, 403])('recovers once from stale selection after HTTP %s', async (status) => {
    const { storage, values } = createStorage();
    const selection = new ManagerStorefrontSelection(() => storage, vi.fn());
    const key = managerStorefrontStorageKey(auth);
    values.set(key, 'removed-storefront');
    const attempts: Array<string | null> = [];

    await selection.initialize(auth, async () => {
      attempts.push(selection.selectedSlug.value);
      if (attempts.length === 1) throw { status };
      return { items: [mainStorefront] };
    });

    expect(attempts).toEqual(['removed-storefront', null]);
    expect(selection.selectedSlug.value).toBe('main');
    expect(values.get(key)).toBe('main');
  });

  it('never retries a rejected fallback more than once', async () => {
    const { storage, values } = createStorage();
    const selection = new ManagerStorefrontSelection(() => storage, vi.fn());
    values.set(managerStorefrontStorageKey(auth), 'removed-storefront');
    const loader = vi.fn().mockRejectedValue({ status: 403 });

    await expect(selection.initialize(auth, loader)).rejects.toEqual({ status: 403 });
    expect(loader).toHaveBeenCalledTimes(2);
    expect(selection.selectedSlug.value).toBeNull();
  });

  it('persists a validated choice and reloads exactly once', async () => {
    const { storage, values } = createStorage();
    const reload = vi.fn();
    const selection = new ManagerStorefrontSelection(() => storage, reload);
    await selection.initialize(auth, async () => ({ items: [mainStorefront, orshaStorefront] }));

    expect(selection.switchTo('orsha')).toBe(true);
    expect(selection.selectedSlug.value).toBe('orsha');
    expect(values.get(managerStorefrontStorageKey(auth))).toBe('orsha');
    expect(reload).toHaveBeenCalledTimes(1);
    expect(selection.switchTo('orsha')).toBe(false);
    expect(selection.switchTo('foreign')).toBe(false);
    expect(reload).toHaveBeenCalledTimes(1);
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
    expect(badge.attributes('title')).toBe('Витрина: MVN Орша, Орша');
    expect(badge.attributes('aria-label')).toBe('Текущая витрина: MVN Орша, Орша');
    expect(badge.classes()).toContain('md:flex');
  });
});
