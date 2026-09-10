import { flushPromises, shallowMount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import OrderEquipmentPanel from '../src/components/equipment/OrderEquipmentPanel.vue';
import OrderAttachmentsPanel from '../src/components/service-attachments/OrderAttachmentsPanel.vue';

const equipmentApi = vi.hoisted(() => ({ listLinks: vi.fn() }));
const attachmentsApi = vi.hoisted(() => ({ list: vi.fn() }));

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
