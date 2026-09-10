import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import type { DashboardKpi } from '../src/client';
import DashboardFunnel from '../src/components/dashboard/DashboardFunnel.vue';
import DashboardKpiCard from '../src/components/dashboard/DashboardKpiCard.vue';
import DashboardSalesChart from '../src/components/dashboard/DashboardSalesChart.vue';
import DashboardSearchDemand from '../src/components/dashboard/DashboardSearchDemand.vue';
import {
  formatDashboardComparisonPeriod,
  formatDurationSeconds,
  getDashboardTrend,
} from '../src/services/dashboard-overview';
import { buildSearchDemandCsv } from '../src/services/search-demand-export';

const kpi = (overrides: Partial<DashboardKpi> = {}): DashboardKpi => ({
  label: 'Метрика', unit: 'count', current: 12, previous: 10, delta_pct: 20, trend: 'up', ...overrides,
});
const freshDemand = {
  status: 'fresh' as const,
  providers: [{ provider: 'yandex_webmaster' as const, status: 'fresh' as const }],
};

describe('dashboard overview presentation rules', () => {
  it('uses the exact API period range for month-to-date comparison', () => {
    expect(formatDashboardComparisonPeriod({
      current: { start: '2026-08-01T00:00:00+03:00', end: '2026-08-25T00:00:00+03:00' },
      previous: { start: '2026-07-01T00:00:00+03:00', end: '2026-07-25T00:00:00+03:00' },
    })).toBe('1–24 авг. · сравнение с 1–24 июл.');
  });

  it('does not invent historical movement for current-state KPIs', () => {
    expect(getDashboardTrend('active_tasks', kpi({ previous: null, delta_pct: null, trend: 'unavailable' }))).toEqual({
      label: 'Срез на сейчас', tone: 'neutral',
    });
    expect(getDashboardTrend('receivables', kpi({ trend: 'up', delta_pct: 20 })).tone).toBe('negative');
  });

  it('uses the product KPI label instead of a backend shortcut', () => {
    const wrapper = mount(DashboardKpiCard, {
      props: { metric: 'receivables', kpi: kpi({ label: 'Долг', unit: 'byn' }) },
    });
    expect(wrapper.text()).toContain('Дебиторская задолженность');
    expect(wrapper.text()).not.toContain('Долг');
  });

  it('calls monthly stage events deal movement and never shows a cohort conversion', () => {
    const wrapper = mount(DashboardFunnel, {
      props: { stages: [
        { stage: 'proposals', label: 'Предложения', current: 1, conversion_from_previous_pct: 50 },
        { stage: 'sales', label: 'Продажи', current: 5, conversion_from_previous_pct: 500 },
      ] },
    });
    expect(wrapper.text()).toContain('Движение сделок');
    expect(wrapper.text()).not.toContain('Конверсия');
    expect(wrapper.text()).not.toContain('500%');
  });

  it('keeps graph selection usable with keyboard navigation', async () => {
    const wrapper = mount(DashboardSalesChart, {
      props: { series: [
        { date: '2026-09-01', revenue: 100, sales: 1 },
        { date: '2026-09-02', revenue: 200, sales: 2 },
      ] },
    });
    const chart = wrapper.get('svg');
    await chart.trigger('keydown', { key: 'ArrowRight' });
    expect(wrapper.text()).toContain('2 сент.');
    expect(wrapper.text()).toContain('200');
  });

  it('filters, expands, and sorts search requests without losing mobile cards', async () => {
    const queries = Array.from({ length: 12 }, (_, index) => ({
      provider: 'yandex_webmaster' as const,
      query: `запрос ${index + 1}`,
      clicks: index + 1,
      impressions: (index + 1) * 10,
      ctr: index + 1,
      avg_position: 12 - index,
    }));
    const wrapper = mount(DashboardSearchDemand, {
      props: { canManageIntegrations: false, demand: { ...freshDemand, queries } },
    });
    expect(wrapper.findAll('tbody tr')).toHaveLength(10);
    await wrapper.findAll('button').find(button => button.text().startsWith('Показать все'))!.trigger('click');
    expect(wrapper.findAll('tbody tr')).toHaveLength(12);
    await wrapper.findAll('button').find(button => button.text().startsWith('Средняя позиция'))!.trigger('click');
    expect(wrapper.find('th[aria-sort="ascending"]').text()).toContain('Средняя позиция');
  });

  it('exports all query rows to Excel-friendly CSV and formats provider durations', () => {
    const csv = buildSearchDemandCsv([
      { provider: 'yandex_webmaster', query: 'купить "кондиционер"', clicks: 8, impressions: 100, ctr: 8, avg_position: 3.4 },
      { provider: 'google_search_console', query: 'монтаж', clicks: 3, impressions: 50, ctr: 6, avg_position: null },
    ]);
    expect(csv.startsWith('\uFEFF')).toBe(true);
    expect(csv).toContain('"купить ""кондиционер"""');
    expect(csv.split('\r\n')).toHaveLength(4);
    expect(formatDurationSeconds(82)).toBe('1 мин 22 с');
  });
});
