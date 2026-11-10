import { mount, flushPromises } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ManagerOrderEquipmentService } from '../src/client';
import ConsumerEquipmentRegistry from '../src/features/documents/components/ConsumerEquipmentRegistry.vue';
import { createDefaultConsumerDocumentTerms } from '../src/features/documents/model/consumer-document-terms';

const first = { equipment_id: 1, version: 'card-1', customer_id: 11, customer_branch_id: null,
  catalog_product_id: null, equipment_source: 'customer_owned', brand: 'TEST', model: 'TEST-09', serial: 'TEST-SN-001', roles: ['installation'] };
const second = { ...first, equipment_id: 2, serial: 'TEST-SN-002', version: 'card-2' };
const state = { order_id: 42, version: 'order-1', items: [first, second], total: 2, manager_url: '/orders/42' };
const terms = { ...createDefaultConsumerDocumentTerms(), equipment_brand: 'TEST', equipment_model: 'TEST-09', equipment_serial: 'TEST-SN-001' };
afterEach(() => vi.restoreAllMocks());

describe('saved physical equipment in consumer documents', () => {
  it('selects one of two physical units of the same model by ID and serial', async () => {
    vi.spyOn(ManagerOrderEquipmentService, 'getManagerOrderEquipmentIdentities').mockResolvedValue(state);
    const wrapper = mount(ConsumerEquipmentRegistry, { props: { orderId: 42, terms } });
    await flushPromises();
    await wrapper.get('select').setValue('2');
    expect(wrapper.emitted('updateTerms')?.at(-1)?.[0]).toMatchObject({ equipment_id: 2, equipment_serial: 'TEST-SN-002' });
    wrapper.unmount();
  });
  it('keeps the saved snapshot until the operator explicitly refreshes from the card', async () => {
    vi.spyOn(ManagerOrderEquipmentService, 'getManagerOrderEquipmentIdentities').mockResolvedValue({ ...state,
      items: [{ ...first, model: 'CHANGED-18', serial: 'NEW-SERIAL' }] });
    const wrapper = mount(ConsumerEquipmentRegistry, { props: { orderId: 42, terms: { ...terms, equipment_id: 1 } } });
    await flushPromises();
    expect(wrapper.emitted('updateTerms')).toBeUndefined();
    await wrapper.get('[data-testid="consumer-equipment-refresh"]').trigger('click');
    await flushPromises();
    expect(wrapper.emitted('updateTerms')?.at(-1)?.[0]).toMatchObject({ equipment_id: 1, equipment_model: 'CHANGED-18', equipment_serial: 'NEW-SERIAL' });
    wrapper.unmount();
  });
  it('retries the exact save after a timeout and adopts legacy snapshot data without retyping', async () => {
    vi.spyOn(ManagerOrderEquipmentService, 'getManagerOrderEquipmentIdentities').mockResolvedValue(state);
    const save = vi.spyOn(ManagerOrderEquipmentService, 'saveManagerOrderEquipmentIdentity')
      .mockRejectedValueOnce(new Error('Timeout'))
      .mockResolvedValueOnce({ result: { order_id: 42, equipment_id: 1, equipment: first, version: 'order-2', manager_url: '/orders/42' }, replayed: true });
    const wrapper = mount(ConsumerEquipmentRegistry, { props: { orderId: 42, terms, sourceDocumentId: 614 } });
    await flushPromises();
    await wrapper.get('[data-testid="consumer-equipment-save"]').trigger('click');
    await flushPromises();
    await wrapper.get('[data-testid="consumer-equipment-save"]').trigger('click');
    await flushPromises();
    expect(save.mock.calls[0]).toEqual(save.mock.calls[1]);
    expect(save.mock.calls[0]?.[1]).toMatchObject({ source_document_id: 614, model: 'TEST-09', serial: 'TEST-SN-001', expected_version: 'order-1' });
    expect(wrapper.emitted('updateTerms')?.at(-1)?.[0]).toMatchObject({ equipment_id: 1, equipment_model: 'TEST-09' });
    wrapper.unmount();
  });
});
