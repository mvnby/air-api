import { DOMWrapper, flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ get: vi.fn(), preview: vi.fn(), update: vi.fn() }));
vi.mock('../src/services/yandex-business-feed-settings', async () => {
  const actual = await vi.importActual<typeof import('../src/services/yandex-business-feed-settings')>('../src/services/yandex-business-feed-settings');
  return {
    ...actual,
    getYandexBusinessFeedSettings: mocks.get,
    previewYandexBusinessFeedSettings: mocks.preview,
    updateYandexBusinessFeedSettings: mocks.update,
  };
});

import YandexBusinessFeedSettingsDialog from '../src/components/yandex-business/YandexBusinessFeedSettingsDialog.vue';

const settings = {
  selection_mode: 'all_published' as const,
  include_services: true,
  require_ready_image: false,
  require_in_stock: false,
};
const preview = (productOfferCount = 12) => ({
  product_offer_count: productOfferCount,
  product_picture_count: 10,
  service_offer_count: 2,
  excluded_product_count: 0,
  excluded_products: [],
  collection_conflicts: [],
  categories_below_minimum_pictures: [],
  editorial_categories: [],
  settings: { ...settings },
});
const mounted: Array<ReturnType<typeof mount>> = [];
const mountDialog = () => {
  const wrapper = mount(YandexBusinessFeedSettingsDialog, { props: { open: true }, attachTo: document.body });
  mounted.push(wrapper);
  return wrapper;
};
const dialog = () => new DOMWrapper(document.body.querySelector('[role="dialog"]')!);
const saveButton = () => dialog().findAll('button').find(button => button.text().includes('Сохранить'))!;
const refreshButton = () => dialog().findAll('button').find(button => button.text().includes('Обновить'))!;

beforeEach(() => {
  mocks.get.mockReset(); mocks.preview.mockReset(); mocks.update.mockReset();
  mocks.get.mockResolvedValue({ ...settings });
  mocks.preview.mockResolvedValue(preview());
});
afterEach(() => { mounted.splice(0).forEach(wrapper => wrapper.unmount()); vi.clearAllMocks(); document.body.innerHTML = ''; });

describe('YandexBusinessFeedSettingsDialog', () => {
  it('loads settings and immediately previews them when opened initially', async () => {
    const wrapper = mountDialog();
    await flushPromises();

    expect(mocks.get).toHaveBeenCalledOnce();
    expect(mocks.preview).toHaveBeenCalledWith(settings);
    expect(dialog().text()).toContain('12');
    expect(saveButton().attributes('disabled')).toBeUndefined();
  });

  it('clears the preview and disables saving after editing a rule', async () => {
    const wrapper = mountDialog();
    await flushPromises();

    await dialog().get('input[value="curated_collections"]').setValue();
    await flushPromises();
    expect(dialog().text()).not.toContain('12');
    expect(dialog().text()).toContain('Обновите предпросмотр');
    expect(saveButton().attributes('disabled')).toBeDefined();
  });

  it('ignores a pending preview after the form changed', async () => {
    const wrapper = mountDialog();
    await flushPromises();
    let resolvePreview!: (result: ReturnType<typeof preview>) => void;
    mocks.preview.mockImplementationOnce(() => new Promise(resolve => { resolvePreview = resolve; }));
    await refreshButton().trigger('click');
    await dialog().get('input[value="curated_collections"]').setValue();
    resolvePreview(preview(99));
    await flushPromises();

    expect(dialog().text()).not.toContain('99');
    expect(saveButton().attributes('disabled')).toBeDefined();
  });

  it('enables saving only after an explicit refreshed preview matches the edited form', async () => {
    const wrapper = mountDialog();
    await flushPromises();
    await dialog().get('input[value="curated_collections"]').setValue();
    mocks.preview.mockResolvedValueOnce(preview(7));
    await refreshButton().trigger('click');
    await flushPromises();

    expect(mocks.preview).toHaveBeenLastCalledWith({ ...settings, selection_mode: 'curated_collections' });
    expect(dialog().text()).toContain('7');
    expect(saveButton().attributes('disabled')).toBeUndefined();
  });
});
