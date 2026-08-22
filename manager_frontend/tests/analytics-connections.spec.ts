import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  upsert: vi.fn(),
}));

vi.mock('../src/client', () => ({
  ManagerAnalyticsConnectionsService: {
    listManagerAnalyticsConnections: mocks.list,
    upsertManagerYandexMetrikaConnection: mocks.upsert,
  },
}));

import AnalyticsConnectionsView from '../src/views/AnalyticsConnectionsView.vue';
import { managerStorefrontSelection } from '../src/services/manager-storefront-selection';

const items = [
  {
    provider: 'yandex_metrika',
    label: 'Яндекс Метрика',
    description: 'Посещения сайта.',
    state: 'not_configured',
    available: true,
    credentials_configured: false,
  },
  {
    provider: 'yandex_direct',
    label: 'Яндекс Директ',
    description: 'Расходы и клики.',
    state: 'coming_soon',
    available: false,
  },
  {
    provider: 'google_analytics',
    label: 'Google Analytics 4',
    description: 'Трафик GA4.',
    state: 'coming_soon',
    available: false,
  },
  {
    provider: 'google_ads',
    label: 'Google Ads',
    description: 'Реклама Google.',
    state: 'coming_soon',
    available: false,
  },
] as const;

describe('analytics connections', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    document.body.innerHTML = '';
    managerStorefrontSelection.storefronts.value = [{
      id: 71,
      tenant_id: 21,
      slug: 'vitebsk',
      display_name: 'Витебск',
      status: 'active',
      city: 'Витебск',
      default_locale: 'ru-BY',
      currency: 'BYN',
      is_default: true,
      is_current: true,
    }];
    managerStorefrontSelection.selectedSlug.value = 'vitebsk';
    mocks.list.mockResolvedValue({ tenant_id: 21, storefront_id: 71, items });
    mocks.upsert.mockResolvedValue({
      ...items[0],
      state: 'connected',
      credentials_configured: true,
      counter_id: '123456',
      counter_name: 'Мастер Воздуха Витебск',
      site: 'mvn.by',
    });
  });

  it('shows exact storefront scope and all provider states', async () => {
    const wrapper = mount(AnalyticsConnectionsView);
    await flushPromises();

    expect(wrapper.text()).toContain('«Витебск»');
    expect(wrapper.text()).toContain('Яндекс Метрика');
    expect(wrapper.text()).toContain('Яндекс Директ');
    expect(wrapper.text()).toContain('Google Analytics 4');
    expect(wrapper.text()).toContain('Google Ads');
    expect(wrapper.text()).toContain('Скоро');
  });

  it('opens official help from the question action', async () => {
    const wrapper = mount(AnalyticsConnectionsView, { attachTo: document.body });
    await flushPromises();

    await wrapper.get('[data-testid="analytics-help-button"]').trigger('click');
    await flushPromises();

    const help = document.body.querySelector('[data-testid="metrika-help"]');
    expect(help?.textContent).toContain('metrika:read');
    expect(help?.querySelector('a')?.getAttribute('href')).toBe(
      'https://yandex.ru/dev/metrika/ru/intro/authorization',
    );
    wrapper.unmount();
  });

  it('saves a token once and renders the verified counter', async () => {
    const wrapper = mount(AnalyticsConnectionsView, { attachTo: document.body });
    await flushPromises();

    const connect = wrapper.findAll('button').find(button => button.text() === 'Подключить');
    expect(connect).toBeDefined();
    await connect!.trigger('click');
    await flushPromises();
    const counter = document.body.querySelector('[data-testid="metrika-counter-id"]') as HTMLInputElement;
    const token = document.body.querySelector('[data-testid="metrika-oauth-token"]') as HTMLInputElement;
    counter.value = '123456';
    counter.dispatchEvent(new Event('input', { bubbles: true }));
    token.value = 'secure-oauth-token-value';
    token.dispatchEvent(new Event('input', { bubbles: true }));
    document.body.querySelector('form')?.dispatchEvent(
      new Event('submit', { bubbles: true, cancelable: true }),
    );
    await flushPromises();

    expect(mocks.upsert).toHaveBeenCalledWith({
      counter_id: '123456',
      oauth_token: 'secure-oauth-token-value',
    });
    expect(wrapper.get('[data-testid="analytics-saved"]').text()).toContain('Витебск');
    expect(wrapper.text()).toContain('Мастер Воздуха Витебск');
    wrapper.unmount();
  });
});
