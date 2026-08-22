import { mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it } from 'vitest';
import type { DashboardKpi } from '../src/client';
import DashboardKpiCard from '../src/components/dashboard/DashboardKpiCard.vue';
import DashboardMarketing from '../src/components/dashboard/DashboardMarketing.vue';
import {
  DASHBOARD_MODE_STORAGE_KEY,
  dashboardKpiOrder,
  dashboardMarketingStatus,
  formatMarketingProvider,
  formatMarketingValue,
  getDashboardTrend,
  loadDashboardMode,
  saveDashboardMode,
} from '../src/services/dashboard-overview';

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
});
