import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  overview: vi.fn(),
  stats: vi.fn(),
  leads: vi.fn(),
}));

vi.mock('../src/api', () => ({
  api: {
    getDashboardOverview: mocks.overview,
    getDashboardStats: mocks.stats,
    getLeadsCounter: mocks.leads,
  },
}));

import ManagerHome from '../src/views/ManagerHome.vue';

const operationalStats = {
  total_amount: 0,
  new_leads_count: 0,
  bank_receipts_review_count: 1,
  bank_receipts_review: [{
    id: 42, amount: 250, currency: 'BYN', payer_name: 'ООО Тест',
    payer_unp: '123456789', payment_document_number: '15', payment_purpose: 'Оплата заказа',
    candidate_order_ids: [77],
  }],
  expiring_contracts: [{
    contract_id: 5, customer_id: 8, customer_name: 'Клиент Тест',
    number: 'Д-15', valid_until: '2020-01-01', edit_url: 'https://example.test/contract/5',
  }],
  upcoming_touchpoints: [{
    order_id: 77, customer_name: 'Клиент Тест', phone: '+375291234567',
    title: 'Перезвонить', next_followup_date: '2020-01-01',
  }],
};

describe('ManagerHome operational resilience', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    mocks.overview.mockRejectedValue(new Error('overview unavailable'));
    mocks.stats.mockResolvedValue(operationalStats);
    mocks.leads.mockResolvedValue({ count: 0 });
  });

  it('keeps verified operational lists when the overview request fails', async () => {
    const wrapper = mount(ManagerHome);
    await flushPromises();

    expect(wrapper.text()).toContain('Не удалось загрузить сводку');
    expect(wrapper.text()).toContain('ООО Тест');
    expect(wrapper.text()).toContain('Клиент Тест · Д-15');
    expect(wrapper.text()).toContain('Заказ #77');
  });

  it('does not claim there are no urgent actions when lead counter loading fails', async () => {
    mocks.stats.mockResolvedValue({ ...operationalStats, bank_receipts_review_count: 0, bank_receipts_review: [], expiring_contracts: [], upcoming_touchpoints: [] });
    mocks.leads.mockRejectedValue(new Error('counter unavailable'));
    const wrapper = mount(ManagerHome);
    await flushPromises();

    expect(wrapper.text()).toContain('Часть проверок недоступна');
    expect(wrapper.text()).not.toContain('Срочных действий нет.');
  });
});
