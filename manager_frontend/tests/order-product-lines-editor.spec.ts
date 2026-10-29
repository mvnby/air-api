import { flushPromises, mount } from '@vue/test-utils';
import { nextTick } from 'vue';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import OrderProductLinesEditor from '../src/components/orders/OrderProductLinesEditor.vue';
import type { ProductLine, ProductOption } from '../src/components/orders/order-editor-types';
import { committedLines } from '../src/components/orders/order-line-drafts';
import { managerSession } from '../src/services/manager-session';

const line = (overrides: Partial<ProductLine> = {}): ProductLine => ({
  link_id: 41,
  product_id: 501,
  product_query: 'Gree Pular',
  client_description: 'Инвертор; площадь: 35 м²',
  quantity: 2,
  price: 1_500,
  cost: 1_000,
  ...overrides,
});

const option: ProductOption = {
  id: 502,
  title: 'Gree Fairy',
  price: 1_700,
  cost: 1_100,
  product_kind: 'conditioner',
  is_inverter: true,
  power_cooling: 2.5,
  availability_status: 'in_stock',
  vitebsk_qty: 2,
  minsk_qty: 1,
};

const props = (lines: ProductLine[], extra: Record<string, unknown> = {}) => ({
  lines,
  searchInStock: false,
  productOptions: [],
  productLookupById: {},
  productLookupLoading: false,
  activeSuggestionIndex: null,
  supplyActionLoadingLineId: null,
  supplyBadgeForLine: () => null,
  compact: true,
  ...extra,
});

beforeEach(() => {
  managerSession.auth.value = { capabilities: ['platform.manage'] } as any;
});

afterEach(() => {
  managerSession.auth.value = null;
});

