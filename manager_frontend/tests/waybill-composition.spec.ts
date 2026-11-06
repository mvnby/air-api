import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ManagerDocumentSystemService, type WaybillCompositionSource, type WaybillComposition_Input } from '../src/client';
import NativeWaybillComposition from '../src/features/documents/components/NativeWaybillComposition.vue';

const source = (id: number): WaybillCompositionSource => ({
  source_revision: (id === 1 ? 'a' : 'b').repeat(64),
  lines: [{ order_product_line_id: id, title: 'Комплект', product_id: 11, country: 'Китай',
    quantity: 2, unit_price: '2470.00', components: null }],
});
afterEach(() => vi.restoreAllMocks());

describe('native waybill composition', () => {
  it('ignores an older order response after switching orders', async () => {
    let finish!: (value: WaybillCompositionSource) => void;
    const late = new Promise<WaybillCompositionSource>(resolve => { finish = resolve; });
    vi.spyOn(ManagerDocumentSystemService, 'getManagerWaybillComposition').mockImplementationOnce(async () => late).mockResolvedValue(source(2));
    const wrapper = mount(NativeWaybillComposition, { props: { orderId: 1, proposalId: 7 } });
    await wrapper.setProps({ orderId: 2, proposalId: 8 });
    await flushPromises();
    finish(source(1)); await flushPromises();
    const sent = wrapper.emitted('change')!.at(-1)![0] as WaybillComposition_Input;
    expect(sent.source_revision).toBe('b'.repeat(64));
    expect(sent.lines).toEqual([{ order_product_line_id:2, components:null }]);
    wrapper.unmount();
  });

  it('requires a comparison before replacing a historical waybill without recorded line IDs', async () => {
    vi.spyOn(ManagerDocumentSystemService, 'getManagerWaybillComposition').mockResolvedValue(source(2));
    const wrapper = mount(NativeWaybillComposition, { props: { orderId: 1, proposalId: 7, replacementId: 52 } });
    await flushPromises();
    expect(wrapper.emitted('change')!.at(-1)![0]).toBeNull();
    expect(wrapper.text()).toContain('Сверьте состав исправленной накладной');
    wrapper.unmount();
  });

  it('asks for review when a replacement no longer matches its original proposal', async () => {
    vi.spyOn(ManagerDocumentSystemService, 'getManagerWaybillComposition').mockResolvedValue(source(2));
    const wrapper = mount(NativeWaybillComposition, { props: { orderId: 1, proposalId: 7,
      prior: { source_revision: 'a'.repeat(64), lines: [{order_product_line_id:1,components:null}] } } });
    await flushPromises();
    expect(wrapper.emitted('change')!.at(-1)![0]).toBeNull();
    await wrapper.findAll('button').find(button => button.text() === 'Состав проверен')!.trigger('click');
    expect(wrapper.emitted('change')!.at(-1)![0]).toMatchObject({source_revision:'b'.repeat(64)});
    wrapper.unmount();
  });

  it('keeps issued component prices when source is unchanged, restoring whole does not rewrite them', async () => {
    vi.spyOn(ManagerDocumentSystemService, 'getManagerWaybillComposition').mockResolvedValue(source(1));
    const prior = { source_revision:'a'.repeat(64), lines:[{order_product_line_id:1,components:[
      {title:'Позиция', country:'Беларусь', unit:'шт.', quantity_per_parent:2, unit_price:'1235.00'},
    ]}] };
    const wrapper = mount(NativeWaybillComposition, { props: {orderId:1,proposalId:7,prior} });
    await flushPromises();
    expect(wrapper.emitted('change')!.at(-1)![0]).toEqual(prior);
    await wrapper.findAll('button').find(button => button.text() === 'Целиком')!.trigger('click');
    expect(wrapper.emitted('change')!.at(-1)![0]).toMatchObject({lines:[{order_product_line_id:1,components:null}]});
    expect(prior.lines[0]!.components[0]!.unit_price).toBe('1235.00');
    wrapper.unmount();
  });
});
