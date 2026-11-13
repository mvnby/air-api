import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SupplierMappingView from '../src/views/SupplierMappingView.vue';
import { api } from '../src/api';
import { supplierMappingApi } from '../src/services/product-supplier-offers-api';
import { confirmDialog } from '../src/services/ui-feedback';

vi.mock('../src/services/ui-feedback', () => ({ confirmDialog: vi.fn() }));

const deferred = <T = any,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
};
const listResult = (title: string, total = 1, page = 1) => ({
  items: [{ supplier_id: 1, external_id: title, title_raw: title }],
  meta: { total, page, limit: 25, pages: Math.max(1, Math.ceil(total / 25)) },
});
const urlResult = (title: string) => ({ items: [{ title_raw: title, source_url: `https://example.test/${title}` }] });
const mounts: ReturnType<typeof mount>[] = [];
const start = async () => {
  const wrapper = mount(SupplierMappingView, { global: { stubs: { MoneyAmount: true } } });
  mounts.push(wrapper);
  await flushPromises();
  return wrapper;
};
const button = (wrapper: ReturnType<typeof mount>, text: string) => wrapper.findAll('button').find(node => node.text() === text)!;
const filter = (wrapper: ReturnType<typeof mount>, kind: 'supplier' | 'source') => wrapper.findAll('select')[kind === 'supplier' ? 0 : 1]!;
const changeFilter = async (wrapper: ReturnType<typeof mount>, kind: 'supplier' | 'source', value: 'A' | 'B') => {
  await filter(wrapper, kind).setValue(kind === 'supplier' ? (value === 'A' ? '1' : '2') : (value === 'A' ? '11' : '22'));
};
const dispatchFilter = (wrapper: ReturnType<typeof mount>, value: string) => {
  const select = filter(wrapper, 'supplier').element as HTMLSelectElement;
  select.value = value;
  select.dispatchEvent(new Event('change', { bubbles: true }));
};

beforeEach(() => {
  vi.spyOn(api, 'listSuppliers').mockResolvedValue({ items: [{ id: 1, name: 'Supplier A' }, { id: 2, name: 'Supplier B' }] } as any);
  vi.spyOn(api, 'listSupplierSources').mockResolvedValue({ items: [
    { id: 11, supplier_id: 1, sheet_name: 'Source A' }, { id: 22, supplier_id: 2, sheet_name: 'Source B' },
  ] } as any);
  vi.spyOn(supplierMappingApi, 'listUnmapped').mockResolvedValue(listResult('Initial') as any);
  vi.spyOn(api, 'listSupplierSourceUrlImportCandidates').mockResolvedValue(urlResult('Initial URL') as any);
  vi.spyOn(api, 'startSupplierSourceUrlImport').mockResolvedValue({ job_id: 'test-job' } as any);
  vi.spyOn(api, 'suggestSupplierOffers').mockResolvedValue({ items: [] } as any);
  vi.spyOn(api, 'smartSearchProducts').mockResolvedValue([]);
  vi.mocked(confirmDialog).mockResolvedValue(true);
});
afterEach(() => {
  mounts.splice(0).forEach(wrapper => wrapper.unmount());
  vi.restoreAllMocks();
  vi.mocked(confirmDialog).mockReset();
});

