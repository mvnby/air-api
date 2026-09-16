import { afterEach, describe, expect, it, vi } from 'vitest';
import { DOMWrapper, flushPromises, mount } from '@vue/test-utils';

import { ManagerCatalogDecisionService, ManagerOrdersService } from '../src/client';
import CatalogDecisionOrderDialog from '../src/components/catalog-decision/CatalogDecisionOrderDialog.vue';
import CatalogDecisionCollectionDialog from '../src/components/catalog-decision/CatalogDecisionCollectionDialog.vue';
import CatalogDecisionQuickOrderDialog from '../src/components/catalog-decision/CatalogDecisionQuickOrderDialog.vue';
import CatalogDecisionSelectionTray from '../src/components/catalog-decision/CatalogDecisionSelectionTray.vue';
import { defaultCatalogDecisionAttachMode, hasActiveOrderProducts } from '../src/services/catalog-decision-order';

const selection = [
  { id: 11, title: 'Gree 12' },
  { id: 22, title: 'MDV 18' },
];

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = '';
});

describe('catalog decision basket actions', () => {
  it('offers collection and order actions from the fixed basket', async () => {
    const wrapper = mount(CatalogDecisionSelectionTray, { props: { items: selection } });
    const buttons = wrapper.findAll('button');

    await buttons.find(button => button.text() === 'Создать подборку')!.trigger('click');
    await buttons.find(button => button.text() === 'В существующий заказ')!.trigger('click');
    await buttons.find(button => button.text() === 'Новый заказ')!.trigger('click');

    expect(wrapper.emitted('createCollection')).toHaveLength(1);
    expect(wrapper.emitted('attachOrder')).toHaveLength(1);
    expect(wrapper.emitted('createOrder')).toHaveLength(1);
  });

  it('creates a negotiation order with separate alternatives by default', async () => {
    const create = vi.spyOn(ManagerCatalogDecisionService, 'createManagerCatalogDecisionOrder')
      .mockResolvedValue({ id: 88 } as never);
    const wrapper = mount(CatalogDecisionQuickOrderDialog, {
      props: { open: true, items: selection },
      attachTo: document.body,
      global: { stubs: { teleport: true } },
    });
    const body = new DOMWrapper(document.body);
    await body.findAll('button').find(button => button.text() === 'Юрлицу')!.trigger('click');
    await body.findAll('button').find(button => button.text() === 'Создать заказ')!.trigger('click');
    await flushPromises();

    expect(create).toHaveBeenCalledTimes(1);
    expect(create.mock.calls[0][0]).toMatchObject({
      product_ids: [11, 22],
      prospect_type: 'company',
      proposal_mode: 'alternatives',
    });
    expect(create.mock.calls[0][0].idempotency_key.length).toBeGreaterThanOrEqual(8);
    expect(wrapper.emitted('created')).toEqual([[88]]);
  });

  it('allows an explicit bundle and does not close a saving dialog with Escape', async () => {
    let finish!: (value: any) => void;
    const create = vi.spyOn(ManagerCatalogDecisionService, 'createManagerCatalogDecisionOrder')
      .mockImplementation(() => new Promise(resolve => { finish = resolve; }) as any);
    const wrapper = mount(CatalogDecisionQuickOrderDialog, { props: { open: true, items: selection }, global: { stubs: { teleport: true } } });
    await wrapper.findAll('button').find(button => button.text() === 'Один комплект')!.trigger('click');
    await wrapper.findAll('button').find(button => button.text() === 'Создать заказ')!.trigger('click');
    expect(create.mock.calls[0][0].proposal_mode).toBe('bundle');
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(wrapper.emitted('close')).toBeUndefined();
    finish({ id: 88 });
    await flushPromises();
    wrapper.unmount();
  });

  it('enables comparison only for two to four selections', async () => {
    const wrapper = mount(CatalogDecisionSelectionTray, { props: { items: selection } });
    const compare = () => wrapper.findAll('button').find(button => button.text().startsWith('Сравнить'))!;
    await compare().trigger('click');
    expect(wrapper.emitted('compare')).toHaveLength(1);
    await wrapper.setProps({ items: [selection[0]!] });
    expect(compare().attributes('disabled')).toBeDefined();
    await wrapper.setProps({ items: Array.from({ length: 5 }, (_, id) => ({ id, title: String(id) })) });
    expect(compare().attributes('disabled')).toBeDefined();
    wrapper.unmount();
  });

  it('adds separate alternatives to an existing order without requesting replacement', async () => {
    vi.spyOn(ManagerOrdersService, 'getManagerOrders').mockResolvedValue({ items: [{ id: 88, title: 'Офис' }], meta: {} } as any);
    vi.spyOn(ManagerOrdersService, 'getManagerOrderDetail').mockResolvedValue({ id: 88, status: 'negotiation', proposals: [{ id: 1, is_selected: true, product_lines: [{ product_id: 99 }] }] } as any);
    const attach = vi.spyOn(ManagerCatalogDecisionService, 'attachManagerCatalogDecisionToOrder').mockResolvedValue({ id: 88 } as any);
    const wrapper = mount(CatalogDecisionOrderDialog, { props: { open: true, items: selection }, attachTo: document.body });
    await flushPromises();
    const dialog = new DOMWrapper(document.body.querySelector<HTMLElement>('[role="dialog"]')!);
    expect(dialog.text()).toContain('Офис');
    await dialog.findAll('button').find(button => button.text().includes('Офис'))!.trigger('click');
    await flushPromises();
    await dialog.findAll('button').find(button => button.text() === 'Прикрепить')!.trigger('click');
    await flushPromises();
    expect(attach).toHaveBeenCalledWith(88, { product_ids: [11, 22], mode: 'new_alternative', proposal_mode: 'alternatives' });
    expect(wrapper.emitted('attached')).toEqual([[88]]);
    wrapper.unmount();
  });

  it('creates one draft collection from all selected product ids', async () => {
    const create = vi.spyOn(ManagerCatalogDecisionService, 'createManagerCatalogDecisionCollection')
      .mockResolvedValue({ id: 77 } as never);
    const wrapper = mount(CatalogDecisionCollectionDialog, {
      props: { open: true, items: selection },
      attachTo: document.body,
      global: { stubs: { teleport: true } },
    });
    await flushPromises();
    const body = new DOMWrapper(document.body);
    await body.find('input').setValue('Предложение для офиса');
    await body.find('form').trigger('submit');

    expect(create).toHaveBeenCalledWith({ title: 'Предложение для офиса', product_ids: [11, 22] });
    expect(wrapper.emitted('created')).toEqual([[77]]);
  });

  it('defaults to a safe alternative only when the order already has products', () => {
    const filledOrder = {
      id: 501,
      status: 'negotiation',
      created_at: '2026-08-21',
      total_amount: 2200,
      total_cost: 1000,
      margin: 1200,
      is_paid: false,
      needs_attention: false,
      awaiting_measurement: false,
      client_thinking: false,
      ready_for_execution: false,
      proposals: [{ id: 1, order_id: 501, name: 'Основное', is_selected: true, product_lines: [{ id: 1, order_id: 501, proposal_id: 1, product_id: 9, quantity: 1, price: 2200, cost: 1000 }] }],
    } as never;
    const emptyOrder = { ...filledOrder, proposals: [{ id: 1, order_id: 501, name: 'Основное', is_selected: true, product_lines: [] }] } as never;

    expect(hasActiveOrderProducts(filledOrder)).toBe(true);
    expect(defaultCatalogDecisionAttachMode(filledOrder)).toBe('new_alternative');
    expect(hasActiveOrderProducts(emptyOrder)).toBe(false);
    expect(defaultCatalogDecisionAttachMode(emptyOrder)).toBe('auto');
  });
});
