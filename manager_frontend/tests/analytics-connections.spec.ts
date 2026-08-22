import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  list: vi.fn(), metrika: vi.fn(), direct: vi.fn(), webmaster: vi.fn(),
  googleAnalytics: vi.fn(), googleAds: vi.fn(), searchConsole: vi.fn(),
}));

vi.mock('../src/client', () => ({
  ManagerAnalyticsConnectionsService: {
    listManagerAnalyticsConnections: mocks.list,
    upsertManagerYandexMetrikaConnection: mocks.metrika,
    upsertManagerYandexDirectConnection: mocks.direct,
    upsertManagerYandexWebmasterConnection: mocks.webmaster,
    startManagerGoogleAnalyticsAuthorization: mocks.googleAnalytics,
    startManagerGoogleAdsAuthorization: mocks.googleAds,
    startManagerGoogleSearchConsoleAuthorization: mocks.searchConsole,
  },
}));

import AnalyticsConnectionsView from '../src/views/AnalyticsConnectionsView.vue';
import { managerStorefrontSelection } from '../src/services/manager-storefront-selection';

const items = [
  { provider: 'yandex_metrika', label: 'Яндекс Метрика', description: 'Посещения сайта.', state: 'not_configured', available: true, credentials_configured: false },
  { provider: 'yandex_direct', label: 'Яндекс Директ', description: 'Расходы и клики.', state: 'not_configured', available: true, credentials_configured: false },
  { provider: 'yandex_webmaster', label: 'Яндекс Вебмастер', description: 'Запросы и позиции.', state: 'not_configured', available: true, credentials_configured: false },
  { provider: 'google_analytics', label: 'Google Analytics 4', description: 'Трафик GA4.', state: 'not_configured', available: true, credentials_configured: false },
  { provider: 'google_ads', label: 'Google Ads', description: 'Реклама Google.', state: 'not_configured', available: true, credentials_configured: false },
  { provider: 'google_search_console', label: 'Google Search Console', description: 'Запросы Google.', state: 'not_configured', available: true, credentials_configured: false },
] as const;

const findCard = (wrapper: ReturnType<typeof mount>, label: string) => (
  wrapper.findAll('article').find(card => card.text().includes(label))!
);

describe('analytics connections', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    document.body.innerHTML = '';
    window.history.replaceState({}, '', '/manager/profile/integrations');
    managerStorefrontSelection.storefronts.value = [{ id: 71, tenant_id: 21, slug: 'vitebsk', display_name: 'Витебск', status: 'active', city: 'Витебск', default_locale: 'ru-BY', currency: 'BYN', is_default: true, is_current: true }];
    managerStorefrontSelection.selectedSlug.value = 'vitebsk';
    mocks.list.mockResolvedValue({ tenant_id: 21, storefront_id: 71, items });
    mocks.metrika.mockResolvedValue({ ...items[0], state: 'connected', credentials_configured: true, counter_id: '123456', counter_name: 'Мастер Воздуха Витебск', site: 'mvn.by' });
    mocks.direct.mockResolvedValue({ ...items[1], state: 'connected', credentials_configured: true, configuration: { 'Логин клиента': 'master-vozduha' } });
  });

  it('shows all six provider cards scoped to the selected storefront', async () => {
    const wrapper = mount(AnalyticsConnectionsView);
    await flushPromises();
    expect(wrapper.text()).toContain('«Витебск»');
    for (const item of items) expect(wrapper.text()).toContain(item.label);
  });

  it('saves Direct access without rendering the submitted token', async () => {
    const wrapper = mount(AnalyticsConnectionsView, { attachTo: document.body });
    await flushPromises();
    await findCard(wrapper, 'Яндекс Директ').get('button').trigger('click');
    await flushPromises();
    const login = document.body.querySelector('[data-testid="direct-client-login"]') as HTMLInputElement;
    const token = document.body.querySelector('[data-testid="yandex-provider-oauth-token"]') as HTMLInputElement;
    login.value = 'master-vozduha'; login.dispatchEvent(new Event('input', { bubbles: true }));
    token.value = 'secure-direct-token'; token.dispatchEvent(new Event('input', { bubbles: true }));
    document.body.querySelector('form')?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await flushPromises();
    expect(mocks.direct).toHaveBeenCalledWith({ client_login: 'master-vozduha', oauth_token: 'secure-direct-token' });
    expect(wrapper.text()).not.toContain('secure-direct-token');
    wrapper.unmount();
  });

  it('shows Direct scope and official help link', async () => {
    const wrapper = mount(AnalyticsConnectionsView, { attachTo: document.body });
    await flushPromises();
    const buttons = findCard(wrapper, 'Яндекс Директ').findAll('button');
    await buttons[1].trigger('click');
    await flushPromises();
    const help = document.body.querySelector('[data-testid="yandex-provider-help"]');
    expect(help?.textContent).toContain('direct:api');
    expect(help?.querySelector('a')?.getAttribute('href')).toBe('https://yandex.ru/dev/direct/doc/ru/concepts/register');
    wrapper.unmount();
  });

  it('reports OAuth callback outcome and removes callback parameters', async () => {
    window.history.replaceState({}, '', '/manager/profile/integrations?oauth_connected=google_search_console');
    const wrapper = mount(AnalyticsConnectionsView);
    await flushPromises();
    expect(wrapper.get('[data-testid="analytics-saved"]').text()).toContain('Google Search Console');
    expect(window.location.search).not.toContain('oauth_connected');
  });
});
