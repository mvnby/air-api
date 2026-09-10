import { nextTick } from 'vue';
import { shallowMount, flushPromises, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import OrderEditDrawer from '../src/components/orders/OrderEditDrawer.vue';
import OrderCustomerContext from '../src/components/orders/OrderCustomerContext.vue';
import OrderProposalWorkspace from '../src/components/orders/OrderProposalWorkspace.vue';
import OrderDocumentsWorkspace from '../src/components/orders/OrderDocumentsWorkspace.vue';
import OrderPaymentsPanel from '../src/components/orders/OrderPaymentsPanel.vue';
import OrderWorkspaceHeader from '../src/components/orders/OrderWorkspaceHeader.vue';
import OrderWorkspaceNav from '../src/components/orders/OrderWorkspaceNav.vue';
import { ManagerOrdersService, ManagerMailService, ManagerSettingsService } from '../src/client';
import { ManagerOrderUsageService, CancelablePromise } from '../src/client';
import { managerSession } from '../src/services/manager-session';
import { managerStorefrontSelection } from '../src/services/manager-storefront-selection';
import type { ManagerOrderDetailResponse } from '../src/client';

const apiMock = vi.hoisted(() => ({
  getManagerInstallers: vi.fn(), listManagerServiceEstimates: vi.fn(), listSupplyRequests: vi.fn(),
}));
vi.mock('../src/api', () => ({ api: apiMock }));
vi.mock('../src/composables/useSmartStickyHeader', async () => {
  const { ref } = await import('vue');
  return { useSmartStickyHeader: () => ({ compact: ref(false), reset: vi.fn() }) };
});
vi.mock('../src/services/ui-feedback', () => ({ confirmDialog: vi.fn().mockResolvedValue(false), promptDialog: vi.fn() }));

const initialOrder = (): ManagerOrderDetailResponse => ({
  id: 395, title: 'Обслуживание', status: 'negotiation', workflow_type: 'maintenance',
  negotiation_status: 'awaiting_offer', execution_status: 'needs_schedule',
  created_at: '2026-09-10T08:00:00Z', is_paid: false,
  total_amount: 0, total_cost: 0, margin: 0, payments: [], documents: [],
  product_lines: [], service_lines: [],
  customer: { id: 12, name: 'Лаборатория', type: 'company' },
  proposals: [{ id: 25, name: 'Основное', status: 'draft', is_selected: true, is_archived: false,
    product_lines: [], service_lines: [], total_amount: 0 }],
} as ManagerOrderDetailResponse);
let wrapper: VueWrapper;
let stored: ManagerOrderDetailResponse;
const commit = (payload: any) => {
  stored = { ...stored, ...payload, delivery_address: payload.customer_delivery_address ?? stored.delivery_address };
  if (payload.services) stored.proposals![0] = { ...stored.proposals![0]!, service_lines: payload.services };
  return structuredClone(stored);
};
const mountDrawer = async () => {
  wrapper = shallowMount(OrderEditDrawer, {
    props: { modelValue: false, order: stored, onUpdated: (order: ManagerOrderDetailResponse) => { void wrapper.setProps({ order }); } },
  });
  await wrapper.setProps({ modelValue: true });
  await flushPromises();
};
const customer = () => wrapper.findComponent(OrderCustomerContext);
const header = () => wrapper.findComponent(OrderWorkspaceHeader);
const payments = () => wrapper.findComponent(OrderPaymentsPanel);
const openDocuments = async () => {
  wrapper.findComponent(OrderWorkspaceNav).vm.$emit('select', 'documents');
  await nextTick();
};

beforeEach(() => {
  vi.useFakeTimers();
  Object.values(apiMock).forEach((mock) => mock.mockResolvedValue({ items: [] }));
  localStorage.clear(); sessionStorage.clear();
  stored = initialOrder();
  vi.spyOn(ManagerMailService, 'listManagerOrderOutgoingEmails').mockResolvedValue({ items: [] } as any);
  vi.spyOn(ManagerOrdersService, 'patchManagerOrder').mockImplementation(async (_id, payload) => commit(payload));
});
afterEach(() => { wrapper?.unmount(); vi.restoreAllMocks(); vi.useRealTimers(); });

describe('order drawer autosave integration', () => {
  it('counts opening once with the hydrated scenario, before any user edit', async () => {
    managerSession.isAuthenticated.value = true;
    managerSession.auth.value = { tenant_id: 1, staff_user_id: 99, username: 'usage-test' } as any;
    managerStorefrontSelection.selectedSlug.value = 'main';
    const record = vi.spyOn(ManagerOrderUsageService, 'recordManagerOrderUsage')
      .mockImplementation(() => new CancelablePromise((resolve) => resolve({ accepted: 1 })));
    try {
      await mountDrawer();
      await vi.advanceTimersByTimeAsync(2_000);
      expect(record).toHaveBeenCalledOnce();
      expect(record.mock.calls[0]?.[0].events).toEqual([{
        metric: 'order_open', workflow: 'maintenance', party_kind: 'company', viewport: 'desktop',
      }]);
      expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    } finally {
      managerSession.isAuthenticated.value = false;
      managerSession.auth.value = null;
      managerStorefrontSelection.selectedSlug.value = null;
    }
  });
  it('flushes edits before navigating to the customer profile', async () => {
    await mountDrawer();
    customer().vm.$emit('update:comment', 'Сохранить перед переходом');
    await nextTick();
    expect(await customer().props('beforeNavigate')!()).toBe(true);
    expect(stored.comment).toBe('Сохранить перед переходом');
    expect(wrapper.emitted('update:modelValue')).toEqual([[false]]);
  });
  it('persists a suggested address and added service before generating a contract', async () => {
    await mountDrawer();
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    customer().vm.$emit('update:deliveryAddress', 'Витебск, Свердлова, 15');
    const commercial = wrapper.findComponent(OrderProposalWorkspace).props('commercial');
    commercial.serviceLines.value.push({ service_id: null, title: 'Обслуживание', quantity: 11, price: 220, cost: 0 });
    await nextTick();
    await openDocuments();
    const beforeGenerate = wrapper.findComponent(OrderDocumentsWorkspace).props('beforeGenerate')!;
    expect(await beforeGenerate('contract')).toEqual({ mutated: true });
    expect(ManagerOrdersService.patchManagerOrder).toHaveBeenCalledOnce();
    expect(ManagerOrdersService.patchManagerOrder).toHaveBeenCalledWith(395, expect.objectContaining({
      customer_delivery_address: 'Витебск, Свердлова, 15', line_proposal_id: 25,
      services: [expect.objectContaining({ title: 'Обслуживание', quantity: 11, price: 220, proposal_id: 25 })],
    }));
    expect(header().props('dirty')).toBe(false);
    expect(header().props('saveStatusText')).toBe('Сохранено');
  });

  it('does not autosave a saved EUR deal while the unavailable FX rate loads', async () => {
    stored = {
      ...stored,
      target_currency: 'EUR',
      target_currency_amount: 1_250.75,
    };
    vi.spyOn(ManagerSettingsService, 'getFxRate').mockResolvedValue({
      usd_byn: 3.2,
      eur_byn: null,
    } as any);

    await mountDrawer();
    await vi.advanceTimersByTimeAsync(1_000);

    expect(payments().props('targetCurrency')).toBe('EUR');
    expect(payments().props('targetCurrencyAmount')).toBe(1_250.75);
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    expect(header().props('dirty')).toBe(false);
  });

  it('saves a comment on a saved EUR deal while its live FX rate is unavailable', async () => {
    stored = {
      ...stored,
      target_currency: 'EUR',
      target_currency_amount: 1_250.75,
    };
    vi.spyOn(ManagerSettingsService, 'getFxRate').mockResolvedValue({
      usd_byn: 3.2,
      eur_byn: null,
    } as any);

    await mountDrawer();
    customer().vm.$emit('update:comment', 'Комментарий без изменения суммы');
    await nextTick();
    await vi.advanceTimersByTimeAsync(1_000);

    expect(ManagerOrdersService.patchManagerOrder).toHaveBeenCalledWith(395, {
      comment: 'Комментарий без изменения суммы',
    });
    expect(stored.target_currency).toBe('EUR');
    expect(stored.target_currency_amount).toBe(1_250.75);
  });

  it('blocks an edited currency amount while its live FX rate is unavailable', async () => {
    stored = {
      ...stored,
      target_currency: 'EUR',
      target_currency_amount: 1_250.75,
    };
    vi.spyOn(ManagerSettingsService, 'getFxRate').mockResolvedValue({
      usd_byn: 3.2,
      eur_byn: null,
    } as any);

    await mountDrawer();
    payments().vm.$emit('update:targetCurrencyAmount', 1_300);
    await nextTick();
    await vi.advanceTimersByTimeAsync(1_000);

    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    expect(header().props('dirty')).toBe(true);
  });

  it('keeps input typed during a slow save after the parent publishes the old response', async () => {
    let finish: () => void = () => {};
    vi.mocked(ManagerOrdersService.patchManagerOrder).mockImplementationOnce((_id, payload) => {
      const first = commit(payload);
      return new Promise((resolve) => { finish = () => resolve(first); }) as any;
    });
    await mountDrawer();
    customer().vm.$emit('update:comment', 'Первый текст');
    await nextTick();
    await vi.advanceTimersByTimeAsync(750);
    customer().vm.$emit('update:comment', 'Новый текст во время запроса');
    await nextTick();
    finish();
    await flushPromises();
    expect(customer().props('comment')).toBe('Новый текст во время запроса');
    expect(ManagerOrdersService.patchManagerOrder).toHaveBeenCalledTimes(2);
    expect(stored.comment).toBe('Новый текст во время запроса');
    expect(header().props('dirty')).toBe(false);
  });

  it('keeps manual mode dirty, prevents document creation, and still supports Save', async () => {
    await mountDrawer();
    header().vm.$emit('toggle-autosave');
    customer().vm.$emit('update:deliveryAddress', 'Минск, Ленина, 1');
    await nextTick();
    await vi.advanceTimersByTimeAsync(1000);
    await openDocuments();
    const beforeGenerate = wrapper.findComponent(OrderDocumentsWorkspace).props('beforeGenerate')!;
    expect(await beforeGenerate('invoice')).toBe(false);
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    header().vm.$emit('save');
    await flushPromises();
    expect(stored.delivery_address).toBe('Минск, Ленина, 1');
    expect(header().props('dirty')).toBe(false);
  });
});
