import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import LeadSourceReviewModal from '../src/components/leads/LeadSourceReviewModal.vue';

const sourceApi = vi.hoisted(() => ({ preview: vi.fn(), apply: vi.fn(), analyze: vi.fn() }));
vi.mock('../src/services/order-source-review', () => ({ orderSourceReviewApi: sourceApi }));

const preview = {
  order_id: 41,
  source_code: 'belzakupki', external_id: 'T-12', source_url: 'https://example.test/tender', title: 'Поставка',
  customer: { name: 'ООО Заказчик', inn: '123456789', type: 'company', email: 'office@example.test' },
  existing_customer_id: null, work_summary: 'Монтаж', equipment_details: '2 блока',
  objects: [{ address: 'Минск, Ленина, 1', equipment: [{ brand: 'Daikin', model: 'A1', quantity: 2 }] }],
  documents: [{ id: 'doc-1', name: 'ТЗ.pdf', download_url: '/api/manager/orders/41/source-documents/doc-1', extracted_text: 'Техническое задание' }],
  warnings: [],
};

describe('LeadSourceReviewModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sourceApi.preview.mockResolvedValue(preview);
    sourceApi.apply.mockResolvedValue({ order_id: 41, customer_id: 9, attachment_ids: [1], applied_fields: ['customer'] });
    sourceApi.analyze.mockRejectedValue(new Error('AI unavailable'));
  });

  it('requires explicit confirmation and sends reviewed data without a price', async () => {
    const wrapper = mount(LeadSourceReviewModal, { props: { open: true, orderId: 41, leadStatus: 'new_lead' } });
    await flushPromises();
    expect(wrapper.text()).toContain('ТЗ.pdf');
    expect(wrapper.find('input[placeholder*="Цен"]').exists()).toBe(false);
    expect(wrapper.get('button.btn-mini').attributes('disabled')).toBeDefined();

    await wrapper.findAll('input[type="checkbox"]').at(-1)!.setValue(true);
    await wrapper.get('button.btn-mini').trigger('click');

    expect(sourceApi.apply).toHaveBeenCalledWith(41, expect.objectContaining({
      customer_action: 'create', document_ids: ['doc-1'], objects: [{ address: 'Минск, Ленина, 1', equipment: [{ brand: 'Daikin', model: 'A1', quantity: 2 }] }],
    }));
    expect(wrapper.emitted('applied')?.[0]?.[0]).toEqual(expect.objectContaining({ orderId: 41, customerId: 9 }));
  });

  it('does not offer skip for a new lead', async () => {
    const wrapper = mount(LeadSourceReviewModal, { props: { open: true, orderId: 41, leadStatus: 'new_lead' } });
    await flushPromises();
    expect(wrapper.text()).not.toContain('Не менять клиента');
  });

  it('keeps the review visible when document analysis fails', async () => {
    const wrapper = mount(LeadSourceReviewModal, { props: { open: true, orderId: 41, leadStatus: 'new_lead' } });
    await flushPromises();
    await wrapper.findAll('button').find((button) => button.text() === 'Обработать ИИ')!.trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('AI unavailable');
    expect(wrapper.text()).toContain('ТЗ.pdf');
    expect(wrapper.find('input[placeholder="Название или имя"]').exists()).toBe(true);
  });
});
