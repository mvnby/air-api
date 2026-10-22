import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { nextTick } from 'vue';
const mocks = vi.hoisted(() => ({ overview: vi.fn(), stats: vi.fn(), leads: vi.fn() }));
vi.mock('../src/api', () => ({ api: { getDashboardOverview: mocks.overview, getDashboardStats: mocks.stats, getLeadsCounter: mocks.leads } }));
import ManagerHome from '../src/views/ManagerHome.vue';
import DashboardLoadingState from '../src/components/dashboard/DashboardLoadingState.vue';
import DashboardKpiGrid from '../src/components/dashboard/DashboardKpiGrid.vue';
import DashboardAdvertising from '../src/components/dashboard/DashboardAdvertising.vue';
import DashboardSiteSeo from '../src/components/dashboard/DashboardSiteSeo.vue';
import { clearManagerSession, managerSession } from '../src/services/manager-session';
import { managerStorefrontSelection } from '../src/services/manager-storefront-selection';
import { dashboardOperationsState, dashboardOverviewState, managerLeadsCounterState } from '../src/services/manager-dashboard-state';
import { inboxChangedEvent } from '../src/services/lead-inbox';
import type { DashboardOverviewResponse, ManagerAuthStatusResponse } from '../src/client';
enableAutoUnmount(afterEach);
const deferred = <T,>() => { let resolve!: (value: T) => void; let reject!: (reason: Error) => void; const promise = new Promise<T>((ok, fail) => { resolve = ok; reject = fail; }); return { promise, resolve, reject }; };
const auth = (extra: Partial<ManagerAuthStatusResponse> = {}): ManagerAuthStatusResponse => ({ username: 'owner', status: 'ok', staff_user_id: 1, tenant_id: 1, storefront_id: 1, capabilities: ['crm.manage'], is_system_tenant: true, ...extra });
const overview = (sales = 7): DashboardOverviewResponse => ({
  generated_at: new Date().toISOString(),
  period: { current: { start: '2026-10-01T00:00:00+03:00', end: '2026-10-23T00:00:00+03:00' }, previous: { start: '2026-09-01T00:00:00+03:00', end: '2026-09-23T00:00:00+03:00' } },
  kpis: Object.fromEntries(['sales', 'revenue', 'receivables', 'new_leads', 'installations', 'active_tasks'].map(key => [key, { label: key, current: sales, previous: null, delta_pct: null, trend: 'unavailable', unit: 'count' }])) as DashboardOverviewResponse['kpis'],
  sales_series: [], funnel: [], marketing: { status: 'unconfigured', providers: [] }, search_demand: { status: 'unconfigured', queries: [], providers: [] },
});
const emptyStats = { total_amount: 999999, new_leads_count: 0, bank_receipts_review_count: 0, bank_receipts_review: [], expiring_contracts: [], upcoming_touchpoints: [] };
let hidden = false;
beforeEach(() => {
  clearManagerSession();
  vi.clearAllMocks(); vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-10-23T10:00:00Z'));
  hidden = false;
  vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => hidden ? 'hidden' : 'visible');
  managerSession.auth.value = auth(); managerSession.isAuthenticated.value = true;
  mocks.overview.mockResolvedValue(overview()); mocks.stats.mockResolvedValue(emptyStats); mocks.leads.mockResolvedValue({ count: 3 });
});
afterEach(() => { clearManagerSession(); vi.useRealTimers(); vi.restoreAllMocks(); });

