import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import OrderSitesPanel from '../src/components/orders/OrderSitesPanel.vue';

const api = vi.hoisted(() => ({
  listSites: vi.fn(),
  addSite: vi.fn(),
  updateSite: vi.fn(),
  listSiteEquipment: vi.fn(),
  linkSiteEquipment: vi.fn(),
  listBranches: vi.fn(),
  listEquipment: vi.fn(),
}));
vi.mock('../src/client', () => ({
  ManagerOrderSitesService: {
    managerListOrderSites: api.listSites,
    managerAddOrderSite: api.addSite,
    managerUpdateOrderSite: api.updateSite,
    managerListOrderSiteEquipment: api.listSiteEquipment,
    managerLinkOrderSiteEquipment: api.linkSiteEquipment,
  },
  ManagerService: { getManagerCustomerBranches: api.listBranches },
  ManagerEquipmentService: { listManagerEquipment: api.listEquipment },
}));

const site = (id: number, title: string, branch: number | null, version = 1) => ({
  id, title, order_id: 42, customer_branch_id: branch, address: `Тестовая улица, ${id}`, version,
  manager_url: `/manager/orders/42?section=work&orderSiteId=${id}#order-workspace-sites`,
});
const sitePage = (items: ReturnType<typeof site>[]) => ({
  items, total: items.length, limit: 100, offset: 0,
  legacy_primary: { customer_branch_id: 10, title: 'Основной филиал', address: 'Тестовая улица, 10' },
});
const equipment = (id: number, branch: number | null, name: string, components: Array<{
  id: number; component_type: string; model: string;
}> = []) => ({
  id, display_name: name, customer_branch_id: branch, customer_id: 5, components,
});
const link = (siteId: number, item: ReturnType<typeof equipment>) => ({
  equipment_id: item.id, site_id: siteId, role: 'diagnostic', equipment: item,
});
const list = <T>(items: T[]) => ({ items, total: items.length, limit: 100, offset: 0 });
const button = (wrapper: VueWrapper | DOMWrapper<Element>, title: string) => {
  const match = wrapper.findAll('button').find(node => node.text().trim() === title);
  expect(match, `button «${title}»`).toBeDefined();
  return match!;
};
const panel = (disabled = false) => mount(OrderSitesPanel, {
  props: { orderId: 42, customerId: 5, disabled, beforeAction: vi.fn().mockResolvedValue(true) },
});
const dialog = () => new DOMWrapper(document.body).get('[role="dialog"]');
const expand = async (wrapper: VueWrapper) => {
  await button(wrapper, 'Объекты заказа').trigger('click');
  await flushPromises();
};

beforeEach(() => {
  vi.resetAllMocks();
  api.listSites.mockResolvedValue(sitePage([]));
  api.listSiteEquipment.mockResolvedValue(list([]));
  api.listBranches.mockResolvedValue({
    items: [{ id: 20, name: 'Филиал B', delivery_address: 'Тестовая улица, 20' }],
  });
  api.listEquipment.mockResolvedValue({
    items: [
      equipment(101, 10, 'Только филиал A'),
      equipment(102, 20, 'Реестр филиала B'),
      equipment(103, null, 'Без филиала'),
    ],
  });
});

