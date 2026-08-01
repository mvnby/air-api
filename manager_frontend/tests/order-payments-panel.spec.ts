import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  BankReceiptResponse,
  ManagerOrderDetailResponse,
  PaymentResponse,
} from '../src/client';
import { ManagerMailService, ManagerOrdersService } from '../src/client';
import OrderPaymentsPanel from '../src/components/orders/OrderPaymentsPanel.vue';

vi.mock('../src/client', () => ({
  ManagerMailService: {
    listManagerBankReceipts: vi.fn(),
    attachManagerBankReceipt: vi.fn(),
  },
  ManagerOrdersService: {
    addManagerOrderPayment: vi.fn(),
    deleteManagerOrderPayment: vi.fn(),
  },
}));

const payment: PaymentResponse = {
  id: 801,
  amount: 500,
  currency: 'BYN',
  date: '2026-07-31T12:00:00Z',
  type: 'prepayment',
  created_at: '2026-07-31T12:00:00Z',
};

const receipt: BankReceiptResponse = {
  id: 901,
  status: 'requires_review',
  operation_type: 'credit',
  sender_email: 'bank@example.test',
  subject: 'Поступление',
  fingerprint: 'receipt-901',
  received_at: '2026-07-31T11:30:00Z',
  amount: 1_200,
  currency: 'BYN',
  payer_name: 'ООО Климат',
  payer_unp: '190000001',
  payment_document_number: '42',
  payment_purpose: 'Оплата по заказу',
  raw_body: 'test fixture',
  created_at: '2026-07-31T11:31:00Z',
};

const order = {
  id: 42,
  status: 'new_lead',
  created_at: '2026-07-31T10:00:00Z',
  total_amount: 2_000,
  total_cost: 1_200,
  margin: 800,
  is_paid: false,
  customer: {
    id: 11,
    name: 'ООО Климат',
    inn: '190000001',
  },
  needs_attention: false,
  awaiting_measurement: false,
  client_thinking: false,
  ready_for_execution: false,
} as ManagerOrderDetailResponse;

const listReceiptsMock = vi.mocked(ManagerMailService.listManagerBankReceipts);
const attachReceiptMock = vi.mocked(ManagerMailService.attachManagerBankReceipt);
const addPaymentMock = vi.mocked(ManagerOrdersService.addManagerOrderPayment);
const deletePaymentMock = vi.mocked(ManagerOrdersService.deleteManagerOrderPayment);
const mountedWrappers: VueWrapper[] = [];

const mountPanel = (payments: PaymentResponse[] = []) => {
  const wrapper = mount(OrderPaymentsPanel, {
    attachTo: document.body,
    props: {
      order,
      expanded: true,
      payments,
      enableCurrency: false,
      targetCurrency: null,
      targetCurrencyAmount: null,
      currentFxRate: { usd_byn: 3.25, eur_byn: 3.55, source: 'nbrb' },
      isB2cCustomer: false,
      total: 2_000,
      totalPayments: payments.reduce((sum, item) => sum + item.amount, 0),
      balanceDue: 1_500,
      margin: 800,
      calculatedTargetCurrencyPayments: 0,
      targetCurrencyBalanceDue: 0,
    },
  });
  mountedWrappers.push(wrapper);
  return wrapper;
};

beforeEach(() => {
  vi.clearAllMocks();
  listReceiptsMock.mockResolvedValue({ items: [receipt], total: 1 });
  attachReceiptMock.mockResolvedValue(receipt);
  addPaymentMock.mockResolvedValue([payment]);
  deletePaymentMock.mockResolvedValue([]);
});

afterEach(() => {
  for (const wrapper of mountedWrappers.splice(0)) wrapper.unmount();
  document.body.innerHTML = '';
});

describe('OrderPaymentsPanel', () => {
  it('loads review candidates by customer UNP and attaches a receipt to the order', async () => {
    const wrapper = mountPanel();
    await flushPromises();

    expect(listReceiptsMock).toHaveBeenCalledWith(
      1,
      20,
      'requires_review',
      order.customer?.inn,
    );
    await wrapper.get(`[data-testid="attach-receipt-${receipt.id}"]`).trigger('click');
    await flushPromises();

    expect(attachReceiptMock).toHaveBeenCalledWith(receipt.id, {
      order_id: order.id,
      payment_type: 'postpayment',
    });
    expect(wrapper.emitted('reload')).toEqual([[order.id]]);
    expect(wrapper.emitted('toast')).toContainEqual([{
      message: 'Поступление прикреплено к заказу',
      type: 'success',
    }]);
    expect(listReceiptsMock).toHaveBeenCalledTimes(2);
  });

  it('adds a payment and returns the updated payment projection to the drawer', async () => {
    const wrapper = mountPanel();
    await flushPromises();

    await wrapper.get('[data-testid="payment-amount"]').setValue('500');
    await wrapper.get('[data-testid="add-payment"]').trigger('click');
    await flushPromises();

    expect(addPaymentMock).toHaveBeenCalledWith(order.id, {
      amount: 500,
      type: 'prepayment',
      currency: 'BYN',
    });
    expect(wrapper.emitted('update:payments')).toEqual([[[payment]]]);
    expect(wrapper.emitted('toast')).toContainEqual([{
      message: 'Платеж добавлен',
      type: 'success',
    }]);
  });

  it('requires an available exchange rate and keeps invalid payments local', async () => {
    const wrapper = mount(OrderPaymentsPanel, {
      props: {
        order,
        expanded: true,
        payments: [],
        enableCurrency: true,
        targetCurrency: 'EUR',
        targetCurrencyAmount: null,
        currentFxRate: { usd_byn: 3.25, eur_byn: null, source: 'manual' },
        isB2cCustomer: true,
        total: 2_000,
        totalPayments: 0,
        balanceDue: 2_000,
        margin: 800,
        calculatedTargetCurrencyPayments: 0,
        targetCurrencyBalanceDue: 0,
      },
    });
    mountedWrappers.push(wrapper);
    await flushPromises();

    await wrapper.get('[data-testid="payment-amount"]').setValue('100');
    await wrapper.get('[data-testid="add-payment"]').trigger('click');
    await flushPromises();

    expect(addPaymentMock).not.toHaveBeenCalled();
    expect(wrapper.emitted('toast')).toEqual([[{
      message: 'Для выбранной валюты нет доступного курса',
      type: 'error',
    }]]);
  });

  it('deletes a payment only after the inline confirmation', async () => {
    const wrapper = mountPanel([payment]);
    await flushPromises();

    await wrapper.get('button[title="Удалить платеж"]').trigger('click');
    expect(deletePaymentMock).not.toHaveBeenCalled();
    await wrapper.get(`[data-testid="delete-payment-${payment.id}"]`).trigger('click');
    await flushPromises();

    expect(deletePaymentMock).toHaveBeenCalledWith(order.id, payment.id);
    expect(wrapper.emitted('update:payments')).toEqual([[[]]]);
    expect(wrapper.emitted('toast')).toContainEqual([{
      message: 'Платеж удален',
      type: 'success',
    }]);
  });
});