describe('Manager home freshness and retained content', () => {
  it('shows cold analytics as preparing while canonical CRM and actions are already available', async () => {
    const result = overview();
    result.marketing = { status: 'pending', providers: [{ provider: 'yandex_metrika', status: 'pending' }, { provider: 'yandex_direct', status: 'pending' }] };
    result.search_demand = { status: 'pending', queries: [], providers: [{ provider: 'yandex_webmaster', status: 'pending' }] };
    mocks.overview.mockResolvedValue(result);
    const wrapper = mount(ManagerHome); await flushPromises();
    expect(wrapper.findComponent(DashboardKpiGrid).props('kpis').sales.current).toBe(7);
    expect(wrapper.text()).toContain('3 входящих'); expect(wrapper.text()).not.toContain('999');
    expect(wrapper.find('template').exists()).toBe(false);
    await wrapper.get('#dashboard-tab-site-seo').trigger('click');
    expect(wrapper.text()).toContain('Готовится'); expect(wrapper.text()).toContain('Первый снимок');
    expect(wrapper.findAll('dd')).toHaveLength(0);
    await wrapper.get('#dashboard-tab-advertising').trigger('click');
    expect(wrapper.text()).toContain('Первый снимок готовится'); expect(wrapper.text()).not.toContain('За этот период рекламный кабинет');
  });

  it('retains every successful block during refresh and after errors, without a skeleton', async () => {
    const wrapper = mount(ManagerHome); await flushPromises();
    const next = deferred<DashboardOverviewResponse>(); mocks.overview.mockReturnValue(next.promise);
    const nextStats = deferred<typeof emptyStats>(); mocks.stats.mockReturnValue(nextStats.promise);
    window.dispatchEvent(new Event('focus')); await flushPromises();
    expect(wrapper.findComponent(DashboardLoadingState).exists()).toBe(false);
    expect(wrapper.findComponent(DashboardKpiGrid).exists()).toBe(true);
    expect(wrapper.text()).toContain('Обновляем'); expect(wrapper.text()).toContain('3 входящих');
    next.reject(new Error('offline')); nextStats.reject(new Error('offline')); await flushPromises();
    expect(wrapper.findComponent(DashboardKpiGrid).props('kpis').sales.current).toBe(7);
    expect(wrapper.text()).toContain('Показаны последние данные'); expect(wrapper.text()).toContain('Не удалось обновить часть проверок');
    expect(wrapper.text()).toContain('3 входящих');
  });

  it.each([401, 403])('clears former results if the server denies access (%s)', async status => {
    const wrapper = mount(ManagerHome); await flushPromises();
    mocks.overview.mockRejectedValue({ status }); mocks.stats.mockRejectedValue({ status }); mocks.leads.mockRejectedValue({ status });
    window.dispatchEvent(new Event(inboxChangedEvent)); await flushPromises();
    expect(wrapper.findComponent(DashboardKpiGrid).exists()).toBe(false);
    expect(dashboardOperationsState.data.value).toBeNull(); expect(managerLeadsCounterState.data.value).toBeNull();
    expect(wrapper.text()).not.toContain('3 входящих');
  });

  it('shows operational actions without waiting for the personal counter', async () => {
    const pending = deferred<{ count: number }>(); mocks.leads.mockReturnValue(pending.promise);
    mocks.stats.mockResolvedValue({ ...emptyStats, upcoming_touchpoints: [{ order_id: 42, customer_name: 'Срочный клиент', next_followup_date: '2020-01-01' }] });
    const wrapper = mount(ManagerHome); await flushPromises();
    expect(wrapper.text()).toContain('Просроченные касания'); expect(wrapper.text()).toContain('Срочный клиент');
    expect(wrapper.text()).not.toContain('Срочных действий нет.');
  });

  it('preserves the last result on SPA return and still refreshes it', async () => {
    const first = mount(ManagerHome); await flushPromises(); first.unmount();
    const pending = deferred<DashboardOverviewResponse>(); mocks.overview.mockReturnValue(pending.promise);
    const second = mount(ManagerHome); await flushPromises();
    expect(mocks.overview).toHaveBeenCalledTimes(2);
    expect(second.findComponent(DashboardLoadingState).exists()).toBe(false);
    expect(second.findComponent(DashboardKpiGrid).props('kpis').sales.current).toBe(7);
    pending.resolve(overview(8)); await flushPromises();
    expect(second.findComponent(DashboardKpiGrid).props('kpis').sales.current).toBe(8);
  });

  it('polls at 45 seconds only while visible, resumes on visibility/focus and cleans up on leave', async () => {
    const wrapper = mount(ManagerHome); await flushPromises();
    await vi.advanceTimersByTimeAsync(45_000); expect(mocks.overview).toHaveBeenCalledTimes(2);
    hidden = true; document.dispatchEvent(new Event('visibilitychange'));
    await vi.advanceTimersByTimeAsync(180_000); window.dispatchEvent(new Event('focus')); await flushPromises();
    expect(mocks.overview).toHaveBeenCalledTimes(2);
    hidden = false; document.dispatchEvent(new Event('visibilitychange')); await flushPromises();
    expect(mocks.overview).toHaveBeenCalledTimes(3);
    window.dispatchEvent(new Event('focus')); await flushPromises(); expect(mocks.overview).toHaveBeenCalledTimes(4);
    wrapper.unmount(); await vi.advanceTimersByTimeAsync(90_000); window.dispatchEvent(new Event('focus')); window.dispatchEvent(new Event(inboxChangedEvent));
    await flushPromises(); expect(mocks.overview).toHaveBeenCalledTimes(4);
  });

  it('does not begin a request while initially hidden', async () => {
    hidden = true; mount(ManagerHome); await flushPromises(); expect(mocks.overview).not.toHaveBeenCalled();
    hidden = false; document.dispatchEvent(new Event('visibilitychange')); await flushPromises(); expect(mocks.overview).toHaveBeenCalledOnce();
  });

  it('does not overlap reads even when focus and polling arrive together', async () => {
    const pending = deferred<DashboardOverviewResponse>(); mocks.overview.mockReturnValue(pending.promise);
    mount(ManagerHome); await flushPromises();
    window.dispatchEvent(new Event('focus'));
    await vi.advanceTimersByTimeAsync(135_000); expect(mocks.overview).toHaveBeenCalledOnce();
    // A stalled overview does not stop the independent operational/counter refreshes.
    expect(mocks.stats.mock.calls.length).toBeGreaterThan(1);
    pending.resolve(overview()); await flushPromises(); window.dispatchEvent(new Event(inboxChangedEvent)); await flushPromises();
    expect(mocks.overview).toHaveBeenCalledTimes(2);
  });

  it('queues one fresh read after an own change during an older read, with no overlap', async () => {
    const old = deferred<DashboardOverviewResponse>(); const oldCounter = deferred<{ count: number }>();
    mocks.overview.mockReturnValueOnce(old.promise).mockResolvedValue(overview(8));
    mocks.leads.mockReturnValueOnce(oldCounter.promise).mockResolvedValue({ count: 2 });
    const wrapper = mount(ManagerHome); await flushPromises();
    window.dispatchEvent(new Event(inboxChangedEvent)); window.dispatchEvent(new Event(inboxChangedEvent));
    await flushPromises(); expect(mocks.overview).toHaveBeenCalledOnce(); expect(mocks.leads).toHaveBeenCalledOnce();
    old.resolve(overview(7)); oldCounter.resolve({ count: 3 }); await flushPromises();
    expect(mocks.overview).toHaveBeenCalledTimes(2); expect(mocks.leads).toHaveBeenCalledTimes(2);
    expect(wrapper.findComponent(DashboardKpiGrid).props('kpis').sales.current).toBe(8);
    expect(wrapper.text()).toContain('2 входящих');
  });

  it.each(['hidden', 'unmounted', 'context'] as const)('drops a queued read if its subscriber becomes %s', async mode => {
    const old = deferred<DashboardOverviewResponse>(); mocks.overview.mockReturnValueOnce(old.promise);
    const wrapper = mount(ManagerHome); await flushPromises();
    window.dispatchEvent(new Event(inboxChangedEvent));
    if (mode === 'hidden') { hidden = true; document.dispatchEvent(new Event('visibilitychange')); }
    if (mode === 'unmounted') wrapper.unmount();
    if (mode === 'context') clearManagerSession();
    old.resolve(overview()); await flushPromises(); expect(mocks.overview).toHaveBeenCalledOnce();
  });

  it('shares the counter with the App badge including a just-completed initial read', async () => {
    await managerLeadsCounterState.refresh(5_000);
    mount(ManagerHome); await flushPromises(); expect(mocks.leads).toHaveBeenCalledOnce();
    window.dispatchEvent(new Event(inboxChangedEvent)); await flushPromises(); expect(mocks.leads).toHaveBeenCalledTimes(2);
  });

  it.each([
    ['user', () => { managerSession.auth.value = auth({ staff_user_id: 2, username: 'another' }); }],
    ['tenant', () => { managerSession.auth.value = auth({ tenant_id: 2 }); }],
    ['storefront', () => { managerSession.auth.value = auth({ storefront_id: 2 }); }],
    ['slug', () => { managerStorefrontSelection.selectedSlug.value = 'another'; }],
    ['permissions', () => { managerSession.auth.value = auth({ capabilities: ['crm.manage', 'analytics.manage'] }); }],
    ['role', () => { managerSession.auth.value = auth({ role: 'manager' }); }],
    ['system role', () => { managerSession.auth.value = auth({ is_system_tenant: false }); }],
  ])('clears all retained data on %s change and rejects the old response', async (_name, change) => {
    const first = mount(ManagerHome); await flushPromises(); first.unmount();
    const old = deferred<DashboardOverviewResponse>(); mocks.overview.mockReturnValueOnce(old.promise);
    void dashboardOverviewState.refresh(); await flushPromises();
    change();
    expect(dashboardOverviewState.data.value).toBeNull(); expect(dashboardOperationsState.data.value).toBeNull(); expect(managerLeadsCounterState.data.value).toBeNull();
    const current = deferred<DashboardOverviewResponse>(); mocks.overview.mockReturnValueOnce(current.promise);
    const second = mount(ManagerHome); await flushPromises();
    old.resolve(overview(999)); await flushPromises(); expect(second.findComponent(DashboardKpiGrid).exists()).toBe(false);
    current.resolve(overview(22)); await flushPromises(); expect(second.findComponent(DashboardKpiGrid).props('kpis').sales.current).toBe(22);
  });

  it('discards old personal counter and operational responses after logout', async () => {
    const counter = deferred<{ count: number }>(); const operations = deferred<typeof emptyStats>();
    mocks.leads.mockReturnValueOnce(counter.promise); mocks.stats.mockReturnValueOnce(operations.promise);
    const wrapper = mount(ManagerHome); await flushPromises();
    clearManagerSession();
    counter.resolve({ count: 999 }); operations.resolve({ ...emptyStats, bank_receipts_review_count: 999 }); await flushPromises();
    expect(managerLeadsCounterState.data.value).toBeNull(); expect(dashboardOperationsState.data.value).toBeNull();
    expect(wrapper.text()).not.toContain('999');
  });

  it('drops the personal counter when CRM capability is removed', async () => {
    mount(ManagerHome); await flushPromises(); expect(managerLeadsCounterState.data.value?.count).toBe(3);
    managerSession.auth.value = auth({ capabilities: [] }); await flushPromises();
    expect(managerLeadsCounterState.data.value).toBeNull();
    await vi.advanceTimersByTimeAsync(90_000); expect(mocks.leads).toHaveBeenCalledOnce();
  });

  it('does not read a mixed company/site context before the server identity matches', async () => {
    mount(ManagerHome); await flushPromises();
    managerStorefrontSelection.selectedTenantId.value = 2; await flushPromises();
    expect(dashboardOverviewState.data.value).toBeNull();
    await vi.advanceTimersByTimeAsync(90_000); expect(mocks.overview).toHaveBeenCalledOnce();
    managerSession.auth.value = auth({ tenant_id: 2 }); await flushPromises(); expect(mocks.overview).toHaveBeenCalledTimes(2);
  });

  it('clears retained data on logout while unmounted and never resurrects it after login', async () => {
    const wrapper = mount(ManagerHome); await flushPromises(); wrapper.unmount();
    clearManagerSession(); expect(dashboardOverviewState.data.value).toBeNull(); expect(managerLeadsCounterState.data.value).toBeNull();
    managerSession.auth.value = auth(); managerSession.isAuthenticated.value = true;
    const pending = deferred<DashboardOverviewResponse>(); mocks.overview.mockReturnValueOnce(pending.promise);
    const second = mount(ManagerHome); await flushPromises(); expect(second.findComponent(DashboardKpiGrid).exists()).toBe(false);
  });

  it('stops reads and drops content during a context switch or session recovery', async () => {
    const wrapper = mount(ManagerHome); await flushPromises();
    managerStorefrontSelection.switching.value = true; await nextTick();
    expect(wrapper.findComponent(DashboardKpiGrid).exists()).toBe(false);
    await vi.advanceTimersByTimeAsync(90_000); expect(mocks.overview).toHaveBeenCalledOnce();
    managerStorefrontSelection.switching.value = false; await flushPromises(); expect(mocks.overview).toHaveBeenCalledTimes(2);
    managerSession.recoveryRequired.value = true; await flushPromises();
    expect(dashboardOverviewState.data.value).toBeNull(); expect(managerLeadsCounterState.data.value).toBeNull();
    await vi.advanceTimersByTimeAsync(90_000); expect(mocks.overview).toHaveBeenCalledTimes(2);
  });

  it('shows source-specific periods and last success without replacing stale success with zeros', () => {
    const marketing = { status: 'stale' as const, providers: [{ provider: 'yandex_direct' as const, status: 'stale' as const, ad_spend: 123, currency: 'BYN', updated_at: '2026-10-22T09:00:00Z', last_attempt_at: '2026-10-23T09:00:00Z', next_retry_at: '2026-10-23T10:05:00Z', error_code: 'provider_timeout', period_start: '2026-10-01', period_end: '2026-10-22' }] };
    const wrapper = mount(DashboardAdvertising, { props: { marketing, canManageIntegrations: false } });
    expect(wrapper.text()).toContain('123'); expect(wrapper.text()).toContain('Период снимка: 1–21 окт.');
    expect(wrapper.text()).toContain('Последнее успешное обновление'); expect(wrapper.text()).toContain('Сохранены последние полученные показатели');
    expect(wrapper.text()).toContain('Следующая попытка'); expect(wrapper.text()).not.toContain('provider_timeout');
  });

  it('labels partial traffic and SEO independently while keeping a fresh provider usable', () => {
    const wrapper = mount(DashboardSiteSeo, { props: { canManageIntegrations: false,
      marketing: { status: 'stale', providers: [{ provider: 'yandex_metrika', status: 'fresh', visits: 88 }, { provider: 'google_analytics', status: 'pending' }] },
      searchDemand: { status: 'error', queries: [], providers: [{ provider: 'yandex_webmaster', status: 'error', error_code: 'timeout' }] },
    } });
    expect(wrapper.text()).toContain('88'); expect(wrapper.text()).toContain('Частично доступно');
    expect(wrapper.text()).toContain('Готовится'); expect(wrapper.text()).toContain('Источники недоступны');
    expect(wrapper.text()).not.toContain('За этот период поисковые системы не вернули запросов');
  });
});
