import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import OrderSiteDiagnosticsPanel from '../src/components/orders/OrderSiteDiagnosticsPanel.vue';
import type { ManagerOrderDetailResponse, OrderInspectionState, OrderSiteEquipmentItem } from '../src/client';

const api = vi.hoisted(() => ({
  get: vi.fn(), save: vi.fn(), prepare: vi.fn(), issuers: vi.fn(),
  native: vi.fn(), legacy: vi.fn(), contracts: vi.fn(),
}));
vi.mock('../src/client', () => ({
  ManagerOrderDiagnosticsService: {
    getManagerOrderInspection: api.get,
    saveManagerOrderInspection: api.save,
    prepareManagerOrderTechnicalAct: api.prepare,
  },
  ManagerDocumentSystemService: {
    listManagerDocumentLegalEntities: api.issuers,
    listManagerManagedOrderDocuments: api.native,
  },
  ManagerDocsService: { getManagerOrderDocuments: api.legacy },
  ManagerContractsService: { getManagerCustomerContracts: api.contracts },
}));
vi.mock('../src/services/manager-session', () => ({ managerSession: { auth: { value: null } } }));
const order = {
  id: 42, customer: { id: 7, type: 'company' }, status: 'execution', workflow_type: 'service_work',
} as ManagerOrderDetailResponse;
const scope = (siteId: number) => ({
  id: siteId, order_id: 42, title: `Объект ${siteId}`, address: `Тестовый адрес, ${siteId}`,
  customer_branch_id: siteId + 100, version: 3, manager_url: '/manager/fixture',
});
const item = (siteId: number, equipmentId: number): OrderSiteEquipmentItem => ({
  equipment_id: equipmentId, site_id: siteId, role: 'diagnostic',
  equipment: { id: equipmentId, customer_id: 7, display_name: `Кондиционер ${equipmentId}`, created_at: '2026-11-01' },
});
const state = (
  site_id: number, equipment_id: number, current_version = 0, status: 'defect_found' | 'no_defect_found' | 'restored' = 'no_defect_found',
  facts = 'Штатная работа при проверке', shown = current_version,
): OrderInspectionState => ({
  site_id, equipment_id, order_id: 42, current_version,
  inspection: shown ? { revision_id: 100 + shown, version: shown, status, facts, recorded_at: '2026-11-20T09:00:00Z', recorded_by: 'Тестовый мастер' } : null,
});
const panel = (siteId: number, equipmentIds: number[], disabled = false) => mount(OrderSiteDiagnosticsPanel, {
  props: { order, site: scope(siteId), equipment: equipmentIds.map(id => item(siteId, id)), disabled, beforeAction: vi.fn().mockResolvedValue(true) },
});
const button = (wrapper: VueWrapper, title: string) => {
  const match = wrapper.findAll('button').find(node => node.text().trim() === title);
  expect(match, `button «${title}»`).toBeDefined();
  return match!;
};
const expand = async (wrapper: VueWrapper) => {
  await button(wrapper, 'Результаты диагностики').trigger('click');
  await flushPromises();
};
const openAct = async (wrapper: VueWrapper) => {
  await button(wrapper, 'Подготовить технический акт').trigger('click');
  await flushPromises();
  return wrapper.get('[data-testid="prepare-site-technical-act"]');
};
const original = (overrides: Record<string, unknown> = {}) => ({
  id: 94, order_id: 42, status: 'issued', doc_type: 'defect_act', scope_site_ids: [1], scope_equipment_ids: [11],
  legal_entity_id: 91, base_document_id: 88, display_number: 'Т-94', date: '2026-11-20', ...overrides,
});

beforeEach(() => {
  vi.resetAllMocks();
  api.get.mockImplementation(async (_orderId, siteId, id) => state(siteId, id));
  api.issuers.mockResolvedValue({ items: [
    { id: 91, status: 'active', display_name: 'Тестовый исполнитель' },
    { id: 92, status: 'disabled', display_name: 'Архивный исполнитель' },
  ] });
  api.native.mockResolvedValue({ items: [] });
  api.legacy.mockResolvedValue({ items: [{ id: 88, doc_type: 'contract', number: 'Т-001', date: '2026-11-18' }] });
  api.contracts.mockResolvedValue({ items: [] });
  api.prepare.mockResolvedValue({
    result: { document_id: 101, manager_url: '/manager/orders/42?section=documents&documentId=101' }, replayed: false,
  });
});

