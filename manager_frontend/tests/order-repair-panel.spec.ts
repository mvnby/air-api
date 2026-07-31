import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ManagerOrderDetailResponse } from '../src/client';
import {
  ManagerEquipmentService,
  ManagerOrdersService,
  ManagerRepairComplaintsService,
} from '../src/client';
import OrderRepairEquipmentPanel from '../src/components/orders/OrderRepairEquipmentPanel.vue';
import OrderRepairPanel from '../src/components/orders/OrderRepairPanel.vue';
import { emptyRepairMeta } from '../src/components/orders/repair-meta';

vi.mock('../src/client', () => ({
  ManagerEquipmentService: {
    listManagerEquipment: vi.fn(),
    getManagerEquipment: vi.fn(),
    createManagerEquipment: vi.fn(),
    createManagerEquipmentHistoryFromRepairOrder: vi.fn(),
  },
  ManagerOrdersService: {
    patchManagerOrder: vi.fn(),
  },
  ManagerRepairComplaintsService: {
    listManagerRepairComplaintPresets: vi.fn(),
    generateManagerRepairActAiDraft: vi.fn(),
  },
}));

const order = {
  id: 42,
  status: 'negotiation',
  title: 'Ремонт кондиционера',
  created_at: '2026-07-31T10:00:00Z',
  total_amount: 0,
  total_cost: 0,
  margin: 0,
  is_paid: false,
  customer: { id: 11, name: 'Анна' },
  needs_attention: false,
  awaiting_measurement: false,
  client_thinking: false,
  ready_for_execution: false,
} as ManagerOrderDetailResponse;

const preset = {
  id: 17,
  complaint_group: 'cooling',
  customer_phrase: 'Не холодит',
  document_wording: 'Оборудование не обеспечивает охлаждение',
  likely_diagnosis: 'Требуется диагностика холодильного контура',
  is_favorite: true,
  created_at: '2026-07-31T10:00:00Z',
};

const equipment = {
  id: 71,
  customer_id: 11,
  customer_branch_id: null,
  display_name: 'Gree Pular',
  brand: 'Gree',
  model: 'Pular',
  serial: 'SN-71',
  created_at: '2026-07-31T10:00:00Z',
};

const mountedWrappers: VueWrapper[] = [];
const listPresetsMock = vi.mocked(
  ManagerRepairComplaintsService.listManagerRepairComplaintPresets,
);
const generateDraftMock = vi.mocked(
  ManagerRepairComplaintsService.generateManagerRepairActAiDraft,
);
const patchOrderMock = vi.mocked(ManagerOrdersService.patchManagerOrder);
const listEquipmentMock = vi.mocked(ManagerEquipmentService.listManagerEquipment);
const getEquipmentMock = vi.mocked(ManagerEquipmentService.getManagerEquipment);
const recordHistoryMock = vi.mocked(
  ManagerEquipmentService.createManagerEquipmentHistoryFromRepairOrder,
);

beforeEach(() => {
  vi.clearAllMocks();
  listPresetsMock.mockResolvedValue({ items: [preset], total: 1 } as any);
  generateDraftMock.mockResolvedValue({
    repair_meta: { diagnostic_result: 'Недостаточное давление хладагента' },
    model: 'test-model',
  });
  patchOrderMock.mockResolvedValue(order);
  listEquipmentMock.mockResolvedValue({ items: [equipment], total: 1 } as any);
  getEquipmentMock.mockResolvedValue({
    ...equipment,
    recent_history: [{
      id: 501,
      equipment_id: equipment.id,
      event_type: 'diagnostic',
      event_date: '2026-07-31T11:00:00Z',
      diagnostic_result: 'Проверено давление',
      created_at: '2026-07-31T11:00:00Z',
    }],
  } as any);
  recordHistoryMock.mockResolvedValue({} as any);
});

afterEach(() => {
  for (const wrapper of mountedWrappers.splice(0)) wrapper.unmount();
  document.body.innerHTML = '';
});

describe('OrderRepairPanel', () => {
  it('loads the complaint library and applies a controlled preset to repair meta', async () => {
    const repairMeta = emptyRepairMeta();
    const wrapper = mount(OrderRepairPanel, {
      props: {
        order,
        orderTitle: order.title || '',
        measurementResult: '',
        customerBranchId: null,
        objectAddress: 'Минск',
        expanded: true,
        repairMeta,
      },
    });
    mountedWrappers.push(wrapper);
    await flushPromises();

    expect(listPresetsMock).toHaveBeenCalledWith('', null, false, false, 100);
    await wrapper.get(`[data-testid="repair-preset-${preset.id}"]`).trigger('click');

    expect(repairMeta.customer_complaint).toBe(preset.customer_phrase);
    expect(repairMeta.complaint_official).toBe(preset.document_wording);
    expect(repairMeta.likely_diagnosis).toBe(preset.likely_diagnosis);
  });

  it('persists an AI draft through the order command and requests a projection reload', async () => {
    const repairMeta = emptyRepairMeta();
    repairMeta.customer_complaint = 'Не холодит';
    const wrapper = mount(OrderRepairPanel, {
      props: {
        order,
        orderTitle: order.title || '',
        measurementResult: 'Выезд выполнен',
        customerBranchId: null,
        objectAddress: 'Минск',
        expanded: true,
        repairMeta,
      },
    });
    mountedWrappers.push(wrapper);
    await flushPromises();

    await wrapper.get('[data-testid="generate-repair-ai"]').trigger('click');
    await flushPromises();

    expect(generateDraftMock).toHaveBeenCalledTimes(1);
    expect(patchOrderMock).toHaveBeenCalledWith(order.id, expect.objectContaining({
      measurement_result: 'Выезд выполнен',
      repair_meta: expect.objectContaining({
        diagnostic_result: 'Недостаточное давление хладагента',
      }),
    }));
    expect(wrapper.emitted('reload')).toEqual([[order.id]]);
    expect(wrapper.emitted('toast')).toContainEqual([{
      message: 'Черновик дефектного акта заполнен и сохранен',
      type: 'success',
    }]);
  });
});

describe('OrderRepairEquipmentPanel', () => {
  it('loads branch equipment and records history without changing the order status', async () => {
    const wrapper = mount(OrderRepairEquipmentPanel, {
      props: {
        orderId: order.id,
        orderTitle: order.title || '',
        customerId: order.customer?.id || null,
        customerBranchId: null,
        objectAddress: 'Минск',
        repairMeta: emptyRepairMeta(),
      },
    });
    mountedWrappers.push(wrapper);
    await flushPromises();

    expect(listEquipmentMock).toHaveBeenCalledWith(11, null, 1, 50, false);
    expect(wrapper.text()).toContain('Gree Pular');
    expect(wrapper.text()).toContain('Проверено давление');

    await wrapper.get('[data-testid="record-repair-history"]').trigger('click');
    await flushPromises();

    expect(recordHistoryMock).toHaveBeenCalledWith(equipment.id, {
      order_id: order.id,
      event_type: null,
      notes: null,
    });
    expect(wrapper.emitted('toast')).toEqual([[{
      message: 'Событие записано в историю оборудования',
      type: 'success',
    }]]);
  });
});