describe('OrderProductLinesEditor compact mode', () => {
  it('keeps saved rows collapsed with readable details and no inputs', () => {
    const wrapper = mount(OrderProductLinesEditor, { props: props([line(), line({ link_id: 42 })]) });

    expect(wrapper.findAll('[data-testid="product-line-row"]')).toHaveLength(2);
    expect(wrapper.text()).toContain('Gree Pular');
    expect(wrapper.text()).toContain('Инвертор; площадь: 35 м²');
    expect(wrapper.findAll('[data-testid="product-line-row"] input, [data-testid="product-line-row"] textarea')).toHaveLength(0);
    expect(wrapper.findAll('[data-order-usage="order_product_edit"]')).toHaveLength(2);
    expect(wrapper.findAll('[data-order-usage="order_product_remove"]')).toHaveLength(2);
  });

  it('opens only the chosen row, applies v-model edits, and preserves selection events', async () => {
    const first = line({ product_id: 0, product_query: 'Gr' });
    const second = line({ link_id: 42, product_query: 'Midea' });
    const wrapper = mount(OrderProductLinesEditor, {
      props: props([first, second], { productOptions: [option], activeSuggestionIndex: 0 }),
    });

    await wrapper.get('[aria-label="Редактировать товар #1"]').trigger('click');
    expect(wrapper.findAll('textarea')).toHaveLength(2);
    expect(wrapper.get('[data-testid="select-product-502"]').exists()).toBe(true);

    const price = wrapper.find('input[type="number"]');
    await price.setValue('1800');
    expect(first.price).toBe(1800);

    await wrapper.get('[data-testid="select-product-502"]').trigger('click');
    expect(wrapper.emitted('select')).toEqual([[{ index: 0, option }]]);
    await wrapper.get('[aria-label="Применить: товар #1"]').trigger('click');
    expect(wrapper.findAll('textarea')).toHaveLength(0);
  });

  it('marks catalog discounts and markups only on collapsed rows with accessible reference details', async () => {
    const discounted = line({ price: 2_480 });
    const wrapper = mount(OrderProductLinesEditor, {
      props: props([discounted], { productLookupById: { 501: { ...option, id: 501, price: 2_690 } } }),
    });
    const discount = wrapper.get('[data-testid="product-price-adjustment"]');

    expect(discount.text()).toBe('↓ Скидка 7,8%');
    expect(discount.attributes('title')?.replace(/\s/g, '')).toBe(
      'Скидка210BYN(7,8%)относительнокаталожнойцены2690BYN',
    );
    expect(discount.attributes('aria-label')).toBe(discount.attributes('title'));

    await wrapper.get('[aria-label="Редактировать товар #1"]').trigger('click');
    expect(wrapper.find('[data-testid="product-price-adjustment"]').exists()).toBe(false);
    await wrapper.find('input[type="number"]').setValue('2790');
    await wrapper.get('[aria-label="Применить: товар #1"]').trigger('click');
    expect(discounted.price).toBe(2_790);
    expect(wrapper.get('[data-testid="product-price-adjustment"]').text()).toBe('↑ Наценка 3,7%');
    expect(wrapper.get('[data-testid="product-price-adjustment"]').attributes('title')?.replace(/\s/g, ''))
      .toContain('Наценка100BYN(3,7%)относительнокаталожнойцены2690BYN');
  });

  it('omits the price marker for zero prices, matching prices, and missing catalog prices', () => {
    const wrapper = mount(OrderProductLinesEditor, {
      props: props([
        line({ link_id: 1, product_id: 501, price: 0 }),
        line({ link_id: 2, product_id: 501, price: 2_690 }),
        line({ link_id: 3, product_id: 777, price: 2_480 }),
      ], { productLookupById: { 501: { ...option, id: 501, price: 2_690 } } }),
    });

    expect(wrapper.findAll('[data-testid="product-price-adjustment"]')).toHaveLength(0);
  });

  it('does not treat a fallback lookup value as a known catalog price', async () => {
    const unknownCatalogPrice = { ...option, id: 501, price: 2_690, catalog_price_known: false };
    const wrapper = mount(OrderProductLinesEditor, {
      props: props([
        line({ link_id: 1, product_id: 501, price: 2_480 }),
        line({ link_id: 2, product_id: 501, price: 2_690 }),
      ], { productLookupById: { 501: unknownCatalogPrice } }),
    });

    expect(wrapper.findAll('[data-testid="product-price-adjustment"]')).toHaveLength(0);
    await wrapper.setProps({ compact: false });
    expect(wrapper.text()).not.toContain('Цена строки отличается от каталожной');
  });

  it('allocates extra edit rows for long model names and retains the full text', async () => {
    const title = 'MS-12K-ABC Inverter Wi-Fi Climate Control Series Extended Model Name With Optional Enhanced Airflow Settings';
    const wrapper = mount(OrderProductLinesEditor, { props: props([line({ product_query: title })]) });

    await wrapper.get('[aria-label="Редактировать товар #1"]').trigger('click');
    const nameField = wrapper.findAll('textarea')[0];
    expect((nameField.element as HTMLTextAreaElement).rows).toBeGreaterThanOrEqual(3);
    expect((nameField.element as HTMLTextAreaElement).value).toBe(title);
    expect(nameField.classes()).toContain('min-w-0');
    expect(nameField.classes()).toContain('w-full');
    expect(wrapper.findAll('input[type="number"]').every((input) => input.classes().includes('min-w-0'))).toBe(true);
  });

  it('opens a newly appended empty line and closes when the edited line leaves the array', async () => {
    const original = line();
    const wrapper = mount(OrderProductLinesEditor, { props: props([original]) });

    await wrapper.get('[aria-label="Редактировать товар #1"]').trigger('click');
    expect(wrapper.findAll('textarea')).toHaveLength(2);

    const emptyLine = line({ link_id: null, product_id: 0, product_query: '', client_description: null });
    await wrapper.setProps({ lines: [original, emptyLine] });
    expect(wrapper.findAll('textarea')).toHaveLength(4);
    expect(wrapper.get('[aria-label="Добавить товар #2"]').text()).toBe('Добавить товар');

    await wrapper.setProps({ lines: [line({ link_id: 99, product_query: 'Другой товар' })] });
    await nextTick();
    expect(wrapper.findAll('textarea')).toHaveLength(0);
  });

  it('shows cost only when requested and allowed by demo and capability permissions', async () => {
    const wrapper = mount(OrderProductLinesEditor, { props: props([line()], { showCosts: true }) });
    expect(wrapper.text()).toContain('Себест.');
    expect(wrapper.text()).toContain('1 000');

    await wrapper.setProps({ showCosts: false });
    expect(wrapper.text()).not.toContain('Себест.');

    managerSession.auth.value = { demo_read_only: true, capabilities: [] } as any;
    await wrapper.setProps({ showCosts: true });
    expect(wrapper.text()).not.toContain('Себест.');
    await wrapper.get('[aria-label="Редактировать товар #1"]').trigger('click');
    expect(wrapper.findAll('input[type="number"]')).toHaveLength(2);
    expect(wrapper.text()).not.toContain('В поставку');
    expect(wrapper.text()).not.toContain('Забронировать');
  });
});

