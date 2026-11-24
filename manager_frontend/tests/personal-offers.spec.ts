import { afterEach, expect, it, vi } from 'vitest';
import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils';
import PersonalOffersView from '../src/views/PersonalOffersView.vue';
import CatalogDecisionWorkspaceView from '../src/views/CatalogDecisionWorkspaceView.vue';
import CatalogDecisionTable from '../src/components/catalog-decision/CatalogDecisionTable.vue';
import CatalogDecisionSelectionTray from '../src/components/catalog-decision/CatalogDecisionSelectionTray.vue';
import { catalogDecisionApi } from '../src/services/catalog-decision-api';
import { catalogDecisionSelectionStorageKey, saveCatalogDecisionSelection } from '../src/services/catalog-decision-selection';
import { managerSession } from '../src/services/manager-session';
import { personalOffersApi, type Draft } from '../src/services/personal-offers';
import { ManagerOrdersService } from '../src/client';
import * as feedback from '../src/services/ui-feedback';

const products = [
  { id: 41, title: 'Air 07 Бюджет', retail_price_byn: 1570, main_image: 'https://mvn.by/images/fixture-07.webp' },
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

function button(wrapper: VueWrapper | DOMWrapper<Element>, label: string) {
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

async function openEditor(query: string, catalogHref?: string) {
  history.replaceState(catalogHref ? { managerReturn: { href: catalogHref } } : {}, '', '/manager/personal-offers' + query);
  managerSession.auth.value = managerAuth as never;
  vi.spyOn(catalogDecisionApi, 'list').mockImplementation(async (_page, _limit, filters) => {
    const classes: Record<number, number> = { 41: 7, 42: 7, 43: 12, 44: 9 };
    const items = products.filter(product => (!filters.productIds || filters.productIds.includes(product.id))
      && (!filters.coolingBtuClasses?.length || filters.coolingBtuClasses.includes(classes[product.id])));
    return { items, meta: { ...meta, total: items.length } } as never;
  });
  vi.spyOn(catalogDecisionApi, 'filterOptions').mockResolvedValue({ brands: [], series: [] } as never);
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
  const confirm = vi.spyOn(feedback, 'confirmDialog').mockImplementation(async options => {
    await options.onConfirm?.();
    return true;
  });
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
  expect(model.get('textarea').attributes('rows')).toBe('1');
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

  await button(wrapper, 'Опубликовать и скопировать').trigger('click');
  await flushPromises();
  const link = (view: VueWrapper) => view.get<HTMLInputElement>('input[aria-label="Ссылка на предложение"]');
  expect(link(wrapper).element.value).toBe(shareUrl('1'));
  expect(api.snapshot()!.rooms.map(room => room.title)).toEqual(roomNamesInPreview(wrapper));

  const writeText = vi.fn().mockResolvedValue(undefined).mockRejectedValueOnce(new Error('clipboard denied'));
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
  await button(wrapper, 'Заменить ссылку').trigger('click');
  await flushPromises();
  expect(api.confirm).toHaveBeenCalledTimes(1);
  expect(link(wrapper).element.value).toBe(shareUrl('2'));
  expect(writeText).toHaveBeenLastCalledWith(shareUrl('2'));

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
  const title = wrapper.findAll('label').find(label => label.text() === 'Название в Manager');
  await title!.get('input').setValue('  Кабинет — варианты  ');
  await savePreview(wrapper);
  expect(roomNamesInPreview(wrapper)).toEqual(['Подбор кондиционера']);
  expect(api.create.mock.calls[0][0].order_id).toBeNull();
  expect(api.create.mock.calls[0][0].title).toBe('Кабинет — варианты');

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
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
  const wrapper = await openEditor('?products=41,42');
  await savePreview(wrapper);
  const previewHeading = wrapper.get('#offer-preview-heading').element;
  expect(document.activeElement).not.toBe(document.body);
  expect(document.activeElement?.contains(previewHeading)).toBe(true);

  const publication = wrapper.get('#offer-publication');
  expect(publication.element.contains(button(wrapper, 'Опубликовать и скопировать').element)).toBe(true);
  expect(publication.element.nextElementSibling?.querySelector('h3')).not.toBeNull();
  await button(publication, 'Опубликовать и скопировать').trigger('click');
  await flushPromises();
  expect(document.activeElement).toBe(button(publication, 'Скопировать ссылку').element);
  expect(publication.get('[role="status"]').text()).toBe('Предложение опубликовано. Ссылка скопирована.');
  expect(writeText).toHaveBeenCalledExactlyOnceWith(shareUrl('1'));
  expect(publication.findAll('button').map(element => element.text())).toEqual([
    'Скопировать ссылку', 'Заменить ссылку', 'Отозвать',
  ]);
});

it('keeps a model photo, price and note with the row when ordering the offer', async () => {
  const api = mockOfferApi();
  const wrapper = await openEditor('?products=41,42,43');
  const first = modelInRoom(wrapper, 0, products[0].title);
  expect(first.get('img').attributes('src')).toBe(products[0].main_image);
  await first.get('input').setValue('1530');
  await first.get('textarea').setValue('Для гостиной');

  const last = modelInRoom(wrapper, 0, products[2].title);
  const dataTransfer = { setData: vi.fn(), effectAllowed: '', dropEffect: '' };
  await first.get('[draggable]').trigger('dragstart', { dataTransfer });
  await last.trigger('dragover', { dataTransfer });
  await last.trigger('drop', { dataTransfer });
  expect(roomsInEditor(wrapper)[0].findAll('li').at(-1)?.element).toBe(first.element);

  await first.get('[aria-label="Поднять Air 07 Бюджет"]').trigger('click');
  expect(roomsInEditor(wrapper)[0].findAll('li')[1].element).toBe(first.element);
  expect(first.get('textarea').element.value).toBe('Для гостиной');
  await savePreview(wrapper);
  const previewOptions = wrapper.get('#offer-publication').element.nextElementSibling!.querySelectorAll('li');
  expect(Array.from(previewOptions, row => row.querySelector('p')?.textContent)).toEqual([
    products[1].title, products[0].title, products[2].title,
  ]);
  expect(api.create.mock.calls[0][0].rooms[0].options).toEqual([
    { product_id: 42, price_byn: '1740', note: null },
    { product_id: 41, price_byn: '1530', note: 'Для гостиной' },
    { product_id: 43, price_byn: '1910', note: null },
  ]);
  await button(wrapper, 'Опубликовать и скопировать').trigger('click');
  await flushPromises();
  expect(api.snapshot()!.rooms[0].options.map(option => option.title)).toEqual([
    products[1].title, products[0].title, products[2].title,
  ]);
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
  const writeText = vi.fn().mockRejectedValue(new Error('clipboard denied'));
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
  api.create.mockRejectedValueOnce(new Error('Черновик не сохранён'));
  api.publish.mockRejectedValueOnce(new Error('Ссылка не опубликована'));
  const wrapper = await openEditor('?products=41,42');

  await savePreview(wrapper);
  expect(wrapper.get('form [role="alert"]').text()).toBe('Черновик не сохранён');
  expect(wrapper.find('#offer-preview-heading').exists()).toBe(false);
  await savePreview(wrapper);
  expect(wrapper.find('form [role="alert"]').exists()).toBe(false);

  await button(wrapper, 'Опубликовать и скопировать').trigger('click');
  await flushPromises();
  expect(button(wrapper, 'Опубликовать и скопировать').element.parentElement?.querySelector('[role="alert"]')?.textContent)
    .toBe('Ссылка не опубликована');
  expect(wrapper.find('input[aria-label="Ссылка на предложение"]').exists()).toBe(false);
  expect(writeText).not.toHaveBeenCalled();

  await button(wrapper, 'Опубликовать и скопировать').trigger('click');
  await flushPromises();
  expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  const link = wrapper.get<HTMLInputElement>('input[aria-label="Ссылка на предложение"]').element;
  expect(link.value).toBe(shareUrl('1'));
  expect(document.activeElement).toBe(link);
  expect([link.selectionStart, link.selectionEnd]).toEqual([0, link.value.length]);
  expect(wrapper.text()).toContain('Скопируйте выделенную ссылку вручную.');
});

it('reuses catalog filters by room and adds verified models without changing the draft terms or catalog basket', async () => {
  const api = mockOfferApi();
  const basketKey = catalogDecisionSelectionStorageKey(managerAuth);
  saveCatalogDecisionSelection([{ id: 41, title: products[0].title }], basketKey);
  const basket = localStorage.getItem(basketKey);
  const wrapper = await openEditor('?products=41', '/manager/catalog-decision?coolingBtuClasses=7,9&orderable=1&page=3');
  await button(wrapper, 'Добавить помещение').trigger('click');
  await roomNameInputs(wrapper)[0].setValue('Гостиная');
  await roomNameInputs(wrapper)[1].setValue('Спальня');
  await roomsInEditor(wrapper)[0].get('select').setValue('fixed');
  await roomsInEditor(wrapper)[0].get('input[inputmode=decimal]').setValue('500');
  await modelInRoom(wrapper, 0, products[0].title).get('input').setValue('1520,00');

  async function openRoom(index: number) {
    const trigger = button(roomsInEditor(wrapper)[index], 'Добавить из подбора');
    await trigger.trigger('click');
    await flushPromises();
    return { trigger, catalog: wrapper.getComponent(CatalogDecisionWorkspaceView) };
  }

  const bedroom = await openRoom(1);
  expect(bedroom.catalog.get('h1').text()).toBe('Модели · Спальня');
  expect(catalogDecisionApi.list).toHaveBeenLastCalledWith(1, 40, expect.objectContaining({ coolingBtuClasses: [7, 9] }), 'recommended', 'asc');
  expect(button(bedroom.catalog, '7').attributes('aria-pressed')).toBe('true');
  expect(button(bedroom.catalog, '9').attributes('aria-pressed')).toBe('true');
  expect(bedroom.catalog.getComponent(CatalogDecisionTable).props('items').map(item => item.id)).toEqual([41, 42, 44]);
  bedroom.catalog.getComponent(CatalogDecisionTable).vm.$emit('toggle', products[3]);
  await flushPromises();
  await button(bedroom.catalog, 'Добавить выбранные').trigger('click');
  await flushPromises();
  expect(document.activeElement).toBe(bedroom.trigger.element);
  expect(roomsInEditor(wrapper)[1].text()).toContain('Добавлено моделей: 1');
  expect(modelInRoom(wrapper, 1, products[3].title).exists()).toBe(true);

  const living = await openRoom(0);
  expect(living.catalog.getComponent(CatalogDecisionTable).props('existingIds')).toEqual([41]);
  await button(living.catalog, '7').trigger('click');
  await button(living.catalog, '9').trigger('click');
  await button(living.catalog, '12').trigger('click');
  await flushPromises();
  expect(living.catalog.getComponent(CatalogDecisionTable).props('items').map(item => item.id)).toEqual([43]);
  living.catalog.getComponent(CatalogDecisionTable).vm.$emit('toggle', products[2]);
  await flushPromises();
  await button(living.catalog, 'Добавить выбранные').trigger('click');
  await flushPromises();

  const reopened = await openRoom(1);
  expect(button(reopened.catalog, '12').attributes('aria-pressed')).toBe('false');
  expect(button(reopened.catalog, '9').attributes('aria-pressed')).toBe('true');
  await button(reopened.catalog, 'К предложению').trigger('click');
  await flushPromises();
  expect(location.search).toBe('?products=41');
  expect(localStorage.getItem(basketKey)).toBe(basket);
  await savePreview(wrapper);
  const [hall, sleep] = api.create.mock.calls[0][0].rooms;
  expect(hall.installation.price_byn).toBe('500');
  expect(hall.options.map(item => [item.product_id, item.price_byn])).toEqual([[41, '1520.00'], [43, '1910']]);
  expect(sleep.options.map(item => item.product_id)).toEqual([44]);
});

it('opens a room-first draft without models selected in the general catalog', async () => {
  const wrapper = await openEditor('?new=1');
  expect(roomsInEditor(wrapper)).toHaveLength(1);
  expect(roomsInEditor(wrapper)[0].findAll('li')).toHaveLength(0);
  await button(roomsInEditor(wrapper)[0], 'Добавить из подбора').trigger('click');
  await flushPromises();
  expect(wrapper.getComponent(CatalogDecisionWorkspaceView).get('h1').text()).toBe('Модели · Подбор кондиционера');
});