describe('scoped order diagnostics', () => {
  it('records completed maintenance separately from recommendations and checks the resulting revision', async () => {
    api.get.mockResolvedValueOnce(state(3, 31)).mockResolvedValueOnce(state(3, 31, 1, 'restored', 'Насос не отводил воду'));
    api.save.mockResolvedValue({ result: { order_id: 42, site_id: 3, equipment_id: 31, revision_id: 101, version: 1 }, replayed: false });
    const wrapper = panel(3, [31]);
    try {
      expect(api.get).not.toHaveBeenCalled();
      await expand(wrapper);
      const editor = wrapper.get('[data-testid="order-inspection-editor"]');
      await editor.get('select').setValue('restored');
      await editor.get('textarea[name="facts"]').setValue('Насос не отводил воду');
      expect(editor.get('button[type="submit"]').attributes('disabled')).toBeDefined();
      await editor.get('textarea[name="performed_actions"]').setValue('Промыли насос. Водоотвод восстановился.');
      await editor.get('textarea[name="recommendations"]').setValue('Осмотреть при следующем ТО.');
      await editor.trigger('submit');
      await flushPromises();
      expect(api.save).toHaveBeenCalledOnce();
      expect(api.save.mock.calls[0]).toMatchObject([42, 3, 31, {
        expected_version: 0, status: 'restored', facts: 'Насос не отводил воду',
        performed_actions: 'Промыли насос. Водоотвод восстановился.',
        recommendations: 'Осмотреть при следующем ТО.', trial_result: null, event_history: null,
      }]);
      expect(wrapper.text()).toContain('Сохранена версия 1');
      expect(api.get).toHaveBeenCalledTimes(2);
    } finally { wrapper.unmount(); }
  });

  it('keeps the local draft on a version conflict and views older saved versions read-only', async () => {
    api.get.mockResolvedValueOnce(state(1, 11, 2, 'defect_found', 'Текущие факты'))
      .mockResolvedValueOnce(state(1, 11, 3, 'defect_found', 'Данные другого мастера'))
      .mockResolvedValueOnce(state(1, 11, 3, 'no_defect_found', 'Старые факты', 2));
    api.save.mockRejectedValue({ status: 409, body: { detail: 'Осмотр уже изменён' } });
    const wrapper = panel(1, [11]);
    try {
      await expand(wrapper);
      const editor = wrapper.get('[data-testid="order-inspection-editor"]');
      const facts = editor.get<HTMLTextAreaElement>('textarea[name="facts"]');
      await facts.setValue('Мои проверенные факты');
      await editor.trigger('submit');
      await flushPromises();
      expect(facts.element.value).toBe('Мои проверенные факты');
      expect(editor.get('button[type="submit"]').attributes('disabled')).toBeDefined();
      await button(wrapper, 'Заменить мой черновик сохранённой версией').trigger('click');
      await flushPromises();
      expect(facts.element.value).toBe('Данные другого мастера');
      await button(wrapper, 'Предыдущая версия').trigger('click');
      await flushPromises();
      expect(api.get).toHaveBeenLastCalledWith(42, 1, 11, 2);
      expect(facts.element.value).toBe('Старые факты');
      expect(editor.get('fieldset').attributes('disabled')).toBeDefined();
      expect(editor.find('button[type="submit"]').exists()).toBe(false);
      await button(wrapper, 'К актуальной версии').trigger('click');
      expect(facts.element.value).toBe('Данные другого мастера');
    } finally { wrapper.unmount(); }
  });

  it('prepares a defect act for the selected current inspection and preserves the retry key', async () => {
    api.get.mockResolvedValue(state(1, 11, 1, 'defect_found', 'Недостаток хладагента'));
    api.prepare.mockRejectedValueOnce(new Error('Связь прервалась'));
    const wrapper = panel(1, [11]);
    try {
      await expand(wrapper);
      const form = await openAct(wrapper);
      await form.get('input[type="checkbox"]').setValue(true);
      await flushPromises();
      const [type, issuer, basis] = form.findAll('select');
      await type!.setValue('defect_act');
      expect(form.get('button[type="submit"]').attributes('disabled')).toBeDefined();
      await issuer!.setValue('91');
      expect(form.get('button[type="submit"]').attributes('disabled')).toBeDefined();
      await basis!.setValue('document:88');
      await form.trigger('submit');
      await flushPromises();
      expect(form.text()).toContain('Связь прервалась');
      await form.trigger('submit');
      await flushPromises();
      expect(api.prepare.mock.calls[0]).toMatchObject([42, 1, {
        document_type: 'defect_act', expected_site_version: 3, inspections: [{ equipment_id: 11, expected_version: 1 }],
        legal_entity_id: 91, base_document_id: 88, base_customer_contract_id: null,
      }]);
      expect(api.prepare.mock.calls[1]).toEqual(api.prepare.mock.calls[0]);
      expect(form.get('a').attributes('href')).toBe('/manager/orders/42?section=documents&documentId=101');
    } finally { wrapper.unmount(); }
  });

  it('prepares a normal inspection act for two units without requiring a defect', async () => {
    api.get.mockImplementation(async (_orderId, siteId, id) => state(siteId, id, id === 21 ? 1 : 2));
    const wrapper = panel(2, [21, 22]);
    try {
      await expand(wrapper);
      const form = await openAct(wrapper);
      const [first, second] = form.findAll('input[type="checkbox"]');
      await first!.setValue(true);
      await second!.setValue(true);
      await flushPromises();
      const [type, issuer, basis] = form.findAll('select');
      await issuer!.setValue('91');
      await basis!.setValue('document:88');
      await type!.setValue('defect_act');
      expect(form.text()).toContain('должен быть зафиксирован дефект');
      expect(form.get('button[type="submit"]').attributes('disabled')).toBeDefined();
      await type!.setValue('technical_inspection_act');
      await form.trigger('submit');
      await flushPromises();
      expect(api.prepare).toHaveBeenCalledOnce();
      expect(api.prepare.mock.calls[0]).toMatchObject([42, 2, {
        document_type: 'technical_inspection_act',
        inspections: [{ equipment_id: 21, expected_version: 1 }, { equipment_id: 22, expected_version: 2 }],
      }]);
    } finally { wrapper.unmount(); }
  });

  it('deep-links to a correction and reuses the issued kind, issuer, basis and equipment with the latest version', async () => {
    const previous = window.location.href;
    window.history.replaceState(null, '', '/manager/orders/42?section=work&orderSiteId=1&replaceTechnicalActId=94');
    api.native.mockResolvedValue({ items: [original()] });
    api.get.mockResolvedValue(state(1, 11, 4, 'defect_found', 'Актуальный вывод'));
    const wrapper = panel(1, [11, 12]);
    try {
      await flushPromises();
      expect(api.native).toHaveBeenCalledWith(42);
      expect(api.get).toHaveBeenCalledWith(42, 1, 11);
      expect(api.get).not.toHaveBeenCalledWith(42, 1, 12);
      const form = wrapper.get('[data-testid="prepare-site-technical-act"]');
      expect(form.text()).toContain('Т-94');
      const controls = form.findAll('select');
      expect(controls.map(control => (control.element as HTMLSelectElement).value)).toEqual(['defect_act', '91', 'document:88']);
      expect(controls.every(control => control.attributes('disabled') !== undefined)).toBe(true);
      expect(form.findAll('input[type="checkbox"]').every(control => control.attributes('disabled') !== undefined)).toBe(true);
      await form.trigger('submit');
      await flushPromises();
      expect(api.prepare.mock.calls[0]).toMatchObject([42, 1, {
        document_type: 'defect_act', replaces_document_id: 94, legal_entity_id: 91,
        base_document_id: 88, inspections: [{ equipment_id: 11, expected_version: 4 }],
      }]);
      expect(form.get('button[type="submit"]').attributes('disabled')).toBeDefined();
      expect(form.get('a').attributes('href')).toContain('documentId=101');
    } finally {
      wrapper.unmount();
      window.history.replaceState(null, '', previous);
    }
  });

  it.each([{ order_id: 43 }, { scope_site_ids: [2] }, { status: 'draft' }])(
    'rejects an ineligible technical revision source %j',
    async overrides => {
      const previous = window.location.href;
      window.history.replaceState(null, '', '/manager/orders/42?section=work&orderSiteId=1&replaceTechnicalActId=94');
      api.native.mockResolvedValue({ items: [original(overrides)] });
      const wrapper = panel(1, [11]);
      try {
        await flushPromises();
        const form = wrapper.get('[data-testid="prepare-site-technical-act"]');
        expect(form.get('[role="alert"]').text()).toContain('Исходный технический акт недоступен');
        await form.trigger('submit');
        expect(api.prepare).not.toHaveBeenCalled();
      } finally {
        wrapper.unmount();
        window.history.replaceState(null, '', previous);
      }
    },
  );

  it('reads inspections for completed orders with the editor and act commands disabled', async () => {
    api.get.mockResolvedValue(state(3, 31, 1, 'restored'));
    const wrapper = panel(3, [31], true);
    try {
      await expand(wrapper);
      expect(api.get).toHaveBeenCalledWith(42, 3, 31);
      expect(wrapper.get('[data-testid="order-inspection-editor"] fieldset').attributes('disabled')).toBeDefined();
      expect(wrapper.text()).not.toContain('Сохранить осмотр');
      expect(wrapper.text()).not.toContain('Подготовить технический акт');
    } finally { wrapper.unmount(); }
  });
});
