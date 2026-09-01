import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { BankReceiptResponse } from '../src/client';
import { ManagerMailService } from '../src/client';
import BankReceiptsView from '../src/views/BankReceiptsView.vue';

vi.mock('../src/client', () => ({
  ManagerMailService: {
    listManagerBankReceipts: vi.fn(),
    attachManagerBankReceipt: vi.fn(),
  },
}));

const receipt: BankReceiptResponse = {
  id: 141127,
  status: 'requires_review',
  operation_type: 'incoming_funds',
  sender_email: 'bank@example.test',
  subject: 'Бюджетное поступление',
  fingerprint: 'budget-receipt-141127',
  received_at: '2026-09-01T10:00:00Z',
  amount: 1460,
  currency: 'BYN',
  payer_name: 'Главное управление МФ Республики Беларусь по Витебской области',
  payer_unp: '300594330',
  payment_document_number: '141127',
  payment_purpose: 'Оплата через бюджет',
  raw_body: 'test fixture',
  allocated_amount: 0,
  unallocated_amount: 1460,
  allocation_count: 0,
  created_at: '2026-09-01T10:01:00Z',
};

const listReceiptsMock = vi.mocked(ManagerMailService.listManagerBankReceipts);
const attachReceiptMock = vi.mocked(ManagerMailService.attachManagerBankReceipt);
const mountedWrappers: VueWrapper[] = [];

const mountView = async (items: BankReceiptResponse[] = [receipt]) => {
  listReceiptsMock.mockResolvedValue({ items, total: items.length, page: 1, limit: 50 });
  const wrapper = mount(BankReceiptsView, { attachTo: document.body });
  mountedWrappers.push(wrapper);
  await flushPromises();
  return wrapper;
};

beforeEach(() => {
  vi.clearAllMocks();
  attachReceiptMock.mockResolvedValue({
    ...receipt,
    status: 'matched',
    matched_order_id: 279,
    matched_payment_id: 801,
    allocated_amount: 1460,
    unallocated_amount: 0,
    allocation_count: 1,
  });
});

afterEach(() => {
  for (const wrapper of mountedWrappers.splice(0)) wrapper.unmount();
  document.body.innerHTML = '';
});

describe('BankReceiptsView', () => {
  it('attaches a budget payer receipt to an explicitly entered order', async () => {
    const wrapper = await mountView();

    await wrapper.get(`[data-testid="manual-attach-start-${receipt.id}"]`).trigger('click');
    await wrapper.get(`[data-testid="manual-attach-order-${receipt.id}"]`).setValue('279');
    await wrapper.get(`[data-testid="manual-attach-submit-${receipt.id}"]`).trigger('click');
    await flushPromises();

    expect(attachReceiptMock).toHaveBeenCalledWith(receipt.id, {
      order_id: 279,
      payment_type: 'postpayment',
    });
    expect(wrapper.text()).toContain(`Поступление #${receipt.id} прикреплено к заказу #279.`);
    expect(listReceiptsMock).toHaveBeenCalledTimes(2);
  });

  it('keeps invalid order ids local and does not mutate the receipt', async () => {
    const wrapper = await mountView();

    await wrapper.get(`[data-testid="manual-attach-start-${receipt.id}"]`).trigger('click');
    await wrapper.get(`[data-testid="manual-attach-order-${receipt.id}"]`).setValue('0');
    await wrapper.get(`[data-testid="manual-attach-submit-${receipt.id}"]`).trigger('click');

    expect(attachReceiptMock).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('Укажите корректный номер заказа.');
  });

  it.each(['matched', 'partially_allocated', 'void', 'closed_orders', 'non_order_income', 'parse_failed'])(
    'hides direct attach for %s receipts',
    async (status) => {
      const wrapper = await mountView([{ ...receipt, status }]);

      expect(wrapper.find(`[data-testid="manual-attach-start-${receipt.id}"]`).exists()).toBe(false);
    },
  );
});
