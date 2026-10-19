import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import CatalogAccessoriesPanel from '../src/components/catalog/CatalogAccessoriesPanel.vue';

const { request } = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('../src/client/core/request', () => ({ request }));

const inherited = { accessory_product_id: 7, title: 'Wi-Fi Module FG', slug: 'wifi-fg', accessory_type: 'wifi_module', is_published: true, inherited: true, override: null, is_enabled: true };
const workspace = (items: Array<Record<string, unknown>> = [inherited]) => ({ target_type: 'product', target_id: 5, series_id: 3, items });

describe('CatalogAccessoriesPanel', () => {
  beforeEach(() => request.mockReset());

  it('excludes an inherited accessory with one switch and resets the override', async () => {
    request.mockResolvedValueOnce(workspace());
    const wrapper = mount(CatalogAccessoriesPanel, { props: { targetType: 'product', targetId: 5 } });
    await flushPromises();
    expect(wrapper.text()).toContain('Из серии');
    expect(wrapper.get('[role="switch"]').attributes('aria-checked')).toBe('true');
    request.mockResolvedValueOnce(workspace([{ ...inherited, override: false, is_enabled: false }]));
    await wrapper.get('[role="switch"]').trigger('click');
    await flushPromises();
    expect(request.mock.calls[1]?.[1]).toMatchObject({ method: 'PUT', body: { overrides: [{ accessory_product_id: 7, is_enabled: false }] } });
    expect(wrapper.get('[role="switch"]').attributes('aria-checked')).toBe('false');
    request.mockResolvedValueOnce(workspace());
    await wrapper.get('[aria-label="Вернуть правило серии"]').trigger('click');
    await flushPromises();
    expect(request.mock.calls[2]?.[1]).toMatchObject({ method: 'PUT', body: { overrides: [] } });
    expect(wrapper.get('[role="switch"]').attributes('aria-checked')).toBe('true');
  });

  it('searches only accessory products and assigns a model-specific item', async () => {
    request.mockResolvedValueOnce(workspace([]));
    const wrapper = mount(CatalogAccessoriesPanel, { props: { targetType: 'product', targetId: 5 } });
    await flushPromises();
    await wrapper.get('input[type="search"]').setValue('module');
    request.mockResolvedValueOnce({ items: [
      { id: 7, title: 'Wi-Fi Module FG', slug: 'wifi-fg', product_kind: 'accessory', specs: { accessory_type: 'wifi_module' }, is_published: true },
      { id: 8, title: 'Air Conditioner', product_kind: 'complete_split_system' },
    ] });
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(request.mock.calls[1]?.[1]).toMatchObject({ query: { product_kind: 'accessory', search: 'module', limit: 100 } });
    expect(wrapper.text()).not.toContain('Air Conditioner');
    request.mockResolvedValueOnce(workspace([{ ...inherited, inherited: false, override: true }]));
    await wrapper.get('[aria-label="Добавить Wi-Fi Module FG"]').trigger('click');
    await flushPromises();
    expect(request.mock.calls[2]?.[1]).toMatchObject({ body: { overrides: [{ accessory_product_id: 7, is_enabled: true }] } });
    expect(wrapper.text()).toContain('Для этой модели');
  });

  it('removes a series accessory without model overrides and retains server errors', async () => {
    request.mockResolvedValueOnce({ target_type: 'series', target_id: 3, series_id: 3, items: [{ ...inherited, inherited: false }] });
    const wrapper = mount(CatalogAccessoriesPanel, { props: { targetType: 'series', targetId: 3 } });
    await flushPromises();
    request.mockRejectedValueOnce({ body: { detail: 'Не удалось сохранить совместимость' } });
    await wrapper.get('[aria-label="Убрать Wi-Fi Module FG"]').trigger('click');
    await flushPromises();
    expect(request.mock.calls[1]?.[1]).toMatchObject({ method: 'PUT', body: { accessory_product_ids: [] } });
    expect(wrapper.get('[role="alert"]').text()).toBe('Не удалось сохранить совместимость');
    expect(wrapper.text()).toContain('Wi-Fi Module FG');
  });

  it('discards search results from the previously opened model', async () => {
    request.mockResolvedValueOnce(workspace([]));
    const wrapper = mount(CatalogAccessoriesPanel, { props: { targetType: 'product', targetId: 5 } });
    await flushPromises();
    let finishSearch: (value: unknown) => void = () => undefined;
    request.mockImplementationOnce(() => new Promise(resolve => { finishSearch = resolve; }));
    await wrapper.get('input[type="search"]').setValue('old module');
    await wrapper.get('form').trigger('submit');
    request.mockResolvedValueOnce({ ...workspace([]), target_id: 9 });
    await wrapper.setProps({ targetId: 9 });
    await flushPromises();
    finishSearch({ items: [{ id: 7, title: 'Old Model Module', product_kind: 'accessory' }] });
    await flushPromises();
    expect(wrapper.text()).not.toContain('Old Model Module');
    await wrapper.get('input[type="search"]').setValue('new module');
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined();
  });
});
