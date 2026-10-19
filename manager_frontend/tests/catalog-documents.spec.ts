import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ get: vi.fn(), replace: vi.fn(), upload: vi.fn() }));
vi.mock('../src/services/catalog-documents-api', () => ({ catalogDocumentsApi: mocks }));

import CatalogDocumentsPanel from '../src/components/catalog/CatalogDocumentsPanel.vue';
import { managerSession } from '../src/services/manager-session';

const cancelable = <T,>(value: T) => Object.assign(Promise.resolve(value), { cancel: vi.fn(), isCancelled: false });
const material = (id = 1) => ({ id, title: 'Каталог 2026', url: 'https://example.com/catalog.pdf', source_url: null, kind: 'catalog', language: 'ru', year: 2026, visibility: 'public', inherit_to_products: true, origin_type: 'brand', origin_id: 8, origin_title: 'Example', inherited: true });

beforeEach(() => {
  Object.values(mocks).forEach(mock => mock.mockReset());
  managerSession.isAuthenticated.value = true;
  managerSession.auth.value = { capabilities: ['catalog.master.edit'] } as any;
  mocks.get.mockReturnValue(cancelable({ own: [], inherited: [material()], effective: [material()] }));
});
afterEach(() => { managerSession.isAuthenticated.value = false; managerSession.auth.value = null; });

describe('CatalogDocumentsPanel', () => {
  it('preserves inherited origins and saves only the edited own set', async () => {
    mocks.replace.mockReturnValue(cancelable({ own: [], inherited: [material()], effective: [material()] }));
    const wrapper = mount(CatalogDocumentsPanel, { props: { targetType: 'series', targetId: 3 } });
    await flushPromises();
    expect(wrapper.text()).toContain('Бренд: Example');
    expect(wrapper.findAll('fieldset')).toHaveLength(0);
    await wrapper.findAll('button').find(button => button.text() === 'Добавить ссылку')!.trigger('click');
    const fields = wrapper.get('fieldset');
    await fields.findAll('input')[0]!.setValue('Руководство');
    await fields.findAll('input')[1]!.setValue('https://example.com/operation.pdf');
    await fields.findAll('select')[1]!.setValue('internal');
    await wrapper.findAll('button').find(button => button.text() === 'Сохранить документы')!.trigger('click');
    await flushPromises();
    expect(mocks.replace).toHaveBeenCalledWith('series', 3, [{ title: 'Руководство', url: 'https://example.com/operation.pdf', kind: 'other', source_url: null, language: null, year: null, visibility: 'internal', inherit_to_products: true }]);
    expect(wrapper.text()).toContain('Документы сохранены.');
    wrapper.unmount();
  });

  it('shows research links read-only when catalog editing permission is absent', async () => {
    managerSession.auth.value = { capabilities: ['catalog.master.read'] } as any;
    mocks.get.mockReturnValue(cancelable({ own: [], inherited: [{ ...material(), visibility: 'internal' }], effective: [] }));
    const wrapper = mount(CatalogDocumentsPanel, { props: { targetType: 'product', targetId: 4 } });
    await flushPromises();
    expect(wrapper.text()).toContain('Только Manager и AI');
    expect(wrapper.text()).not.toContain('Добавить ссылку');
    expect(wrapper.get('a').attributes('href')).toBe('https://example.com/catalog.pdf');
    wrapper.unmount();
  });

  it('adds a successfully uploaded public file as an unsaved own document', async () => {
    mocks.upload.mockReturnValue(cancelable({ title: 'Инструкция', url: '/media/catalog-documents/original/manual.pdf' }));
    const wrapper = mount(CatalogDocumentsPanel, { props: { targetType: 'brand', targetId: 8 } });
    await flushPromises();
    const file = new File(['%PDF-1.7'], 'Manual.pdf', { type: 'application/pdf' });
    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true });
    await input.trigger('change');
    await flushPromises();
    expect(mocks.upload).toHaveBeenCalledWith('brand', 8, file);
    expect(wrapper.findAll('fieldset')).toHaveLength(1);
    expect(wrapper.text()).toContain('Есть несохранённые изменения');
    expect(mocks.replace).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('does not let a previous target response replace the newly selected workspace', async () => {
    let finish: ((value: unknown) => void) | undefined;
    const oldRequest = Object.assign(new Promise(resolve => { finish = resolve; }), { cancel: vi.fn(), isCancelled: false });
    mocks.get.mockReturnValueOnce(oldRequest).mockReturnValueOnce(cancelable({ own: [], inherited: [{ ...material(), origin_title: 'New brand' }], effective: [] }));
    const wrapper = mount(CatalogDocumentsPanel, { props: { targetType: 'series', targetId: 3 } });
    await wrapper.setProps({ targetId: 6 });
    await flushPromises();
    finish?.({ own: [], inherited: [{ ...material(), origin_title: 'Old brand' }], effective: [] });
    await flushPromises();
    expect(oldRequest.cancel).toHaveBeenCalled();
    expect(wrapper.text()).toContain('New brand');
    expect(wrapper.text()).not.toContain('Old brand');
    wrapper.unmount();
  });

  it('lets a parent save gate keep an invalid document draft open', async () => {
    const wrapper = mount(CatalogDocumentsPanel, { props: { targetType: 'series', targetId: 3 } });
    await flushPromises();
    await wrapper.findAll('button').find(button => button.text() === 'Добавить ссылку')!.trigger('click');
    const accepted = await (wrapper.vm as unknown as { save: () => Promise<boolean> }).save();
    expect(accepted).toBe(false);
    expect(mocks.replace).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('Укажите название и ссылку');
    expect(wrapper.text()).toContain('Есть несохранённые изменения');
    wrapper.unmount();
  });
});