describe('supplier mapping request lifecycle', () => {
  it.each(['supplier', 'source'] as const)('keeps latest %s rows and pagination when B resolves before A', async kind => {
    const wrapper = await start();
    const old = deferred(); const current = deferred();
    vi.mocked(supplierMappingApi.listUnmapped).mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
    await changeFilter(wrapper, kind, 'A');
    await changeFilter(wrapper, kind, 'B');
    current.resolve(listResult('Current B', 76)); await flushPromises();
    old.resolve(listResult('Obsolete A', 2)); await flushPromises();
    expect(wrapper.text()).toContain('Current B');
    expect(wrapper.text()).not.toContain('Obsolete A');
    expect(wrapper.text()).toContain('Показано 1 из 76');
    expect(wrapper.text()).toContain('Страница 1 из 4');
    expect(wrapper.text()).not.toContain('Загрузка...');
  });

  it.each(['supplier', 'source'] as const)('ignores obsolete %s failures after current success', async kind => {
    const wrapper = await start();
    const old = deferred(); const current = deferred();
    vi.mocked(supplierMappingApi.listUnmapped).mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
    await changeFilter(wrapper, kind, 'A'); await changeFilter(wrapper, kind, 'B');
    current.resolve(listResult('Current B')); await flushPromises();
    old.reject(new Error('Obsolete failure')); await flushPromises();
    expect(wrapper.text()).not.toContain('Obsolete failure');
    expect(wrapper.text()).toContain('Current B');
  });

  it.each(['resolve', 'reject'] as const)('retains the current loading state when the older request settles: %s', async settlement => {
    const wrapper = await start();
    const old = deferred(); const current = deferred();
    vi.mocked(supplierMappingApi.listUnmapped).mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
    await changeFilter(wrapper, 'supplier', 'A'); await changeFilter(wrapper, 'supplier', 'B');
    if (settlement === 'resolve') old.resolve(listResult('Obsolete A'));
    else old.reject(new Error('Obsolete failure'));
    await flushPromises();
    expect(wrapper.text()).toContain('Загрузка...');
    expect(wrapper.text()).not.toContain('Obsolete');
    current.reject(new Error('Current failure')); await flushPromises();
    expect(wrapper.text()).toContain('Current failure');
    expect(wrapper.text()).not.toContain('Загрузка...');
  });

  it('invalidates and reloads the list after a same-tick A → B → A filter round trip', async () => {
    const wrapper = await start(); const old = deferred(); const current = deferred();
    vi.mocked(supplierMappingApi.listUnmapped).mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
    await changeFilter(wrapper, 'supplier', 'A');
    // Queue the old settlement before Vue can flush the filter updates.
    old.resolve(listResult('Obsolete A'));
    dispatchFilter(wrapper, '2'); dispatchFilter(wrapper, '1');
    await flushPromises();
    expect(supplierMappingApi.listUnmapped).toHaveBeenCalledTimes(3);
    expect(wrapper.text()).not.toContain('Obsolete A');
    expect(wrapper.text()).toContain('Загрузка...');
    current.resolve(listResult('Fresh A')); await flushPromises();
    expect(wrapper.text()).toContain('Fresh A');
  });

  it('normalizes an incompatible source before making one supplier-filter request', async () => {
    const wrapper = await start();
    await changeFilter(wrapper, 'supplier', 'A');
    await changeFilter(wrapper, 'source', 'A'); await flushPromises();
    vi.mocked(supplierMappingApi.listUnmapped).mockClear();
    await changeFilter(wrapper, 'supplier', 'B'); await flushPromises();
    expect((filter(wrapper, 'source').element as HTMLSelectElement).value).toBe('');
    expect(supplierMappingApi.listUnmapped).toHaveBeenCalledExactlyOnceWith(1, 25, { supplierId: 2, sourceId: undefined, q: '' });
  });

  it('preserves a compatible source while changing the supplier', async () => {
    const wrapper = await start();
    await changeFilter(wrapper, 'source', 'A'); await flushPromises();
    vi.mocked(supplierMappingApi.listUnmapped).mockClear();
    await changeFilter(wrapper, 'supplier', 'A'); await flushPromises();
    expect((filter(wrapper, 'source').element as HTMLSelectElement).value).toBe('11');
    expect(supplierMappingApi.listUnmapped).toHaveBeenCalledExactlyOnceWith(1, 25, { supplierId: 1, sourceId: 11, q: '' });
  });

  it('preserves submitted search and pagination request semantics', async () => {
    const wrapper = await start();
    vi.mocked(supplierMappingApi.listUnmapped).mockResolvedValueOnce(listResult('Search match', 50) as any);
    await wrapper.get('input[type="search"]').setValue('Model');
    await wrapper.get('form').trigger('submit'); await flushPromises();
    expect(supplierMappingApi.listUnmapped).toHaveBeenLastCalledWith(1, 25, { supplierId: undefined, sourceId: undefined, q: 'Model' });
    vi.mocked(supplierMappingApi.listUnmapped).mockResolvedValueOnce(listResult('Second page', 50, 2) as any);
    await button(wrapper, 'Далее').trigger('click'); await flushPromises();
    expect(supplierMappingApi.listUnmapped).toHaveBeenLastCalledWith(2, 25, { supplierId: undefined, sourceId: undefined, q: 'Model' });
    expect(wrapper.text()).toContain('Страница 2 из 2');
  });

  it.each(['supplier', 'source'] as const)('invalidates pending URL candidates when the %s changes', async kind => {
    const wrapper = await start(); const old = deferred();
    vi.mocked(api.listSupplierSourceUrlImportCandidates).mockReturnValueOnce(old.promise);
    await button(wrapper, 'Показать кандидатов').trigger('click');
    await changeFilter(wrapper, kind, 'B');
    old.resolve(urlResult('Obsolete URL')); await flushPromises();
    expect(wrapper.text()).not.toContain('Obsolete URL');
    expect(button(wrapper, 'Импортировать: 0').attributes('disabled')).toBeDefined();
    expect(button(wrapper, 'Показать кандидатов').attributes('disabled')).toBeUndefined();
    expect(api.startSupplierSourceUrlImport).not.toHaveBeenCalled();
  });

  it('clears visible URL candidates and selection on filter changes', async () => {
    const wrapper = await start();
    await button(wrapper, 'Показать кандидатов').trigger('click'); await flushPromises();
    expect(button(wrapper, 'Импортировать: 1').attributes('disabled')).toBeUndefined();
    await changeFilter(wrapper, 'supplier', 'B'); await flushPromises();
    expect(wrapper.text()).not.toContain('Initial URL');
    expect(button(wrapper, 'Импортировать: 0').attributes('disabled')).toBeDefined();
  });

  it('keeps current URL candidates when an older request finishes later', async () => {
    const wrapper = await start(); const old = deferred(); const current = deferred();
    vi.mocked(api.listSupplierSourceUrlImportCandidates).mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
    await button(wrapper, 'Показать кандидатов').trigger('click');
    await changeFilter(wrapper, 'supplier', 'B'); await flushPromises();
    // A changed filter makes its own candidate check available immediately.
    expect(button(wrapper, 'Показать кандидатов')).toBeDefined();
    await button(wrapper, 'Показать кандидатов').trigger('click');
    current.resolve(urlResult('Current URL')); await flushPromises();
    old.resolve(urlResult('Obsolete URL')); await flushPromises();
    expect(wrapper.text()).toContain('Current URL');
    expect(wrapper.text()).not.toContain('Obsolete URL');
    expect(button(wrapper, 'Импортировать: 1').attributes('disabled')).toBeUndefined();
  });

  it('ignores old URL failures while retaining current loading, error and retry behavior', async () => {
    const wrapper = await start(); const old = deferred(); const current = deferred();
    vi.mocked(api.listSupplierSourceUrlImportCandidates).mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
    await button(wrapper, 'Показать кандидатов').trigger('click');
    await changeFilter(wrapper, 'supplier', 'B'); await flushPromises();
    await button(wrapper, 'Показать кандидатов').trigger('click');
    old.reject(new Error('Obsolete URL failure')); await flushPromises();
    expect(wrapper.text()).not.toContain('Obsolete URL failure');
    expect(button(wrapper, 'Проверка...').attributes('disabled')).toBeDefined();
    current.reject(new Error('Current URL failure')); await flushPromises();
    expect(wrapper.text()).toContain('Current URL failure');
    await button(wrapper, 'Показать кандидатов').trigger('click'); await flushPromises();
    expect(wrapper.text()).not.toContain('Current URL failure');
    expect(button(wrapper, 'Импортировать: 1').attributes('disabled')).toBeUndefined();
    expect(api.listSupplierSourceUrlImportCandidates).toHaveBeenLastCalledWith(100, 2, undefined);
  });

  it('imports the selected current URLs with the existing options and refreshes candidates', async () => {
    const wrapper = await start();
    vi.mocked(api.listSupplierSourceUrlImportCandidates).mockResolvedValueOnce({ items: [
      { title_raw: 'Selected', source_url: 'https://example.test/selected' },
      { title_raw: 'Skipped', source_url: 'https://example.test/skipped' },
    ] } as any).mockResolvedValueOnce({ items: [] } as any);
    await button(wrapper, 'Показать кандидатов').trigger('click'); await flushPromises();
    const checkboxes = wrapper.get('section').findAll('input[type="checkbox"]');
    await checkboxes[0]!.setValue(true);
    await checkboxes[2]!.setValue(false);
    await button(wrapper, 'Импортировать: 1').trigger('click'); await flushPromises();
    expect(confirmDialog).toHaveBeenCalledOnce();
    expect(api.startSupplierSourceUrlImport).toHaveBeenCalledExactlyOnceWith({
      urls: ['https://example.test/selected'], with_related: true, update_existing: false,
    });
    expect(api.listSupplierSourceUrlImportCandidates).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain('Импорт запущен: test-job');
    expect(button(wrapper, 'Импортировать: 0').attributes('disabled')).toBeDefined();
  });

  it('does not import captured URLs after the filter changes during confirmation', async () => {
    const wrapper = await start(); const confirmation = deferred<boolean>();
    vi.mocked(confirmDialog).mockReturnValueOnce(confirmation.promise);
    await button(wrapper, 'Показать кандидатов').trigger('click'); await flushPromises();
    await button(wrapper, 'Импортировать: 1').trigger('click');
    await changeFilter(wrapper, 'supplier', 'B');
    confirmation.resolve(true); await flushPromises();
    expect(api.startSupplierSourceUrlImport).not.toHaveBeenCalled();
  });

  it('invalidates URL candidates after a same-tick A → B → A filter round trip', async () => {
    const wrapper = await start(); const pending = deferred();
    await changeFilter(wrapper, 'supplier', 'A'); await flushPromises();
    vi.mocked(api.listSupplierSourceUrlImportCandidates).mockReturnValueOnce(pending.promise);
    await button(wrapper, 'Показать кандидатов').trigger('click');
    pending.resolve(urlResult('Obsolete A URL'));
    dispatchFilter(wrapper, '2'); dispatchFilter(wrapper, '1');
    await flushPromises();
    expect(wrapper.text()).not.toContain('Obsolete A URL');
    expect(button(wrapper, 'Импортировать: 0').attributes('disabled')).toBeDefined();
    expect(button(wrapper, 'Показать кандидатов').attributes('disabled')).toBeUndefined();
  });

  it('invalidates confirmation before a same-tick filter round trip can flush', async () => {
    const wrapper = await start(); const confirmation = deferred<boolean>();
    await changeFilter(wrapper, 'supplier', 'A'); await flushPromises();
    vi.mocked(confirmDialog).mockReturnValueOnce(confirmation.promise);
    await button(wrapper, 'Показать кандидатов').trigger('click'); await flushPromises();
    await button(wrapper, 'Импортировать: 1').trigger('click');
    confirmation.resolve(true);
    dispatchFilter(wrapper, '2'); dispatchFilter(wrapper, '1');
    await flushPromises();
    expect(api.startSupplierSourceUrlImport).not.toHaveBeenCalled();
  });

  it.each(['resolve', 'reject'] as const)('does not update list state after unmount: %s', async settlement => {
    const wrapper = await start(); const pending = deferred();
    vi.mocked(supplierMappingApi.listUnmapped).mockReturnValueOnce(pending.promise);
    await changeFilter(wrapper, 'supplier', 'B');
    const state = wrapper.vm as any;
    const previousRows = state.unmapped; const previousMeta = state.meta;
    wrapper.unmount();
    if (settlement === 'resolve') pending.resolve(listResult('After unmount', 99));
    else pending.reject(new Error('After unmount'));
    await flushPromises();
    expect(state.unmapped).toBe(previousRows);
    expect(state.meta).toBe(previousMeta);
    expect(state.error).toBe('');
    expect(state.loading).toBe(true);
  });

  it('does not continue initial loading after unmount during filter lookup', async () => {
    const pending = deferred(); vi.mocked(api.listSuppliers).mockReturnValueOnce(pending.promise);
    const wrapper = await start(); const state = wrapper.vm as any;
    wrapper.unmount(); pending.resolve({ items: [{ id: 9, name: 'After unmount' }] }); await flushPromises();
    expect(supplierMappingApi.listUnmapped).not.toHaveBeenCalled();
    expect(state.suppliers).toEqual([]);
    expect(state.sources).toEqual([]);
  });

  it('ignores a filter lookup failure after unmount', async () => {
    const pending = deferred(); vi.mocked(api.listSuppliers).mockReturnValueOnce(pending.promise);
    const wrapper = await start(); const state = wrapper.vm as any;
    wrapper.unmount(); pending.reject(new Error('After unmount')); await flushPromises();
    expect(supplierMappingApi.listUnmapped).not.toHaveBeenCalled();
    expect(state.error).toBe('');
  });

  it('does not populate or select URL candidates after unmount', async () => {
    const wrapper = await start(); const pending = deferred();
    vi.mocked(api.listSupplierSourceUrlImportCandidates).mockReturnValueOnce(pending.promise);
    await button(wrapper, 'Показать кандидатов').trigger('click');
    const state = wrapper.vm as any;
    wrapper.unmount(); pending.resolve(urlResult('After unmount')); await flushPromises();
    expect(state.sourceUrlCandidates).toEqual([]);
    expect(state.sourceUrlSelection).toEqual({});
    expect(state.sourceUrlLoading).toBe(true);
  });

  it('does not select suggested mappings after unmount', async () => {
    const wrapper = await start(); const pending = deferred();
    vi.mocked(api.suggestSupplierOffers).mockReturnValueOnce(pending.promise);
    await button(wrapper, 'Подобрать автоматически').trigger('click');
    const state = wrapper.vm as any;
    wrapper.unmount();
    pending.resolve({ items: [{ supplier_id: 1, external_id: 'Initial', auto_eligible: true, candidates: [{ product_id: 9 }] }] });
    await flushPromises();
    expect(state.suggestionMap).toEqual({});
    expect(state.selectedProductMap).toEqual({});
    expect(state.bulkSelection).toEqual({});
    expect(state.suggestionLoading).toBe(true);
  });

  it('does not select inline search results after unmount', async () => {
    const wrapper = await start(); const pending = deferred();
    await button(wrapper, 'Привязать').trigger('click'); await flushPromises();
    vi.mocked(api.smartSearchProducts).mockReturnValueOnce(pending.promise);
    await wrapper.get('input[placeholder="Поиск товара..."]').setValue('Model');
    await wrapper.get('input[placeholder="Поиск товара..."]').trigger('keyup.enter');
    const state = wrapper.vm as any;
    wrapper.unmount(); pending.resolve([{ id: 9, title: 'After unmount' }]); await flushPromises();
    expect(state.inlineCandidates).toEqual({});
    expect(state.selectedProductMap).toEqual({});
    expect(state.suggestionMap).toEqual({});
  });
});
