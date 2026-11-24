import { afterEach, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import PersonalOffersView from '../src/views/PersonalOffersView.vue';
import CatalogDecisionWorkspaceView from '../src/views/CatalogDecisionWorkspaceView.vue';
import CatalogDecisionTable from '../src/components/catalog-decision/CatalogDecisionTable.vue';
import CatalogDecisionSelectionTray from '../src/components/catalog-decision/CatalogDecisionSelectionTray.vue';
import { catalogDecisionApi } from '../src/services/catalog-decision-api';
import { managerSession } from '../src/services/manager-session';
import { personalOffersApi, type Draft } from '../src/services/personal-offers';
import { ManagerOrdersService } from '../src/client';
import * as feedback from '../src/services/ui-feedback';

const products = [
  { id: 41, title: 'Air 07 Бюджет', retail_price_byn: 1570 },
  { id: 42, title: 'Air 07 Тихий', retail_price_byn: 1740 },
  { id: 43, title: 'Air 12 Зал', retail_price_byn: 1910 },
  { id: 44, title: 'Air 09 Баня', retail_price_byn: 1600 },
];
const managerAuth = {
  username: 'check-manager',
  tenant_id: 43,
  storefront_id: 4,
  staff_user_id: 14,
  capabilities: ['crm.manage'],
};
const meta = { page: 1, pages: 1, total: products.length, limit: 40 };
const shareUrl = (id: string) => 'https://mvn.by/predlozhenie/' + id.repeat(43) + '/';
let mounted: VueWrapper | undefined;

function button(wrapper: VueWrapper, label: string) {
  const found = wrapper.findAll('button').find(item => item.text().trim() === label);
  expect(found, 'button "' + label + '"').toBeDefined();
  return found!;
}

function roomNameInputs(wrapper: VueWrapper) {
  return wrapper.findAll<HTMLInputElement>('input[placeholder]').filter(input =>
    /^(Помещение|Подбор кондиционера)/.test(input.attributes('placeholder')),
  );
}

const roomNamesInPreview = (wrapper: VueWrapper) => wrapper.findAll('h3').map(heading => heading.text());
const roomsInEditor = (wrapper: VueWrapper) => wrapper.findAll('fieldset > section');

async function savePreview(wrapper: VueWrapper) {
  await wrapper.get('form').trigger('submit');
  await flushPromises();
}

function modelInRoom(wrapper: VueWrapper, index: number, title: string) {
  const row = roomsInEditor(wrapper)[index].findAll('li').find(item => item.text().includes(title));
  expect(row, 'room ' + (index + 1) + ', model "' + title + '"').toBeDefined();
  return row!;
}

async function openEditor(query: string) {
  history.replaceState({}, '', '/manager/personal-offers' + query);
  managerSession.auth.value = managerAuth as never;
  vi.spyOn(catalogDecisionApi, 'list').mockImplementation(async (_page, _limit, filters) => ({
    items: products.filter(product => !filters.productIds || filters.productIds.includes(product.id)),
    meta,
  } as never));
  mounted = mount(PersonalOffersView, { attachTo: document.body });
  await flushPromises();
  return mounted;
}

function mockOfferApi() {
  let draft: Draft;
  let revision = 1;
  let share: { url: string; expires_at: string } | null = null;
  let publishCount = 0;

  const response = () => ({ ...structuredClone(draft), id: 7, version: revision, published: share });
  const projection = () => ({
    expires_at: draft.expires_at,
    rooms: draft.rooms.map((room, index, rooms) => {
      const packageMode = room.selection_mode === 'package';
      const equipmentTotal = room.show_total ? room.options.reduce((sum, item) => sum + Number(item.price_byn), 0) : null;
      return {
        title: room.title || (packageMode ? 'Комплект ' + (index + 1) : rooms.length === 1 ? 'Подбор кондиционера' : 'Помещение ' + (index + 1)),
        selection_mode: room.selection_mode,
        equipment_total_byn: equipmentTotal === null ? null : String(equipmentTotal),
        total_with_installation_byn: equipmentTotal !== null && room.installation.mode === 'fixed'
          ? String(equipmentTotal + Number(room.installation.price_byn)) : null,
        installation: room.installation,
        options: room.options.map(option => {
          const product = products.find(item => item.id === option.product_id)!;
          return {
            title: product.title,
            slug: 'fixture-model',
            main_image: null,
            price_byn: option.price_byn,
            original_price_byn: product.retail_price_byn > Number(option.price_byn) ? String(product.retail_price_byn) : null,
            total_price_byn: !packageMode && room.installation.mode === 'fixed'
              ? String(Number(option.price_byn) + Number(room.installation.price_byn))
              : null,
            note: option.note,
            cooling_power_kw: 2,
            noise_indoor_min_db: 20,
            is_inverter: true,
            wifi: 'builtin' as const,
          };
        }),
      };
    }),
  });
  let publicSnapshot: ReturnType<typeof projection> | undefined;

  const create = vi.spyOn(personalOffersApi, 'create').mockImplementation(async data => {
    draft = structuredClone(data);
    return response();
  });
  const update = vi.spyOn(personalOffersApi, 'update').mockImplementation(async (_id, data, version) => {
    expect(version).toBe(revision);
    draft = structuredClone(data);
    revision += 1;
    return response();
  });
  vi.spyOn(personalOffersApi, 'get').mockImplementation(async id => {
    expect(id).toBe(7);
    return response();
  });
  vi.spyOn(personalOffersApi, 'preview').mockImplementation(async () => projection());
  const publish = vi.spyOn(personalOffersApi, 'publish').mockImplementation(async (_id, version, requestId) => {
    expect(version).toBe(revision);
    expect(requestId).toMatch(/^[0-9a-f-]{36}$/);
    share = { url: shareUrl(String(++publishCount)), expires_at: draft.expires_at };
    publicSnapshot = structuredClone(projection());
    revision += 1;
    return response();
  });
  const revoke = vi.spyOn(personalOffersApi, 'revoke').mockImplementation(async (_id, version) => {
    expect(version).toBe(revision);
    share = null;
    revision += 1;
    return response();
  });
  const confirm = vi.spyOn(feedback, 'confirmDialog').mockResolvedValue(true);
  return { create, update, publish, revoke, confirm, snapshot: () => publicSnapshot };
}

afterEach(() => {
  mounted?.unmount();
  mounted = undefined;
  vi.restoreAllMocks();
  managerSession.auth.value = null;
  localStorage.clear();
  history.replaceState({}, '', '/');
  Reflect.deleteProperty(navigator, 'clipboard');
});

it('groups models, previews editable room names and all installation modes, then publishes and revokes the link', async () => {
  const api = mockOfferApi();
  const wrapper = await openEditor('?products=41,42,43,44&orderId=212');
  expect(wrapper.text()).toContain('Заказ №212');
  expect(roomNameInputs(wrapper).map(input => input.attributes('placeholder'))).toEqual(['Подбор кондиционера']);
  const model = modelInRoom(wrapper, 0, products[0].title);
  const modelPrice = model.get<HTMLInputElement>('input[inputmode=decimal]');
  expect(Number(modelPrice.element.value)).toBe(1570);
  await modelPrice.setValue('1520,00');
  await model.get('textarea').setValue('Короткое пояснение клиенту');

  await button(wrapper, 'Добавить помещение').trigger('click');
  await button(wrapper, 'Добавить помещение').trigger('click');
  expect(roomNameInputs(wrapper).map(input => input.attributes('placeholder'))).toEqual([
    'Помещение 1', 'Помещение 2', 'Помещение 3',
  ]);
  await modelInRoom(wrapper, 0, products[2].title).get('select').setValue('2');
  await modelInRoom(wrapper, 0, products[3].title).get('select').setValue('3');

  const [hall, otherRoom, sauna] = roomsInEditor(wrapper);
  await hall.get('select').setValue('fixed');
  await hall.get('input[inputmode=decimal]').setValue('500');
  await otherRoom.get('select').setValue('unknown');
  expect(sauna.findAll('input[inputmode=decimal]')).toHaveLength(1);

  await savePreview(wrapper);
  expect(roomNamesInPreview(wrapper)).toEqual(['Помещение 1', 'Помещение 2', 'Помещение 3']);
  const created = api.create.mock.calls[0][0];
  expect(created.order_id).toBe(212);
  expect(created.rooms.map(room => room.options.map(option => option.product_id))).toEqual([[41, 42], [43], [44]]);
  expect(created.rooms[0].options[0].price_byn).toBe('1520.00');
  expect(created.rooms.map(room => [room.installation.mode, room.installation.price_byn])).toEqual([
    ['fixed', '500'], ['unknown', null], ['none', null],
  ]);
  expect(wrapper.text().replace(/\s/gu, ' ')).toMatch(/С монтажом: 2 020(?:,00)? (?:BYN|Br)/);
  expect(wrapper.text()).toContain('Монтаж: стоимость уточним');
  expect(wrapper.text()).toContain('Короткое пояснение клиенту');

  await roomNameInputs(wrapper)[0].setValue('  Зал  ');
  await roomNameInputs(wrapper)[2].setValue('Баня');
  expect(roomNamesInPreview(wrapper)).toEqual([]);
  await savePreview(wrapper);
  expect(roomNamesInPreview(wrapper)).toEqual(['Зал', 'Помещение 2', 'Баня']);
  expect(api.update).toHaveBeenCalledTimes(1);

  await button(wrapper, 'Опубликовать').trigger('click');
  await flushPromises();
  const link = (view: VueWrapper) => view.get<HTMLInputElement>('input[aria-label="Ссылка на предложение"]');
  expect(link(wrapper).element.value).toBe(shareUrl('1'));
  expect(api.snapshot()!.rooms.map(room => room.title)).toEqual(roomNamesInPreview(wrapper));

  const writeText = vi.fn().mockRejectedValueOnce(new Error('clipboard denied')).mockResolvedValueOnce(undefined);
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
  await button(wrapper, 'Скопировать ссылку').trigger('click');
  await flushPromises();
  expect(wrapper.text()).toContain('Скопируйте выделенную ссылку вручную.');
  expect(document.activeElement).toBe(link(wrapper).element);
  await button(wrapper, 'Скопировать ссылку').trigger('click');
  await flushPromises();
  expect(writeText).toHaveBeenLastCalledWith(shareUrl('1'));
  expect(wrapper.text()).toContain('Ссылка скопирована.');

  await roomNameInputs(wrapper)[0].setValue('');
  await savePreview(wrapper);
  expect(roomNamesInPreview(wrapper)).toEqual(['Помещение 1', 'Помещение 2', 'Баня']);
  expect(api.snapshot()!.rooms[0].title).toBe('Зал');
  await button(wrapper, 'Опубликовать новую ссылку').trigger('click');
  await flushPromises();
  expect(api.confirm).toHaveBeenCalledTimes(1);
  expect(link(wrapper).element.value).toBe(shareUrl('2'));

  mounted?.unmount();
  const reopened = await openEditor('?orderId=212&offerId=7');
  expect(link(reopened).element.value).toBe(shareUrl('2'));
  await button(reopened, 'Отозвать').trigger('click');
  await flushPromises();
  expect(api.revoke).toHaveBeenCalledTimes(1);
  expect(reopened.find('input[aria-label="Ссылка на предложение"]').exists()).toBe(false);
  expect(reopened.text()).toContain('Ссылка отозвана.');
});

it('creates an offer before an order with a named or unnamed single room', async () => {
  const api = mockOfferApi();
  const wrapper = await openEditor('?products=44');
  await savePreview(wrapper);
  expect(roomNamesInPreview(wrapper)).toEqual(['Подбор кондиционера']);
  expect(api.create.mock.calls[0][0].order_id).toBeNull();

  await roomNameInputs(wrapper)[0].setValue('Магазин и склад');
  await savePreview(wrapper);
  expect(roomNamesInPreview(wrapper)).toEqual(['Магазин и склад']);

  await roomNameInputs(wrapper)[0].setValue('   ');
  await savePreview(wrapper);
  expect(roomNamesInPreview(wrapper)).toEqual(['Подбор кондиционера']);
});

it('starts from the real catalog basket and retains the negotiating order and selection', async () => {
  managerSession.auth.value = managerAuth as never;
  history.replaceState({}, '', '/manager/catalog-decision?orderId=212&proposalId=33&search=Air');
  vi.spyOn(catalogDecisionApi, 'list').mockResolvedValue({ items: products, meta } as never);
  vi.spyOn(catalogDecisionApi, 'filterOptions').mockResolvedValue({ brands: [], series: [] });
  vi.spyOn(ManagerOrdersService, 'getManagerOrderDetail').mockResolvedValue({
    status: 'negotiation',
    id: 212,
    proposals: [{ id: 33, status: 'draft' }],
  } as never);

  mounted = mount(CatalogDecisionWorkspaceView, { global: { stubs: {
    CatalogDecisionFilters: true,
    CatalogDecisionTable: true,
    CatalogDecisionCollectionDialog: true,
    CatalogDecisionOrderDialog: true,
    CatalogDecisionQuickOrderDialog: true,
    CatalogDecisionCompareDialog: true,
    CatalogDecisionProductDetailsDialog: true,
  } } });
  await flushPromises();

  const table = mounted.findComponent(CatalogDecisionTable);
  table.vm.$emit('toggle', products[0]);
  table.vm.$emit('toggle', products[3]);
  await flushPromises();
  const tray = mounted.findComponent(CatalogDecisionSelectionTray);
  expect(tray.props('items')).toHaveLength(2);

  await button(tray, 'Подготовить предложение').trigger('click');
  await flushPromises();
  expect(location.pathname).toBe('/manager/personal-offers');
  const query = new URLSearchParams(location.search);
  expect(query.get('orderId')).toBe('212');
  expect(query.get('products')).toBe('41,44');
  expect(tray.props('items')).toHaveLength(2);
});

it('moves focus from the editor to the preview and then to the published link action', async () => {
  mockOfferApi();
  const wrapper = await openEditor('?products=41,42');
  await savePreview(wrapper);
  const previewHeading = wrapper.get('#offer-preview-heading').element;
  expect(document.activeElement).not.toBe(document.body);
  expect(document.activeElement?.contains(previewHeading)).toBe(true);

  await button(wrapper, 'Опубликовать').trigger('click');
  await flushPromises();
  expect(document.activeElement).toBe(button(wrapper, 'Скопировать ссылку').element);
});

it('uses a single proposal mode and opts into the total separately for each package', async () => {
  const api = mockOfferApi();
  const wrapper = await openEditor('?products=41,42,43,44');
  expect(wrapper.find('form input[type="checkbox"]').exists()).toBe(false);
  const mode = wrapper.get('form select');
  await mode.setValue('package');
  await button(wrapper, 'Добавить комплект').trigger('click');
  await modelInRoom(wrapper, 0, products[2].title).get('select').setValue('2');
  await modelInRoom(wrapper, 0, products[3].title).get('select').setValue('2');
  const [first, second] = roomsInEditor(wrapper);
  await first.get('input[placeholder]').setValue('Обычные');
  await second.get('input[placeholder]').setValue('Инверторные');
  await first.get('select').setValue('fixed');
  await first.get('input[inputmode=decimal]').setValue('500');
  await first.get('input[type="checkbox"]').setValue(true);

  await savePreview(wrapper);
  expect(api.create.mock.calls[0][0].rooms.map(room => [room.selection_mode, room.show_total]))
    .toEqual([['package', true], ['package', false]]);
  expect(roomNamesInPreview(wrapper)).toEqual(['Обычные', 'Инверторные']);
  expect(wrapper.text().replace(/\s/gu, ' ')).toMatch(/Итого с монтажом: 3 810(?:,00)? (?:BYN|Br)/);
  expect(wrapper.text().match(/Итого за оборудование/g)).toHaveLength(1);

  await mode.setValue('choice');
  expect(wrapper.find('form input[type="checkbox"]').exists()).toBe(false);
  await savePreview(wrapper);
  expect(api.update.mock.calls[0][1].rooms.map(room => [room.selection_mode, room.show_total]))
    .toEqual([['choice', false], ['choice', false]]);
  expect(wrapper.text()).not.toContain('Итого');
});

it('shows save and publish failures at their actions and allows retry', async () => {
  const api = mockOfferApi();
  api.create.mockRejectedValueOnce(new Error('Черновик не сохранён'));
  api.publish.mockRejectedValueOnce(new Error('Ссылка не опубликована'));
  const wrapper = await openEditor('?products=41,42');

  await savePreview(wrapper);
  expect(wrapper.get('form [role="alert"]').text()).toBe('Черновик не сохранён');
  expect(wrapper.find('#offer-preview-heading').exists()).toBe(false);
  await savePreview(wrapper);
  expect(wrapper.find('form [role="alert"]').exists()).toBe(false);

  await button(wrapper, 'Опубликовать').trigger('click');
  await flushPromises();
  expect(button(wrapper, 'Опубликовать').element.parentElement?.querySelector('[role="alert"]')?.textContent)
    .toBe('Ссылка не опубликована');
  expect(wrapper.find('input[aria-label="Ссылка на предложение"]').exists()).toBe(false);

  await button(wrapper, 'Опубликовать').trigger('click');
  await flushPromises();
  expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  expect(document.activeElement).toBe(button(wrapper, 'Скопировать ссылку').element);
});
