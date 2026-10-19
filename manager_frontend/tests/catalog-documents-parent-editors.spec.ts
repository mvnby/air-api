import { flushPromises, shallowMount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

const mocks = vi.hoisted(() => ({ get: vi.fn(), replace: vi.fn(), upload: vi.fn(), confirmDialog: vi.fn(), productSave: vi.fn() }));
vi.mock('../src/services/catalog-documents-api', () => ({ catalogDocumentsApi: { get: mocks.get, replace: mocks.replace, upload: mocks.upload } }));
vi.mock('../src/services/ui-feedback', () => ({ confirmDialog: mocks.confirmDialog }));

import BrandEditorModal from '../src/components/brands/BrandEditorModal.vue';
import SeriesEditorModal from '../src/components/brands/SeriesEditorModal.vue';
import CatalogDocumentsPanel from '../src/components/catalog/CatalogDocumentsPanel.vue';
import ProductWorkspaceView from '../src/views/ProductWorkspaceView.vue';
import { managerSession } from '../src/services/manager-session';
import { api } from '../src/api';
import { canNavigateAway } from '../src/services/unsaved-navigation-guard';
import type { BrandForm, SeriesForm } from '../src/components/brands/brand-form-types';

const cancelable = <T,>(promise: Promise<T> | T) => Object.assign(Promise.resolve(promise), { cancel: vi.fn(), isCancelled: false });
const document = { id: 1, title: 'Operation', url: 'https://example.com/manual.pdf', source_url: null, kind: 'operation', language: null, year: null, visibility: 'public', inherit_to_products: true, origin_type: 'series', origin_id: 3, origin_title: 'FG', inherited: false };
const workspace = () => ({ own: [{ ...document }], inherited: [], effective: [{ ...document }] });
const brandForm = (): BrandForm => ({ title: 'Example', slug: 'example', logo_url: '', official_url: '', short_description: '', description: '', sort_order: 0, is_published: true });
const seriesForm = (): SeriesForm => ({ title: 'FG', slug: 'fg', tagline: '', short_description: '', description: '', hero_image: '', galleryImages: [], feature_assignments: [], contentBlocks: [], footnotesText: '', seo_title: '', seo_description: '', source_url: '', sort_order: 0, is_published: true });
const product = { id: 4, title: 'Model', slug: 'model', price: 1000, is_published: true, series_id: 3, gallery_images: [], images: [], tags: [] } as any;
const editorStub = defineComponent({
  name: 'ProductEditModal',
  emits: ['dirty-change'],
  setup(_, { expose }) { expose({ save: mocks.productSave }); return () => h('div', { 'data-test': 'product-editor' }); },
});
let currentWrapper: ReturnType<typeof shallowMount> | null = null;

beforeEach(() => {
  Object.values(mocks).forEach(mock => mock.mockReset());
  managerSession.auth.value = { capabilities: ['catalog.master.edit'] } as any;
  mocks.get.mockImplementation(() => cancelable(workspace()));
  mocks.productSave.mockResolvedValue(true);
  mocks.confirmDialog.mockResolvedValue(false);
  localStorage.clear();
  sessionStorage.clear();
  history.replaceState({}, '', '/');
});
afterEach(() => {
  currentWrapper?.unmount(); currentWrapper = null;
  managerSession.auth.value = null;
  vi.restoreAllMocks();
  history.replaceState({}, '', '/');
});

const startModal = async (kind: 'brand' | 'series') => {
  currentWrapper = kind === 'brand'
    ? shallowMount(BrandEditorModal, { props: { open: true, form: brandForm(), editing: true, brandId: 8, saving: false }, global: { stubs: { CatalogDocumentsPanel: false } } })
    : shallowMount(SeriesEditorModal, { props: { open: true, form: seriesForm(), editing: true, seriesId: 3, features: [], featuresLoading: false, saving: false, galleryApplying: false }, global: { stubs: { CatalogDocumentsPanel: false } } });
  await flushPromises();
  await currentWrapper.getComponent(CatalogDocumentsPanel).get('fieldset input').setValue('Edited operation');
  return currentWrapper;
};

describe.each(['brand', 'series'] as const)('%s document save integration', kind => {
  it('keeps the editor open with the document error when parent Save fails', async () => {
    mocks.replace.mockImplementation(() => cancelable(Promise.reject(new Error('Ошибка сохранения документа'))));
    const wrapper = await startModal(kind);
    await wrapper.findAll('footer button').find(button => button.text() === 'Сохранить')!.trigger('click');
    await flushPromises();
    expect(wrapper.emitted('save')).toBeUndefined();
    expect(wrapper.emitted('close')).toBeUndefined();
    expect(wrapper.text()).toContain('Ошибка сохранения документа');
  });

  it('saves documents before emitting the parent save and does not repeat an unchanged set', async () => {
    mocks.replace.mockImplementation(() => cancelable({ own: [{ ...document, title: 'Edited operation' }], inherited: [], effective: [] }));
    const wrapper = await startModal(kind);
    const save = wrapper.findAll('footer button').find(button => button.text() === 'Сохранить')!;
    await save.trigger('click');
    await flushPromises();
    expect(wrapper.emitted('save')).toHaveLength(1);
    expect(mocks.replace).toHaveBeenCalledOnce();
    await save.trigger('click');
    await flushPromises();
    expect(wrapper.emitted('save')).toHaveLength(2);
    expect(mocks.replace).toHaveBeenCalledOnce();
  });

  it('requires the discard decision before cancelling a dirty document draft', async () => {
    const wrapper = await startModal(kind);
    const cancel = wrapper.findAll('footer button').find(button => button.text() === 'Отмена')!;
    await cancel.trigger('click');
    await flushPromises();
    expect(mocks.confirmDialog).toHaveBeenCalledOnce();
    expect(wrapper.emitted('close')).toBeUndefined();
    mocks.confirmDialog.mockResolvedValue(true);
    await cancel.trigger('click');
    await flushPromises();
    expect(wrapper.emitted('close')).toHaveLength(1);
    expect(mocks.replace).not.toHaveBeenCalled();
  });
});

const startProduct = async () => {
  history.replaceState({}, '', '/manager/products/4/publication');
  vi.spyOn(api, 'getManagerProduct').mockResolvedValue(product);
  currentWrapper = shallowMount(ProductWorkspaceView, { global: { stubs: { CatalogDocumentsPanel: false, ProductEditModal: editorStub } } });
  await flushPromises();
  await currentWrapper.getComponent(CatalogDocumentsPanel).get('fieldset input').setValue('Edited operation');
  return currentWrapper;
};

describe('product document save integration', () => {
  it('blocks the product save when document persistence fails and preserves editor changes', async () => {
    mocks.replace.mockImplementation(() => cancelable(Promise.reject(new Error('Ошибка сохранения документа'))));
    const wrapper = await startProduct();
    wrapper.getComponent(editorStub).vm.$emit('dirty-change', true);
    await wrapper.findAll('nav button').find(button => button.text().includes('Основное'))!.trigger('click');
    await wrapper.findAll('header button').find(button => button.text() === 'Сохранить')!.trigger('click');
    await flushPromises();
    expect(mocks.productSave).not.toHaveBeenCalled();
    expect(api.getManagerProduct).toHaveBeenCalledOnce();
    expect(wrapper.text()).toContain('Ошибка сохранения документа');
    expect(wrapper.text()).toContain('Есть несохранённые изменения');
    expect(wrapper.getComponent(CatalogDocumentsPanel).isVisible()).toBe(true);
  });

  it('retains a document draft across section changes and guards close, sidebar and browser leave', async () => {
    const wrapper = await startProduct();
    const panel = wrapper.getComponent(CatalogDocumentsPanel);
    await wrapper.findAll('nav button').find(button => button.text().includes('Основное'))!.trigger('click');
    expect(wrapper.getComponent(CatalogDocumentsPanel).element).toBe(panel.element);
    expect((wrapper.getComponent(CatalogDocumentsPanel).get('fieldset input').element as HTMLInputElement).value).toBe('Edited operation');
    expect(wrapper.getComponent(CatalogDocumentsPanel).isVisible()).toBe(false);
    expect(wrapper.text()).toContain('Есть несохранённые изменения');
    const unload = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);
    expect(await canNavigateAway()).toBe(false);
    await wrapper.get('button[title="К товарам"]').trigger('click');
    await flushPromises();
    expect(location.pathname).toBe('/manager/products/4');
    mocks.confirmDialog.mockResolvedValue(true);
    await wrapper.get('button[title="К товарам"]').trigger('click');
    await flushPromises();
    expect(location.pathname).toBe('/manager/products');
    expect(mocks.replace).not.toHaveBeenCalled();
  });
});
