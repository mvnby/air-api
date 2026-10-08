import { flushPromises, mount } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';
import MoneyAmount from '../src/components/money/MoneyAmount.vue';
import OrderMoney from '../src/components/orders/OrderMoney.vue';
import { formatMoney } from '../src/components/orders/order-utils';
import ProductSuppliersEditor from '../src/components/products/ProductSuppliersEditor.vue';
import ProductMainFields from '../src/components/products/ProductMainFields.vue';
import SupplierMappingView from '../src/views/SupplierMappingView.vue';
import { supplierMappingApi, productSupplierOffersApi } from '../src/services/product-supplier-offers-api';
import { api } from '../src/api';

describe('Manager money display', () => {
  it.each([
    [0, '0 BYN'], [-12.34, '-12,34 BYN'], [0.01, '0,01 BYN'],
    [123456789.12, '123 456 789,12 BYN'],
  ])('renders finite BYN amount %s with selectable currency text', (value, text) => {
    const wrapper = mount(MoneyAmount, { props: { value } });
    expect(wrapper.text()).toBe(text);
    expect(wrapper.classes()).toContain('whitespace-nowrap');
    expect(wrapper.get('.sr-only').text()).toBe('BYN');
    const svg = wrapper.get('svg');
    expect(svg.attributes('aria-hidden')).toBe('true');
    expect(svg.attributes('viewBox')).toBe('0 0 360.67 446.4');
    expect(svg.get('path').attributes('fill')).toBe('currentColor');
  });

  it.each([undefined, null, NaN, Infinity, -Infinity])('shows missing or nonfinite %s as a dash', value => {
    const wrapper = mount(MoneyAmount, { props: { value, formattedValue: '0.00' } });
    expect(wrapper.text()).toBe('—');
    expect(wrapper.attributes('aria-label')).toBe('Нет данных');
    expect(wrapper.find('svg').exists()).toBe(false);
  });

  it.each(['USD', 'EUR', 'PLN'])('keeps the %s code and field-specific precision', currency => {
    const wrapper = mount(MoneyAmount, { props: { value: 10.2345, formattedValue: '10.2345', currency } });
    expect(wrapper.text()).toBe(`10.2345 ${currency}`);
    expect(wrapper.find('svg').exists()).toBe(false);
  });

  it('preserves a fixed two-decimal formatter without applying another rounding step', () => {
    expect(mount(MoneyAmount, { props: { value: 10, formattedValue: '10.00' } }).text()).toBe('10.00 BYN');
  });

  it.each([0, -10, 0.1, 10.001, 10.239, 123456789.12])('preserves the order formatter for %s', value => {
    expect(mount(OrderMoney, { props: { value } }).text()).toBe(formatMoney(value));
  });
});

vi.mock('../src/api', () => ({ api: {
  listSuppliers: vi.fn().mockResolvedValue({ items: [{ id: 1, name: 'Supplier' }] }),
  listSupplierSources: vi.fn().mockResolvedValue({ items: [] }),
  listSupplierSourceUrlImportCandidates: vi.fn(), suggestSupplierOffers: vi.fn(),
} }));
vi.mock('../src/services/product-supplier-offers-api', () => ({
  supplierMappingApi: { listUnmapped: vi.fn() }, productSupplierOffersApi: { listCandidates: vi.fn() },
}));
const moneyOffers = [
  { wholesale_value: 0, wholesale_currency: 'BYN', rrc_byn: 0 },
  { wholesale_value: -0.01, wholesale_currency: 'USD', rrc_byn: -0.01 },
  { wholesale_value: 10.2345, wholesale_currency: 'EUR', rrc_byn: 10.239 },
  { wholesale_value: 123456789.12, wholesale_currency: null, rrc_byn: null },
  { wholesale_value: null, wholesale_currency: 'BYN', rrc_byn: undefined },
  { wholesale_value: 0, wholesale_currency: '', rrc_byn: 0.01 },
].map((offer, index) => ({ ...offer, supplier_id: 1, external_id: `offer-${index}`, id: index + 1,
  title_raw: `Offer ${index}`, qty: 1, is_active: true, updated_at: '2026-10-08', status: 'free' }));
