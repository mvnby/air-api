import { describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { commercialTermsApi, mergeCommercialDocumentDefaults } from '../src/services/commercial-terms-api';
import { createDefaultBusinessDocumentTerms } from '../src/features/documents/model/business-document-terms';
import CommercialTermsPanel from '../src/components/orders/CommercialTermsPanel.vue';

vi.mock('../src/services/commercial-terms-api', async (original) => {
  const actual = await original<typeof import('../src/services/commercial-terms-api')>();
  return { ...actual, commercialTermsApi: { read: vi.fn(), update: vi.fn(), defaults: vi.fn() } };
});

const fixture = {
  order_id: 9, revision: 0, customer_requested: [{kind:'payment' as const, source:'Письмо', evidence:'Оплата через 50 дней после выполнения работ', share_percent:null, due_days:50, day_kind:null, due_event:'after_work', trigger_text:'после выполнения работ', deadline:null, issues:['Вид дней не указан']}],
  proposed: null, suggested: null, confirmed: false, warnings: [],
};

describe('commercial terms', () => {
  it('preserves manual schedule edits when defaults arrive late', () => {
    const baseline = createDefaultBusinessDocumentTerms();
    const current = { ...baseline, payment_schedule: [{...baseline.payment_schedule[0]!, share_percent:50}, {...baseline.payment_schedule[0]!, share_percent:50, due_event:'after_work' as const}] };
    const result = mergeCommercialDocumentDefaults(current, baseline, { payment_schedule:[{ ...baseline.payment_schedule[0]!, due_days:50, due_event:'after_work', due_day_kind:'working' }], delivery_deadline:'2026-10-12' });
    expect(result.payment_schedule).toEqual(current.payment_schedule);
    expect(result.delivery_deadline).toBe('2026-10-12');
  });
  it('shows source ambiguity and requires an explicit proposed schedule before confirmation', async () => {
    vi.mocked(commercialTermsApi.read).mockResolvedValue(fixture);
    const wrapper = mount(CommercialTermsPanel, { props:{orderId:9} });
    await flushPromises();
    expect(wrapper.text()).toContain('Вид дней не указан');
    await wrapper.findAll('button').find((button) => button.text() === 'Подготовить наш вариант')!.trigger('click');
    await wrapper.findAll('button').find((button) => button.text() === 'Подтвердить для документов')!.trigger('click');
    expect(commercialTermsApi.update).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('График оплаты должен составлять ровно 100%');
    wrapper.unmount();
  });
});

it('normalizes decimal shares and retains workflow scenario for partial source suggestions', () => {
  const current = createDefaultBusinessDocumentTerms('service_work');
  const result = mergeCommercialDocumentDefaults(current, current, {contract_scenario:null, payment_schedule:[{share_percent:'100' as unknown as number, due_event:'after_work', due_days:50, due_day_kind:'working', note:null}]});
  expect(result.contract_scenario).toBe('installation');
  expect(result.payment_schedule[0]?.share_percent).toBe(100);
});
