import { mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it } from 'vitest';
import type { DashboardKpi } from '../src/client';
import DashboardKpiCard from '../src/components/dashboard/DashboardKpiCard.vue';
import DashboardFunnel from '../src/components/dashboard/DashboardFunnel.vue';
import DashboardMarketing from '../src/components/dashboard/DashboardMarketing.vue';
import DashboardSearchDemand from '../src/components/dashboard/DashboardSearchDemand.vue';
import {
  DASHBOARD_MODE_STORAGE_KEY,
  dashboardKpiOrder,
  dashboardMarketingStatus,
  formatMarketingProvider,
  formatDurationSeconds,
  formatDashboardComparisonPeriod,
  formatMarketingValue,
  formatSearchDemandProvider,
  getDashboardTrend,
  loadDashboardMode,
  saveDashboardMode,
} from '../src/services/dashboard-overview';
import { buildSearchDemandCsv } from '../src/services/search-demand-export';

const kpi = (overrides: Partial<DashboardKpi> = {}): DashboardKpi => ({
  label: 'Метрика', unit: 'count', current: 12, previous: 10, delta_pct: 20, trend: 'up', ...overrides,
});

describe('dashboard overview presentation rules', () => {
  beforeEach(() => window.localStorage.clear());

  it('keeps a compact, persisted two-mode order without changing KPI data', () => {
    expect(loadDashboardMode()).toBe('manager');
    saveDashboardMode('owner');
    expect(window.localStorage.getItem(DASHBOARD_MODE_STORAGE_KEY)).toBe('owner');
    expect(loadDashboardMode()).toBe('owner');
    expect(dashboardKpiOrder.manager).toHaveLength(6);
    expect(dashboardKpiOrder.owner).toHaveLength(6);
    expect([...dashboardKpiOrder.manager].sort()).toEqual([...dashboardKpiOrder.owner].sort());
  });

  it('shows a current snapshot instead of an invented delta for unavailable history', () => {
    expect(getDashboardTrend('active_tasks', kpi({ previous: null, delta_pct: null, trend: 'unavailable' }))).toEqual({
      label: 'Срез на сейчас', tone: 'neutral',
    });
  });

  it('labels the exact equal month-to-date comparison period', () => {
    expect(formatDashboardComparisonPeriod({
      current: { start: '2026-08-01T00:00:00+03:00', end: '2026-08-25T00:00:00+03:00' },
      previous: { start: '2026-07-01T00:00:00+03:00', end: '2026-07-25T00:00:00+03:00' },
    })).toBe('1–24 авг. · сравнение: 1–24 июл.');
  });

  it('does not describe receivables growth as positive', () => {
    expect(getDashboardTrend('receivables', kpi({ trend: 'up', delta_pct: 20 })).tone).toBe('negative');
    expect(getDashboardTrend('receivables', kpi({ trend: 'down', delta_pct: -20 })).tone).toBe('positive');
  });

  it('maps every local marketing integration state without fabricating values', () => {
    expect(dashboardMarketingStatus({ status: 'unconfigured' }).label).toBe('Не подключено');
    expect(dashboardMarketingStatus({ status: 'fresh' }).label).toBe('Данные актуальны');
    expect(dashboardMarketingStatus({ status: 'stale' }).label).toBe('Данные устарели');
    expect(dashboardMarketingStatus({ status: 'error' }).label).toBe('Ошибка интеграции');
    expect(dashboardMarketingStatus({ status: 'error' }).message).toContain('CRM-данные');
    expect(formatMarketingProvider('yandex_metrika')).toBe('Яндекс Метрика');
    expect(formatMarketingValue(null, 'currency')).toBe('—');
  });

  it('uses the product KPI label instead of a short backend label', () => {
    const wrapper = mount(DashboardKpiCard, {
      props: { metric: 'receivables', kpi: kpi({ label: 'Долг', unit: 'byn' }) },
    });
    expect(wrapper.text()).toContain('Дебиторская задолженность');
    expect(wrapper.text()).not.toContain('Долг');
  });

  it('localizes the marketing provider and explanation instead of rendering backend diagnostics', () => {
    const wrapper = mount(DashboardMarketing, {
      props: {
        marketing: {
          status: 'error',
          provider: 'yandex_metrika',
          message: 'yandex API request failed: forbidden',
          visits: null,
          sources: [],
        },
      },
    });
    expect(wrapper.text()).toContain('Яндекс Метрика');
    expect(wrapper.text()).toContain('Интеграция аналитики временно недоступна');
    expect(wrapper.text()).not.toContain('yandex API request failed');
  });

  it('keeps advertising-platform conversions distinct from CRM CPL and CAC', () => {
    const wrapper = mount(DashboardMarketing, {
      props: {
        marketing: {
          status: 'fresh', provider: 'yandex_direct', ad_spend: 350, clicks: 120,
          platform_conversions: 18, leads: 7, cost_per_lead: 50, customer_acquisition_cost: 175,
          providers: [{ provider: 'yandex_direct', status: 'fresh', ad_spend: 350, clicks: 120, platform_conversions: 18 }],
        },
      },
    });
    expect(wrapper.text()).toContain('Рекламные платформы');
    expect(wrapper.text()).toContain('Конверсии платформ');
    expect(wrapper.text()).toContain('Результат в CRM');
    expect(wrapper.text()).toContain('Расход / CRM-лид');
    expect(wrapper.text()).toContain('Расход / продажу');
    expect(wrapper.text()).toContain('Без сквозной атрибуции');
    expect(formatMarketingProvider('google_ads')).toBe('Google Ads');
    expect(formatMarketingProvider('integrated')).toBe('Сводка по подключённым источникам');
  });

  it('surfaces a partial integration outage and hides unconfigured provider noise', () => {
    const wrapper = mount(DashboardMarketing, {
      props: {
        marketing: {
          status: 'fresh', provider: 'integrated', sources: [], updated_at: '2026-08-24T10:00:00+03:00',
          providers: [
            { provider: 'yandex_metrika', status: 'error' },
            { provider: 'google_analytics', status: 'fresh', sessions: 540 },
            { provider: 'google_ads', status: 'unconfigured' },
          ],
        },
      },
    });
    expect(wrapper.text()).toContain('Частично доступно');
    expect(wrapper.text()).toContain('1 источник требует внимания');
    expect(wrapper.text()).toContain('Обновлено 24 авг.');
    expect(wrapper.get('a').attributes('href')).toBe('/manager/integrations');
    expect(wrapper.text()).not.toContain('Google Ads');
  });

  it('keeps acquisition sources compact until the direct two-state toggle is used', async () => {
    const wrapper = mount(DashboardMarketing, {
      props: {
        marketing: {
          status: 'fresh', provider: 'integrated',
          sources: Array.from({ length: 8 }, (_, index) => ({ name: `source-${index + 1}`, visits: 10, share_pct: 1 })),
        },
      },
    });
    expect(wrapper.text()).toContain('source-6');
    expect(wrapper.text()).not.toContain('source-7');
    await wrapper.get('button').trigger('click');
    expect(wrapper.text()).toContain('source-8');
    expect(wrapper.get('button').text()).toBe('Свернуть');
  });

  it('does not present a cross-period ratio above 100 percent as funnel conversion', () => {
    const wrapper = mount(DashboardFunnel, {
      props: {
        stages: [
          { stage: 'proposals', label: 'Предложения', current: 1, conversion_from_previous_pct: 50 },
          { stage: 'sales', label: 'Продажи', current: 5, conversion_from_previous_pct: 500 },
        ],
      },
    });
    expect(wrapper.text()).toContain('Конверсия: не сопоставимо');
    expect(wrapper.text()).not.toContain('500%');
  });

  it('shows provider-specific web analytics instead of advertising placeholders', () => {
    const wrapper = mount(DashboardMarketing, {
      props: {
        marketing: {
          status: 'fresh', provider: 'integrated',
          providers: [
            { provider: 'yandex_metrika', status: 'fresh', visits: 861, bounce_rate: 17.5, average_session_duration_seconds: 93 },
            { provider: 'google_analytics', status: 'fresh', sessions: 540, active_users: 420, engagement_rate: 61.25, average_session_duration_seconds: 82 },
          ],
        },
      },
    });
    const [metrika, ga4] = wrapper.findAll('article').map(card => card.text());
    expect(metrika).toContain('Визиты861');
    expect(metrika).toContain('Отказы17,5%');
    expect(metrika).toContain('Среднее время на сайте1 мин 33 с');
    expect(metrika).not.toContain('Расход');
    expect(metrika).not.toContain('Клики');
    expect(ga4).toContain('Сеансы540');
    expect(ga4).toContain('Активные пользователи420');
    expect(ga4).toContain('Вовлечённость61,25%');
    expect(ga4).not.toContain('Расход');
    expect(formatDurationSeconds(82)).toBe('1 мин 22 с');
  });

  it('filters search demand by provider and gives mobile-safe query content', async () => {
    const wrapper = mount(DashboardSearchDemand, {
      props: {
        demand: {
          status: 'stale',
          providers: [{ provider: 'yandex_webmaster', status: 'fresh' }, { provider: 'google_search_console', status: 'stale' }],
          queries: [
            { provider: 'yandex_webmaster', query: 'купить кондиционер витебск', clicks: 12, impressions: 100, ctr: 12, avg_position: 3.4 },
            { provider: 'google_search_console', query: 'монтаж кондиционера', clicks: 4, impressions: 80, ctr: 5, avg_position: 7.1 },
          ],
        },
      },
    });
    expect(wrapper.text()).toContain('задержкой');
    expect(wrapper.text()).toContain('приватности');
    await wrapper.findAll('button').find(button => button.text() === 'Яндекс Вебмастер')!.trigger('click');
    expect(wrapper.text()).toContain('купить кондиционер витебск');
    expect(wrapper.text()).not.toContain('монтаж кондиционера');
    expect(formatSearchDemandProvider('google_search_console')).toBe('Google Search Console');
  });

  it('shows ten popular queries, expands, and sorts by a selected metric', async () => {
    const queries = Array.from({ length: 12 }, (_, index) => ({
      provider: 'yandex_webmaster' as const,
      query: `запрос ${index + 1}`,
      clicks: index + 1,
      impressions: (index + 1) * 10,
      ctr: index + 1,
      avg_position: 12 - index,
    }));
    const wrapper = mount(DashboardSearchDemand, {
      props: { demand: { status: 'fresh', providers: [{ provider: 'yandex_webmaster', status: 'fresh' }], queries } },
    });

    expect(wrapper.findAll('tbody tr')).toHaveLength(10);
    expect(wrapper.find('tbody tr').text()).toContain('запрос 12');
    await wrapper.findAll('button').find(button => button.text().startsWith('Показать все'))!.trigger('click');
    expect(wrapper.findAll('tbody tr')).toHaveLength(12);
    await wrapper.findAll('button').find(button => button.text().startsWith('Средняя позиция'))!.trigger('click');
    expect(wrapper.find('tbody tr').text()).toContain('запрос 12');
    expect(wrapper.find('th[aria-sort="ascending"]').text()).toContain('Средняя позиция');
  });

  it('exports every available query row as Excel-friendly CSV', () => {
    const csv = buildSearchDemandCsv([
      { provider: 'yandex_webmaster', query: 'купить "кондиционер"', clicks: 8, impressions: 100, ctr: 8, avg_position: 3.4 },
      { provider: 'google_search_console', query: 'монтаж', clicks: 3, impressions: 50, ctr: 6, avg_position: null },
    ]);

    expect(csv.startsWith('\uFEFF')).toBe(true);
    expect(csv).toContain('"купить ""кондиционер"""');
    expect(csv).toContain('"Яндекс Вебмастер";"8";"100";"8";"3,4"');
    expect(csv.split('\r\n')).toHaveLength(4);
  });
});
