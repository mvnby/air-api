import { flushPromises, shallowMount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import OrderEquipmentPanel from '../src/components/equipment/OrderEquipmentPanel.vue';
import OrderAttachmentsPanel from '../src/components/service-attachments/OrderAttachmentsPanel.vue';

const equipmentApi = vi.hoisted(() => ({ listLinks: vi.fn() }));
const attachmentsApi = vi.hoisted(() => ({ list: vi.fn(), update: vi.fn(), access: vi.fn() }));

vi.mock('../src/client', () => ({
  ManagerEquipmentLinksService: {
    listManagerOrderEquipmentLinks: equipmentApi.listLinks,
  },
  ManagerEquipmentService: {},
}));
vi.mock('../src/components/service-attachments/api', () => ({
  serviceAttachmentsApi: attachmentsApi,
}));

beforeEach(() => {
  vi.clearAllMocks();
  equipmentApi.listLinks.mockResolvedValue({ items: [] });
  attachmentsApi.list.mockResolvedValue({ items: [], total: 0 });
});

describe('order equipment and attachment lazy loading', () => {
  it('loads equipment links only when the panel is used and caches the result', async () => {
    const wrapper = shallowMount(OrderEquipmentPanel, {
      props: { orderId: 42, initialCount: 3 },
    });
    await flushPromises();
    expect(equipmentApi.listLinks).not.toHaveBeenCalled();

    await wrapper.get('button[data-order-usage="equipment_open"]').trigger('click');
    await flushPromises();
    expect(equipmentApi.listLinks).toHaveBeenCalledTimes(1);
    expect(equipmentApi.listLinks).toHaveBeenCalledWith(42);

    await (wrapper.vm as any).$?.exposed?.ensureLoaded();
    expect(equipmentApi.listLinks).toHaveBeenCalledTimes(1);
  });

  it('requests linked equipment and attachments when attachments are expanded', async () => {
    const wrapper = shallowMount(OrderAttachmentsPanel, {
      props: { orderId: 42, initialCount: 2 },
    });
    await flushPromises();
    expect(attachmentsApi.list).not.toHaveBeenCalled();

    await wrapper.get('button[data-order-usage="attachments_open"]').trigger('click');
    await flushPromises();
    expect(wrapper.emitted('need-equipment-options')).toHaveLength(1);
    expect(attachmentsApi.list).toHaveBeenCalledTimes(1);
    expect(attachmentsApi.list).toHaveBeenCalledWith(42);
  });
});


it.each(['manager_maintenance', 'manager'])('keeps equipment link ownership for %s attachments', async (source) => {
  const item={id:99,filename:'block.png',file_kind:'image',mime_type:'image/png',source,category:'defect',caption:null,created_at:'2026-10-07T11:00:00',processing_status:'ready',preview_available:false};
  attachmentsApi.list.mockResolvedValue({items:[item],total:1});
  attachmentsApi.update.mockResolvedValue({...item,caption:'Updated'});
  const wrapper=shallowMount(OrderAttachmentsPanel,{props:{orderId:42,equipmentOptions:[{id:17,label:'Outside block'}]}});
  await wrapper.get('button[data-order-usage="attachments_open"]').trigger('click'); await flushPromises();
  await wrapper.get('[aria-label="Изменить файл"]').trigger('click'); await flushPromises();
  const form=wrapper.get('form');
  const managed=source==='manager_maintenance';
  expect(form.text().includes('Привязка фото управляется замечанием ТО')).toBe(managed);
  expect(form.findAll('select')).toHaveLength(managed ? 1 : 2);
  if(!managed) await form.findAll('select')[1]!.setValue('17');
  await form.trigger('submit'); await flushPromises();
  const command=attachmentsApi.update.mock.calls[0]![2];
  expect(Object.hasOwn(command,'equipment_id')).toBe(!managed);
  if(!managed) expect(command.equipment_id).toBe(17);
});