describe('order sites in Manager', () => {
  it('lazily shows three sites and their distinct 1+2+1 equipment scopes', async () => {
    api.listSites.mockResolvedValue(sitePage([site(1, 'Объект A', 10), site(2, 'Объект B', 20), site(3, 'Объект C', null)]));
    api.listSiteEquipment.mockImplementation(async (_orderId, siteId) => ({
      1: list([link(1, equipment(11, 10, 'Кондиционер A'))]),
      2: list([link(2, equipment(21, 20, 'Кондиционер B1')), link(2, equipment(22, 20, 'Кондиционер B2'))]),
      3: list([link(3, equipment(31, null, 'Кондиционер C', [
        { id: 311, component_type: 'drain_pump', model: 'Тестовый насос' },
      ]))]),
    })[siteId as 1 | 2 | 3]);
    const wrapper = panel();
    try {
      expect(api.listSites).not.toHaveBeenCalled();
      await expand(wrapper);
      expect(api.listSites).toHaveBeenCalledWith(42, 100, 0);
      expect(api.listSiteEquipment).toHaveBeenLastCalledWith(42, 1, 100, 0);
      expect(wrapper.get('[data-testid="order-site-equipment"]').text()).toContain('Кондиционер A');
      expect(wrapper.text()).not.toContain('Основной объект в карточке заказа');

      const picker = wrapper.get('[data-testid="order-site-select"]');
      await picker.setValue('2');
      await flushPromises();
      expect(api.listSiteEquipment).toHaveBeenLastCalledWith(42, 2, 100, 0);
      expect(wrapper.get('[data-testid="order-site-equipment"]').text()).toContain('Кондиционер B1');
      expect(wrapper.get('[data-testid="order-site-equipment"]').text()).toContain('Кондиционер B2');
      expect(wrapper.text()).not.toContain('Кондиционер A');

      await picker.setValue('3');
      await flushPromises();
      expect(wrapper.get('[data-testid="order-site-equipment"]').text()).toContain('Дренажный насос · Тестовый насос');
      expect(wrapper.text()).not.toContain('Кондиционер B1');
    } finally { wrapper.unmount(); }
  });

  it('registers customer branches and retries an identical standalone site command with the same key', async () => {
    api.addSite
      .mockResolvedValueOnce({ result: site(2, 'Филиал B', 20), replayed: false })
      .mockRejectedValueOnce(new Error('Связь прервалась'))
      .mockResolvedValueOnce({ result: site(3, 'Площадка C', null), replayed: true });
    const wrapper = panel();
    try {
      await expand(wrapper);
      expect(wrapper.text()).toContain('Основной филиал');
      await button(wrapper, 'Добавить объект').trigger('click');
      await flushPromises();
      let form = wrapper.get('[data-testid="add-order-site"]');
      await form.get('select').setValue('20');
      await form.trigger('submit');
      await flushPromises();
      expect(api.addSite.mock.calls[0]?.[1]).toMatchObject({ payload: { customer_branch_id: 20 } });
      expect((wrapper.get('[data-testid="order-site-select"]').element as HTMLSelectElement).value).toBe('2');

      await button(wrapper, 'Добавить объект').trigger('click');
      await flushPromises();
      form = wrapper.get('[data-testid="add-order-site"]');
      expect(form.findAll('option')).toHaveLength(1);
      await form.get('input[maxlength="200"]').setValue(' Площадка C ');
      await form.get('input[maxlength="1000"]').setValue(' Тестовая улица, 3 ');
      await form.trigger('submit');
      await flushPromises();
      expect(wrapper.text()).toContain('Связь прервалась');
      await form.trigger('submit');
      await flushPromises();
      expect(api.addSite.mock.calls[1]?.[1]).toMatchObject({ payload: { title: 'Площадка C', address: 'Тестовая улица, 3' } });
      expect(api.addSite.mock.calls[2]?.[1]).toEqual(api.addSite.mock.calls[1]?.[1]);
      expect(wrapper.get('[data-testid="order-site-equipment"]').text()).toContain('Площадка C');
    } finally { wrapper.unmount(); }
  });

  it('corrects the selected site and reuses the request after an interrupted response', async () => {
    api.listSites.mockResolvedValue(sitePage([site(1, 'Объект A', 10), site(2, 'Объект B', 20)]));
    api.updateSite
      .mockRejectedValueOnce(new Error('Связь прервалась'))
      .mockResolvedValueOnce({ result: { ...site(2, 'Новый объект B', 20, 2), address: 'Новый адрес' }, replayed: true });
    const wrapper = panel();
    try {
      await expand(wrapper);
      const picker = wrapper.get('[data-testid="order-site-select"]');
      await picker.setValue('2');
      await button(wrapper, 'Редактировать объект').trigger('click');
      const form = wrapper.get('[data-testid="edit-order-site"]');
      expect((form.get('input[maxlength="200"]').element as HTMLInputElement).value).toBe('Объект B');
      await form.get('input[maxlength="200"]').setValue(' Новый объект B ');
      await form.get('input[maxlength="1000"]').setValue(' Новый адрес ');
      await form.trigger('submit');
      await flushPromises();
      expect(wrapper.text()).toContain('Связь прервалась');
      await form.trigger('submit');
      await flushPromises();
      expect(api.updateSite.mock.calls[0]).toEqual([42, 2, expect.objectContaining({
        payload: { title: 'Новый объект B', address: 'Новый адрес', expected_version: 1 },
      })]);
      expect(api.updateSite.mock.calls[1]).toEqual(api.updateSite.mock.calls[0]);
      expect((picker.element as HTMLSelectElement).value).toBe('2');
      expect(wrapper.get('[data-testid="order-site-equipment"]').text()).toContain('Новый объект B');
      expect(wrapper.find('[data-testid="edit-order-site"]').exists()).toBe(false);
    } finally { wrapper.unmount(); }
  });

  it('refreshes a changed site before resubmitting only the intended correction', async () => {
    api.listSites
      .mockResolvedValueOnce(sitePage([site(2, 'Объект B', 20, 1)]))
      .mockResolvedValueOnce(sitePage([{ ...site(2, 'Объект B', 20, 2), address: 'Адрес коллеги' }]));
    api.updateSite
      .mockRejectedValueOnce({ status: 409, body: { detail: { code: 'version_conflict' } } })
      .mockResolvedValueOnce({ result: { ...site(2, 'Исправленный объект B', 20, 3), address: 'Адрес коллеги' } });
    const wrapper = panel();
    try {
      await expand(wrapper);
      await button(wrapper, 'Редактировать объект').trigger('click');
      const form = wrapper.get('[data-testid="edit-order-site"]');
      await form.get('input[maxlength="200"]').setValue('Исправленный объект B');
      await form.trigger('submit');
      await flushPromises();
      expect(wrapper.get('[role="alert"]').text()).toContain('Объект изменился');
      expect((form.get('input[maxlength="1000"]').element as HTMLInputElement).value).toBe('Адрес коллеги');
      await form.trigger('submit');
      await flushPromises();
      const first = api.updateSite.mock.calls[0]?.[2];
      const second = api.updateSite.mock.calls[1]?.[2];
      expect(second.payload).toEqual({ expected_version: 2, title: 'Исправленный объект B' });
      expect(second.idempotency_key).not.toBe(first.idempotency_key);
    } finally { wrapper.unmount(); }
  });

  it('opens the linked site in a closed order without mutation controls', async () => {
    const oldUrl = window.location.href;
    window.history.replaceState(null, '', '/manager/orders/42?section=work&orderSiteId=2#order-workspace-sites');
    api.listSites.mockResolvedValue(sitePage([site(1, 'Объект A', 10), site(2, 'Объект B', 20)]));
    const wrapper = panel(true);
    try {
      await flushPromises();
      expect(api.listSiteEquipment).toHaveBeenCalledWith(42, 2, 100, 0);
      expect(wrapper.get('[data-testid="order-site-equipment"]').text()).toContain('Объект B');
      expect(wrapper.text()).not.toContain('Добавить объект');
      expect(wrapper.text()).not.toContain('Привязать оборудование');
      expect(wrapper.text()).not.toContain('Редактировать объект');
    } finally {
      wrapper.unmount();
      window.history.replaceState(null, '', oldUrl);
    }
  });

  it('filters candidates by site and refreshes the version after a conflict', async () => {
    api.listSites
      .mockResolvedValueOnce(sitePage([site(2, 'Объект B', 20, 1)]))
      .mockResolvedValueOnce(sitePage([site(2, 'Объект B', 20, 2)]));
    const assigned = link(2, equipment(102, 20, 'Реестр филиала B'));
    api.linkSiteEquipment
      .mockRejectedValueOnce({ status: 409, body: { detail: { code: 'version_conflict' } } })
      .mockResolvedValueOnce({ result: { site: site(2, 'Объект B', 20, 3), equipment: assigned }, replayed: false });
    const wrapper = panel();
    try {
      await expand(wrapper);
      await button(wrapper, 'Привязать оборудование').trigger('click');
      await flushPromises();
      const modal = dialog();
      const select = modal.findAll('select')[0]!;
      expect(select.text()).toContain('Реестр филиала B');
      expect(select.text()).toContain('Без филиала');
      expect(select.text()).not.toContain('Только филиал A');
      await select.setValue('102');
      await modal.get('form').trigger('submit');
      await flushPromises();
      expect(modal.text()).toContain('Объект изменился');
      expect(api.listSites).toHaveBeenCalledTimes(2);
      await modal.get('form').trigger('submit');
      await flushPromises();
      const first = api.linkSiteEquipment.mock.calls[0]?.[2];
      const second = api.linkSiteEquipment.mock.calls[1]?.[2];
      expect(first.payload).toEqual({ equipment_id: 102, role: 'diagnostic', expected_version: 1 });
      expect(second.payload).toEqual({ equipment_id: 102, role: 'diagnostic', expected_version: 2 });
      expect(second.idempotency_key).not.toBe(first.idempotency_key);
      expect(wrapper.emitted('equipment-changed')).toHaveLength(1);
      expect(wrapper.get('[data-testid="order-site-equipment"]').text()).toContain('Реестр филиала B');
    } finally { wrapper.unmount(); }
  });

  it('creates descriptive equipment and components in one site command without inventing serials', async () => {
    api.listSites.mockResolvedValue(sitePage([site(3, 'Объект C', null)]));
    api.linkSiteEquipment.mockResolvedValue({
      result: { site: site(3, 'Объект C', null, 2), equipment: link(3, equipment(31, null, 'Комплект C')) },
      replayed: false,
    });
    const wrapper = panel();
    try {
      await expand(wrapper);
      await button(wrapper, 'Создать оборудование').trigger('click');
      const form = dialog().get('form');
      await form.get('input[placeholder="Кондиционер в серверной"]').setValue('Комплект C');
      await button(form, 'Добавить компонент').trigger('click');
      await button(form, 'Добавить компонент').trigger('click');
      const blocks = form.get('details').findAll('select');
      await blocks[1]!.setValue('outdoor_unit');
      await form.trigger('submit');
      await flushPromises();
      expect(api.linkSiteEquipment).toHaveBeenCalledTimes(1);
      expect(api.linkSiteEquipment.mock.calls[0]).toMatchObject([42, 3, {
        payload: {
          role: 'diagnostic', expected_version: 1,
          equipment: {
            display_name: 'Комплект C', serial: null,
            components: [
              { component_type: 'indoor_unit', serial: null },
              { component_type: 'outdoor_unit', serial: null },
            ],
          },
        },
      }]);
      expect(wrapper.get('[data-testid="order-site-equipment"]').text()).toContain('Комплект C');
    } finally { wrapper.unmount(); }
  });
});