describe('catalog money callers', () => {
  it('keeps supplier table, mobile cards and candidate precision without inventing currencies', async () => {
    vi.mocked(productSupplierOffersApi.listCandidates).mockResolvedValue({ items: moneyOffers, meta: { total: 6, page: 1, pages: 1, limit: 25 } } as any);
    const wrapper = mount(ProductSuppliersEditor, { props: {
      productId: 1, offers: moneyOffers as any, offersLoading: false, offersError: '',
      vitebskQty: 0, stockSaving: false, unlinkingMappingId: null,
    } });
    await flushPromises();
    const table = wrapper.get('tbody');
    const cells = table.findAll('tr').map(row => row.findAll('td')[3]!);
    expect(cells.map(cell => cell.text())).toEqual(['0 BYN', '-0,01 USD', '10,23 EUR', '123 456 789,12', '—', '0']);
    expect(cells[3]!.find('svg').exists()).toBe(false);
    expect(table.text()).toContain('10,24 BYN');
    expect(wrapper.findAll('article').map(card => card.findAll('dd')[2]!.text())).toEqual(cells.map(cell => cell.text()));
    await wrapper.get('select').setValue('1');
    await wrapper.findAll('button').find(button => button.text().includes('Найти'))!.trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('Закупка: 0 BYN');
    expect(wrapper.text()).toContain('РРЦ: 0 BYN');
    expect(wrapper.text()).toContain('Закупка: 123 456 789,12 · РРЦ: —');
    wrapper.unmount();
  });
  it('preserves raw mapping prices including zero and unspecified currency', async () => {
    vi.mocked(supplierMappingApi.listUnmapped).mockResolvedValue({ items: moneyOffers, meta: { total: 6, page: 1, pages: 1, limit: 25 } } as any);
    const wrapper = mount(SupplierMappingView); await flushPromises();
    const cells = wrapper.findAll('tbody tr').map(row => row.findAll('td')[5]!);
    expect(cells.map(cell => cell.text())).toEqual(['0 BYN', '-0.01 USD', '10.2345 EUR', '123456789.12', '—', '0']);
    expect(cells[3]!.find('svg').exists()).toBe(false);
    vi.mocked(api.listSupplierSourceUrlImportCandidates).mockResolvedValue({ items: [
      { source_url: 'https://example.invalid/zero', title_raw: 'Zero RRC', rrc_byn: 0 },
      { source_url: 'https://example.invalid/missing', title_raw: 'Missing RRC', rrc_byn: null },
    ] } as any);
    await wrapper.findAll('button').find(button => button.text() === 'Показать кандидатов')!.trigger('click');
    await flushPromises();
    const sourceLabels = wrapper.get('section').findAll('label');
    expect(sourceLabels.find(label => label.text().includes('Zero RRC'))!.text()).toContain('0 BYN');
    expect(sourceLabels.find(label => label.text().includes('Missing RRC'))!.text()).not.toContain('BYN');
    vi.mocked(api.suggestSupplierOffers).mockResolvedValue({ items: [{
      supplier_id: 1, external_id: 'offer-0', candidates: [{ product_id: 8, title: 'Model', price: 10.2345 }],
    }] } as any);
    await wrapper.findAll('button').find(button => button.text() === 'Привязать')!.trigger('click');
    await flushPromises();
    expect(wrapper.get('input[type="radio"]').element.parentElement!.textContent).toContain('Model (10.2345 BYN)');
    wrapper.unmount();
  });
  it('associates both price fields with accessible names and currency', () => {
    const wrapper = mount(ProductMainFields, { props: {
      modelValue: { title: '', slug: '', price: 0, old_price: null, is_published: false,
        product_kind: 'unknown', catalog_category_override: null }, errors: {},
    } });
    expect(wrapper.get('label[for="product-price"]').text()).toBe('Цена (BYN)');
    expect(wrapper.get('#product-price').element).toHaveProperty('value', '0');
    expect(wrapper.get('label[for="product-old-price"]').text()).toBe('Старая цена (BYN)');
    expect(wrapper.get('#product-old-price').element).toHaveProperty('value', ''); wrapper.unmount();
  });
});


describe('order header and proposal toolbar money callers', () => {
  it.each([null, undefined, NaN, Infinity, "125", 0, -12.345, 12.345, 123456789.12])('keeps raw unknown and numeric value %s', async (value) => {
    const [{ default: Header }, { default: Toolbar }] = await Promise.all([
      import('../src/components/orders/OrderWorkspaceHeader.vue'), import('../src/components/orders/OrderProposalToolbar.vue'),
    ]);
    const header = mount(Header, { props: { title: 'Заказ', workflow: 'supply', viewModel: { stageLabel: 'Новый', nextAction: { label: 'Продолжить' } } as any, total: value as any, paid: value as any, balance: 12.345 } });
    const proposal = { id: 1, name: 'Вариант', status: 'draft', is_selected: true, total_amount: value, product_lines: [{ id: 1 }], service_lines: [] } as any;
    const toolbar = mount(Toolbar, { props: { proposals: [proposal, { ...proposal, id: 2 }], activeProposalId: 1 } });
    const valid = typeof value === 'number' && Number.isFinite(value);
    const expected = valid ? `${value.toLocaleString('ru-RU', { minimumFractionDigits: Number.isInteger(value) ? 0 : 2, maximumFractionDigits: 2 })} BYN` : '—';
    for (const money of [...header.findAllComponents(MoneyAmount).slice(0, 2), ...toolbar.findAllComponents(MoneyAmount)]) {
      expect(money.text()).toBe(expected); expect(money.find('svg').exists()).toBe(valid);
    }
    expect(header.findAllComponents(MoneyAmount)[2]!.text()).toBe('12,35 BYN');
    await toolbar.findAll('button')[0]!.trigger('click'); expect(toolbar.emitted('open')?.[0]).toEqual([proposal]);
    const primary = toolbar.findAll('button').find((b) => b.text().includes('Заполните') || b.text().includes('Завершить'))!;
    await primary.trigger('click');
    expect(Boolean(toolbar.emitted('change-status'))).toBe(Number(value || 0) > 0);
    await header.findAll('button').find((b) => b.text() === 'Внести оплату')!.trigger('click');
    expect(header.emitted('payments')).toEqual([[]]);
    await header.findAll('button').find((b) => b.text() === 'Продолжить')!.trigger('click');
    expect(header.emitted('next')).toEqual([[]]);
    await header.setProps({ compact: true }); expect(header.findAllComponents(MoneyAmount)).toHaveLength(0);
    await header.setProps({ compact: false, workspace: true }); expect(header.findAllComponents(MoneyAmount)).toHaveLength(0);
    await toolbar.setProps({ compact: true, loading: true }); expect(toolbar.findAllComponents(MoneyAmount)).toHaveLength(2);
    expect(toolbar.findAll('button').every((b) => b.attributes('disabled') !== undefined)).toBe(true);
    header.unmount(); toolbar.unmount();
  });
});