describe('proposal product draft lifecycle', () => {
  it('focuses the invalid quantity on direct Add without reopening title suggestions', async () => {
    const draft = line({ link_id: null, product_id: 0, product_query: 'Товар с подробным названием '.repeat(8), quantity: 0, editor: { original: null } });
    const wrapper = mount(OrderProductLinesEditor, { attachTo: document.body, props: props([draft]) });
    await wrapper.get('[aria-label="Добавить товар #1"]').trigger('click');
    await flushPromises();
    expect(document.activeElement).toBe(wrapper.get('input[aria-invalid="true"]').element);
    expect(wrapper.get('[role="alert"]').text()).toBe('Целое число больше 0');
    expect(wrapper.emitted('focus')).toBeUndefined();
    expect(committedLines(wrapper.props('lines'))).toHaveLength(0);
    wrapper.unmount();
  });

  it('validates all pending products without publishing any, then applies them together', async () => {
    const saved = line();
    const manual = line({ link_id: null, product_id: 0, product_query: 'Решётка', price: -1, editor: { original: null } });
    const blank = line({ link_id: null, product_id: 0, product_query: '', client_description: '', price: 0, cost: 0, editor: { original: null } });
    const wrapper = mount(OrderProductLinesEditor, { attachTo: document.body, props: props([saved, manual, blank]) });
    await wrapper.get('[aria-label="Редактировать товар #1"]').trigger('click');
    await wrapper.find('input[type="number"]').setValue(1900);

    expect(wrapper.vm.validateDrafts()).toBe(false);
    expect(committedLines(wrapper.props('lines'))).toHaveLength(1);
    expect(committedLines(wrapper.props('lines'))[0]!.price).toBe(1500);
    await nextTick();
    expect(wrapper.text()).toContain('Целое число от 0');
    expect(wrapper.findAll('[data-testid="product-line-row"]')[2]!.text()).not.toContain('Укажите название');
    wrapper.vm.focusDraft();
    await flushPromises();
    expect(document.activeElement).toBe(wrapper.findAll('[data-testid="product-line-row"]')[1]!.get('input[aria-invalid="true"]').element);

    await wrapper.findAll('[data-testid="product-line-row"]')[1]!.find('input[type="number"]').setValue(350);
    expect(wrapper.vm.validateDrafts()).toBe(true);
    wrapper.vm.commitDrafts();
    await nextTick();
    expect(wrapper.props('lines')).toEqual([saved, manual]);
    expect(committedLines(wrapper.props('lines')).map(row => row.price)).toEqual([1900, 350]);
    expect(wrapper.findAll('textarea')).toHaveLength(0);
    wrapper.unmount();
  });

  it('cancels pending products through the workspace API without losing saved neighbours', async () => {
    const saved = line();
    const manual = line({ link_id: null, product_id: 0, product_query: 'Новый экран', editor: { original: null } });
    const neighbour = line({ link_id: 42, product_query: 'Другой товар' });
    const wrapper = mount(OrderProductLinesEditor, { props: props([saved, manual, neighbour]) });
    await wrapper.get('[aria-label="Редактировать товар #1"]').trigger('click');
    await wrapper.find('input[type="number"]').setValue(1900);
    wrapper.vm.cancelDrafts();
    await nextTick();
    expect(wrapper.props('lines')).toEqual([saved, neighbour]);
    expect(saved.price).toBe(1500);
    expect(wrapper.findAll('textarea')).toHaveLength(0);
    expect(wrapper.emitted('remove')).toBeUndefined();
    wrapper.unmount();
  });

  it('focuses an appended blank draft without errors and cancels only that row', async () => {
    const saved = line();
    const wrapper = mount(OrderProductLinesEditor, { attachTo: document.body, props: props([saved]) });
    const blank = line({ link_id: null, product_id: 0, product_query: '', editor: { original: null } });
    await wrapper.setProps({ lines: [saved, blank] });
    await nextTick(); await nextTick();
    const draft = wrapper.findAll('[data-testid="product-line-row"]')[1]!;
    expect(document.activeElement).toBe(draft.find('textarea').element);
    expect(draft.text()).toContain('Отмена');
    expect(draft.find('[role="alert"]').exists()).toBe(false);
    expect(draft.find('[data-order-usage="order_product_remove"]').exists()).toBe(false);
    expect(committedLines(wrapper.props('lines'))).toEqual([saved]);
    await draft.get('[aria-label="Отмена: товар #2"]').trigger('click');
    expect(wrapper.props('lines')).toEqual([saved]);
    expect(wrapper.emitted('remove')).toBeUndefined();
    wrapper.unmount();
  });

  it('commits a manual good with a neutral warning and no catalog operations', async () => {
    const wrapper = mount(OrderProductLinesEditor, { props: props([]) });
    const blank = line({ link_id: null, product_id: 0, product_query: '', editor: { original: null } });
    await wrapper.setProps({ lines: [blank] });
    await wrapper.get('[aria-label="Добавить товар #1"]').trigger('click');
    expect(wrapper.get('[role="alert"]').text()).toBe('Укажите название');
    expect(committedLines(wrapper.props('lines'))).toHaveLength(0);
    await wrapper.find('textarea').setValue('Декоративный экран для кондиционера');
    await wrapper.find('input[type="number"]').setValue(350);
    await wrapper.get('[data-order-usage="order_product_description"]').setValue('Белый, по размеру клиента');
    await wrapper.get('[aria-label="Добавить товар #1"]').trigger('click');
    expect(wrapper.findAll('textarea')).toHaveLength(0);
    expect(committedLines(wrapper.props('lines'))[0]).toMatchObject({ product_id: 0, product_query: 'Декоративный экран для кондиционера', price: 350, client_description: 'Белый, по размеру клиента' });
    expect(wrapper.get('[role="note"]').text()).toBe('Товар не связан с каталогом; наличие и цена не подтверждены');
    expect(wrapper.find('[data-order-usage="order_product_supply"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it('keeps committed values during editing and restores them on cancel', async () => {
    const saved = line();
    const wrapper = mount(OrderProductLinesEditor, { props: props([saved, line({ link_id: 42, product_query: 'Соседний товар' })]) });
    await wrapper.get('[aria-label="Редактировать товар #1"]').trigger('click');
    await wrapper.find('input[type="number"]').setValue(9999);
    expect(committedLines(wrapper.props('lines'))[0]!.price).toBe(1500);
    await wrapper.get('[aria-label="Отмена: товар #1"]').trigger('click');
    expect(saved.price).toBe(1500);
    expect(wrapper.props('lines')[1]!.product_query).toBe('Соседний товар');
    expect(wrapper.findAll('textarea')).toHaveLength(0);
    wrapper.unmount();
  });
});

it.each([
  { kind: 'catalog snapshot', productId: 501, editorFields: 0 },
  { kind: 'manual name', productId: 0, editorFields: 2 },
])('bounds only manual names while preserving a long $kind', async ({ productId, editorFields }) => {
  const saved = line({ product_id: productId, product_query: 'Очень длинное название модели '.repeat(50) });
  const wrapper = mount(OrderProductLinesEditor, { props: props([saved]) });
  await wrapper.get('[aria-label="Редактировать товар #1"]').trigger('click');
  await wrapper.get('input[type="number"]').setValue(1800);
  await wrapper.get('[aria-label="Применить: товар #1"]').trigger('click');
  expect(wrapper.findAll('textarea')).toHaveLength(editorFields);
  expect(wrapper.find('[role="alert"]').exists()).toBe(productId === 0);
  wrapper.unmount();
});
