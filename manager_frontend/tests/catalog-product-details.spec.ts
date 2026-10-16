import { DOMWrapper, flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import CatalogDecisionProductDetailsDialog from '../src/components/catalog-decision/CatalogDecisionProductDetailsDialog.vue';
import { productReaderApi, productReaderUrl, type ProductReaderDetail } from '../src/services/product-reader-api';
import { managerSession } from '../src/services/manager-session';
import { managerStorefrontSelection } from '../src/services/manager-storefront-selection';

const selection = { id: 11, title: 'Gree Pular 12', retail_price_byn: 1500, availability: 'in_stock', is_inverter: true, is_published: true, slug: 'gree-pular-12' } as const;
const model = (overrides: Partial<ProductReaderDetail> = {}): ProductReaderDetail => ({
  id: 11, title: 'Gree Pular 12 с длинным названием внутреннего блока', slug: 'gree-pular-12',
  brand_title: 'Gree', series_title: 'Pular', main_image: 'https://images.example.test/main.jpg',
  description: 'Тихая работа.\n<img src=x onerror=alert(1)>',
  images: [{ url: 'https://images.example.test/side.jpg', alt: 'Вид сбоку' }],
  specification_groups: [
    { key: 'power', label: 'Производительность', items: [{ key: 'cooling', label: 'Мощность охлаждения', value: '3,5', unit: 'кВт' }] },
    { key: 'dimensions', label: 'Размеры и вес', items: [{ key: 'weight', label: 'Вес блока', value: '8', unit: 'кг' }] },
  ],
  summary_fields: [{ key: 'cooling', label: 'Мощность охлаждения', value: '3,5', unit: 'кВт' }],
  manuals: [{ title: 'Инструкция по монтажу', url: 'https://files.example.test/manual.pdf' }],
  effective_price: 1500, allowed: true, selection_item: selection, ...overrides,
});
const auth = (capabilities = ['crm.manage']) => ({ username: 'reader-test', staff_user_id: 7, tenant_id: 1, capabilities }) as any;
const mounts: ReturnType<typeof mount>[] = [];
const start = () => {
  const wrapper = mount(CatalogDecisionProductDetailsDialog, { props: { open: true, item: { id: 11, title: 'Loading title' } }, attachTo: document.body });
  mounts.push(wrapper); return wrapper;
};
const dialog = () => new DOMWrapper(document.body.querySelector<HTMLElement>('[role="dialog"]')!);
const button = (text: string) => dialog().findAll('button').find(node => node.text() === text)!;
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(res => { resolve = res; });
  return { promise, resolve };
};
beforeEach(() => {
  managerSession.auth.value = auth();
  vi.spyOn(productReaderApi, 'detail').mockResolvedValue(model());
});
afterEach(() => {
  mounts.splice(0).forEach(wrapper => wrapper.unmount()); vi.restoreAllMocks();
  managerSession.auth.value = null; managerStorefrontSelection.selectedSlug.value = null;
  document.body.style.removeProperty('overflow');
});

