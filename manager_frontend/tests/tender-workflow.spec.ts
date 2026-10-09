import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
const api = vi.hoisted(() => ({ get: vi.fn(), update: vi.fn(), candidates: vi.fn(), link: vi.fn(), unlink: vi.fn() }));
vi.mock('../src/services/tender-workflow', () => ({ tenderWorkflowApi: api, tenderStageLabels: {
  price_request: 'Запрос цены', price_sent: 'Ценовое предложение отправлено', announced: 'Объявлена / готовим заявку', submitted: 'Заявка подана', completed: 'Завершена',
} }));
import TenderWorkflowPanel from '../src/components/orders/TenderWorkflowPanel.vue';
const workflow = { order_id: 22, stage: 'announced', deadline_at: '2026-10-15T11:30:00Z', deadline_manual: false, price_enquiry: null, publications: [], history: [] };
beforeEach(() => { vi.clearAllMocks(); api.get.mockResolvedValue({ ...workflow }); api.update.mockResolvedValue({ ...workflow, deadline_manual: true }); api.link.mockResolvedValue({ ...workflow, price_enquiry: { order_id: 11, title: 'Цена', status: 'negotiation', archived: true } }); api.unlink.mockResolvedValue({ ...workflow }); });
describe('Tender workflow', () => {
  it('shows current deadline in Minsk and explicitly saves changed stage with its own date', async () => {
    const wrapper = mount(TenderWorkflowPanel, { props: { orderId: 22 } }); await flushPromises();
    expect(wrapper.text()).toContain('Объявлена / готовим заявку');
    await wrapper.get('button').trigger('click');
    expect(wrapper.get('input[type="datetime-local"]').element).toHaveProperty('value', '2026-10-15T14:30');
    await wrapper.get('select').setValue('submitted');
    expect(wrapper.get('input[type="datetime-local"]').element).toHaveProperty('value', '');
    await wrapper.get('input[type="datetime-local"]').setValue('2026-10-20T09:00');
    await wrapper.get('form').trigger('submit'); await flushPromises();
    expect(api.update).toHaveBeenCalledWith(22, { stage: 'submitted', deadline_at: '2026-10-20T06:00:00.000Z' });
    wrapper.unmount();
  });
  it('finds archived qualified earlier enquiry and explicitly marks/links it without matching automatically', async () => {
    api.candidates.mockResolvedValue([{ order_id: 11, title: 'Цена', external_id: 'old-11', status: 'negotiation', archived: true, stage: null, deadline_at: null }]);
    const wrapper = mount(TenderWorkflowPanel, { props: { orderId: 22 } }); await flushPromises();
    expect(api.candidates).not.toHaveBeenCalled(); expect(api.link).not.toHaveBeenCalled();
    await wrapper.get('button').trigger('click');
    await wrapper.get('input[placeholder]').setValue('Цена');
    await wrapper.findAll('form')[1]!.trigger('submit'); await flushPromises();
    expect(api.candidates).toHaveBeenCalledWith(22, 'Цена');
    expect(wrapper.text()).toContain('в архиве');
    await wrapper.get('.candidate button').trigger('click'); await flushPromises();
    expect(api.update).toHaveBeenCalledWith(11, { stage: 'price_request', deadline_at: null });
    expect(api.link).toHaveBeenCalledWith(22, 11);
    expect(wrapper.get('a').attributes('href')).toBe('/manager/orders/kanban?orderId=11');
    expect(wrapper.text()).toContain('Снять связь с запросом цены');
    await wrapper.findAll('button').find(button => button.text().includes('Снять связь'))!.trigger('click'); await flushPromises();
    expect(api.unlink).toHaveBeenCalledWith(22); wrapper.unmount();
  });
  it('keeps rejected associations inline and does not fabricate saved context', async () => {
    api.candidates.mockResolvedValue([{ order_id: 11, title: 'Цена', stage: 'price_sent', status: 'new_lead', archived: false }]);
    api.link.mockRejectedValueOnce(new Error('Связь изменилась'));
    const wrapper = mount(TenderWorkflowPanel, { props: { orderId: 22 } }); await flushPromises();
    await wrapper.get('button').trigger('click'); await wrapper.findAll('form')[1]!.trigger('submit'); await flushPromises();
    await wrapper.get('.candidate button').trigger('click'); await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('Связь изменилась');
    expect(wrapper.emitted('changed')).toBeUndefined(); expect(api.update).not.toHaveBeenCalled(); wrapper.unmount();
  });
});
