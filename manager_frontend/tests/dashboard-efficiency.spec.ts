import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import DashboardAdvertising from '../src/components/dashboard/DashboardAdvertising.vue';
import DashboardSearchDemand from '../src/components/dashboard/DashboardSearchDemand.vue';
import DashboardSiteSeo from '../src/components/dashboard/DashboardSiteSeo.vue';

const searchDemand = {
  status: 'unconfigured' as const,
  providers: [],
  queries: [],
};

describe('dashboard efficiency integrations', () => {
  it('does not render a meaningless advertising metric panel before providers are connected', () => {
    const wrapper = mount(DashboardAdvertising, {
      props: { marketing: { status: 'unconfigured', providers: [] }, canManageIntegrations: false },
    });

    expect(wrapper.text()).toContain('Источник пока не подключён');
    expect(wrapper.text()).not.toContain('Расход');
    expect(wrapper.find('a[href="/manager/integrations"]').exists()).toBe(false);
  });

  it('keeps a fresh empty advertising report distinct from an unconfigured connection', () => {
    const wrapper = mount(DashboardAdvertising, {
      props: {
        canManageIntegrations: true,
        marketing: {
          status: 'fresh',
          providers: [{ provider: 'yandex_direct', status: 'fresh' }],
        },
      },
    });

    expect(wrapper.text()).toContain('За этот период рекламный кабинет не вернул показателей.');
    expect(wrapper.text()).toContain('Настроить подключения');
  });

  it('shows a provider error as an unavailable saved connection', () => {
    const wrapper = mount(DashboardAdvertising, {
      props: {
        canManageIntegrations: false,
        marketing: {
          status: 'error',
          providers: [{ provider: 'yandex_direct', status: 'error', message: 'Подключение сохранено, данные недоступны.' }],
        },
      },
    });

    expect(wrapper.text()).toContain('Подключение сохранено, но получить данные сейчас не удалось.');
    expect(wrapper.text()).toContain('Подключение сохранено, данные недоступны.');
  });

  it('renders website traffic separately from advertising providers', () => {
    const wrapper = mount(DashboardSiteSeo, {
      props: {
        canManageIntegrations: false,
        searchDemand,
        marketing: {
          status: 'fresh',
          providers: [
            { provider: 'yandex_metrika', status: 'fresh', visits: 145 },
            { provider: 'yandex_direct', status: 'fresh', ad_spend: 30 },
          ],
        },
      },
    });

    expect(wrapper.text()).toContain('Посещаемость');
    expect(wrapper.text()).toContain('145');
    expect(wrapper.text()).not.toContain('Расход');
  });

  it('keeps traffic source breakdown available and names mixed source health explicitly', async () => {
    const wrapper = mount(DashboardSiteSeo, {
      props: {
        canManageIntegrations: false,
        searchDemand,
        marketing: {
          status: 'fresh',
          sources: Array.from({ length: 7 }, (_, index) => ({ name: `source-${index + 1}`, visits: 10, share_pct: 1 })),
          providers: [
            { provider: 'yandex_metrika', status: 'fresh', visits: 145 },
            { provider: 'google_analytics', status: 'error' },
          ],
        },
      },
    });

    expect(wrapper.text()).toContain('Частично доступно');
    expect(wrapper.text()).toContain('source-6');
    expect(wrapper.text()).not.toContain('source-7');
    await wrapper.findAll('button').find(button => button.text().startsWith('Показать все'))!.trigger('click');
    expect(wrapper.text()).toContain('source-7');
  });

  it('distinguishes an empty fresh search report from missing search connections', () => {
    const fresh = mount(DashboardSearchDemand, {
      props: {
        canManageIntegrations: true,
        demand: { status: 'fresh', providers: [{ provider: 'yandex_webmaster', status: 'fresh' }], queries: [] },
      },
    });
    const unconfigured = mount(DashboardSearchDemand, {
      props: { canManageIntegrations: true, demand: searchDemand },
    });

    expect(fresh.text()).toContain('За этот период поисковые системы не вернули запросов.');
    expect(unconfigured.text()).toContain('Подключите Яндекс Вебмастер');
    expect(unconfigured.find('a[href="/manager/integrations"]').exists()).toBe(true);
  });

  it('labels fresh search data plus a failed provider as partially available, not stale', () => {
    const wrapper = mount(DashboardSearchDemand, {
      props: {
        canManageIntegrations: false,
        demand: {
          status: 'stale',
          providers: [
            { provider: 'yandex_webmaster', status: 'fresh' },
            { provider: 'google_search_console', status: 'error' },
          ],
          queries: [],
        },
      },
    });

    expect(wrapper.text()).toContain('Частично доступно');
    expect(wrapper.text()).not.toContain('Часть данных устарела');
  });
});