describe('catalog product reader', () => {
  it('renders grouped details, gallery enlargement, safe description and manuals', async () => {
    const wrapper = start(); await flushPromises();
    expect(dialog().get('h2').text()).toBe(model().title);
    expect(dialog().text()).toContain('3,5 кВт');
    expect(dialog().text()).toContain('<img src=x onerror=alert(1)>');
    expect(dialog().find('img[src="x"]').exists()).toBe(false);
    await dialog().get('button[aria-label="Фото 2"]').trigger('click');
    expect(dialog().get('button[aria-label^="Увеличить"] img').attributes('src')).toContain('side.jpg');
    await dialog().get('button[aria-label^="Увеличить"]').trigger('click');
    expect(dialog().get('img[alt="Вид сбоку"]').attributes('src')).toContain('side.jpg');
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); await flushPromises();
    expect(dialog().find('button[aria-label="Закрыть увеличенное фото"]').exists()).toBe(false);
    expect(wrapper.emitted('close')).toBeUndefined();
    await button('Все характеристики').trigger('click');
    expect(dialog().text()).toContain('Производительность'); expect(dialog().text()).toContain('Размеры и вес');
    expect(dialog().text()).toContain('8 кг');
    await button('Фото и документы').trigger('click');
    expect(dialog().get('a[href="https://files.example.test/manual.pdf"]').text()).toBe('Инструкция по монтажу');
    expect(dialog().get('a').attributes('rel')).toBe('noopener noreferrer');
  });
  it('emits selection using fresh details, keeps open, and disables items already in the proposal', async () => {
    const wrapper = start(); await flushPromises();
    await button('Добавить в подбор').trigger('click');
    expect(wrapper.emitted('toggle')).toEqual([[selection]]); expect(wrapper.emitted('close')).toBeUndefined();
    await wrapper.setProps({ selected: true }); await button('Убрать из подбора').trigger('click');
    expect(wrapper.emitted('toggle')).toHaveLength(2);
    await wrapper.setProps({ inProposal: true });
    expect(button('В предложении').attributes('disabled')).toBeDefined();
    await button('В предложении').trigger('click'); expect(wrapper.emitted('toggle')).toHaveLength(2);
  });
  it.each([{ allowed: false }, { effective_price: null }, { effective_price: 0 }])('disables ineligible products: %j', async overrides => {
    vi.mocked(productReaderApi.detail).mockResolvedValue(model(overrides));
    const wrapper = start(); await flushPromises();
    expect(button('Добавить в подбор').attributes('disabled')).toBeDefined();
    await button('Добавить в подбор').trigger('click'); expect(wrapper.emitted('toggle')).toBeUndefined();
    if (overrides.effective_price === null) {
      expect(dialog().text()).toContain('Цена пока не указана'); expect(dialog().text()).not.toContain('0 BYN');
    }
  });
  it('requires explicit catalog edit permission and CRM permission for selection', async () => {
    managerSession.auth.value = auth(['catalog.master.read']); start(); await flushPromises();
    expect(dialog().text()).not.toContain('Добавить в подбор'); expect(dialog().text()).not.toContain('Редактировать');
    managerSession.auth.value = auth(['catalog.master.edit']); await flushPromises();
    expect(dialog().get('a[href="/manager/products/11"]').text()).toBe('Редактировать');
    expect(dialog().text()).not.toContain('Добавить в подбор');
  });
  it('leaves products without a selection contract read only', async () => {
    vi.mocked(productReaderApi.detail).mockResolvedValue(model({ selection_item: null })); start(); await flushPromises();
    expect(dialog().text()).not.toContain('Добавить в подбор'); expect(button('Закрыть').exists()).toBe(true);
  });
  it('ignores older responses when the selected product changes', async () => {
    const old = deferred<ProductReaderDetail>(); const recent = deferred<ProductReaderDetail>();
    vi.mocked(productReaderApi.detail).mockReturnValueOnce(old.promise).mockReturnValueOnce(recent.promise);
    const wrapper = start(); await wrapper.setProps({ item: { id: 12, title: 'New model' } });
    recent.resolve(model({ id: 12, title: 'Новая модель' })); await flushPromises();
    old.resolve(model({ title: 'Устаревшая модель' })); await flushPromises();
    expect(dialog().text()).toContain('Новая модель'); expect(dialog().text()).not.toContain('Устаревшая модель');
  });
  it('clears old content when loading fails and supports retry', async () => {
    const wrapper = start(); await flushPromises();
    vi.mocked(productReaderApi.detail).mockRejectedValueOnce(new Error('network'));
    await wrapper.setProps({ item: { id: 12, title: 'Другой товар' } }); await flushPromises();
    expect(dialog().get('[role="alert"]').text()).toContain('Не удалось загрузить');
    expect(dialog().text()).not.toContain('3,5 кВт'); expect(dialog().text()).not.toContain('Добавить в подбор');
    await button('Повторить загрузку').trigger('click'); await flushPromises();
    expect(productReaderApi.detail).toHaveBeenLastCalledWith(12); expect(dialog().text()).toContain('3,5 кВт');
  });
  it('invalidates pending responses after closing, storefront switch and logout', async () => {
    const old = deferred<ProductReaderDetail>(); vi.mocked(productReaderApi.detail).mockReturnValueOnce(old.promise);
    const wrapper = start(); await wrapper.setProps({ open: false });
    old.resolve(model({ title: 'Старая витрина' })); await flushPromises();
    expect(document.body.querySelector('[role="dialog"]')).toBeNull();
    await wrapper.setProps({ open: true }); await flushPromises();
    const pending = deferred<ProductReaderDetail>(); vi.mocked(productReaderApi.detail).mockReturnValueOnce(pending.promise);
    managerStorefrontSelection.selectedSlug.value = 'other'; await flushPromises();
    expect(dialog().text()).not.toContain('3,5 кВт');
    managerSession.auth.value = null; pending.resolve(model({ title: 'Чужая витрина' })); await flushPromises();
    expect(dialog().text()).not.toContain('Чужая витрина'); expect(dialog().text()).not.toContain('Добавить в подбор');
    expect(dialog().text()).not.toContain('3,5 кВт');
  });
  it('preserves existing page scroll styling and restores focus on close', async () => {
    document.body.style.setProperty('overflow', 'auto', 'important');
    const trigger = document.createElement('button'); document.body.append(trigger); trigger.focus();
    const wrapper = start(); await flushPromises(); expect(document.body.style.overflow).toBe('hidden');
    await wrapper.setProps({ open: false }); expect(document.body.style.overflow).toBe('auto');
    expect(document.body.style.getPropertyPriority('overflow')).toBe('important');
    expect(document.activeElement).toBe(trigger); trigger.remove();
  });
  it('filters executable media and document URLs', async () => {
    expect(productReaderUrl('javascript:alert(1)')).toBeNull(); expect(productReaderUrl('data:text/html,<h1>test</h1>')).toBeNull();
    vi.mocked(productReaderApi.detail).mockResolvedValue(model({ main_image: 'javascript:alert(1)', images: [], manuals: [{ title: 'Unsafe', url: 'javascript:alert(1)' }] }));
    start(); await flushPromises(); expect(dialog().text()).toContain('Фотографии пока не добавлены');
    await button('Фото и документы').trigger('click'); expect(dialog().text()).toContain('Документы пока не добавлены');
    expect(dialog().find('a[href^="javascript:"]').exists()).toBe(false);
  });
});
