import { flushPromises, mount } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ get: vi.fn(), save: vi.fn(), preview: vi.fn(), clone: vi.fn(), uploadLogo: vi.fn() }));
vi.mock('../src/client', () => ({
  OpenAPI: {},
  ManagerDocumentSystemService: { listManagerDocumentLegalEntities: vi.fn().mockResolvedValue({ items: [] }) },
}));
vi.mock('../src/features/documents/settings/DocumentLegalEntitiesPanel.vue', () => ({ default: { template: '<div />' } }));
vi.mock('../src/features/settings/storefront-settings-api', () => ({
  StorefrontSettingsApiError: class StorefrontSettingsApiError extends Error { status: number; constructor(message: string, status: number) { super(message); this.status = status; } },
  storefrontSettingsApi: { get: mocks.get, save: mocks.save, previewTemplate: mocks.preview, cloneTemplate: mocks.clone, uploadLogo: mocks.uploadLogo },
}));
import SettingsView from '../src/views/SettingsView.vue';

const settings = {
  site: { display_name: 'Partner', city: 'Минск', phone: '', email: '', address: '', work_hours: '', support_telegram_url: '', logo_asset_id: null, compact_logo_asset_id: null, logo_url: null, compact_logo_url: null },
  services: [
    { key: 'installation', title: 'Монтаж', description: 'Аккуратно', enabled: true },
    { key: 'repair', title: 'Ремонт', description: 'Быстро', enabled: false },
  ], version: 3, updated_at: null,
};

describe('storefront settings', () => {
  it('hydrates settings, switches a service directly and saves the changed binary state', async () => {
    mocks.get.mockResolvedValue(settings); mocks.preview.mockResolvedValue({ source_counts: { services: 5, tariffs: 2, tariff_rules: 3, installation_rates: 1 }, source_fingerprint: 'safe', target_counts: { services: 0, tariffs: 0, tariff_rules: 0, installation_rates: 0 }, can_clone: true });
    mocks.save.mockResolvedValue(settings);
    const wrapper = mount(SettingsView, { global: { stubs: { DocumentLegalEntitiesPanel: true } } });
    await flushPromises();
    await wrapper.findAll('button').find(button => button.text() === 'Услуги')!.trigger('click');
    await flushPromises();
    const checkbox = wrapper.findAll('input[type="checkbox"]')[1];
    await checkbox.setValue(true);
    await wrapper.findAll('button').find(button => button.text() === 'Сохранить')!.trigger('click');
    await flushPromises();
    expect(mocks.save).toHaveBeenCalledWith(expect.objectContaining({
      site: expect.objectContaining({ display_name: 'Partner' }),
      services: expect.arrayContaining([expect.objectContaining({ key: 'repair', enabled: true })]),
      version: 3,
    }));
  });

  it('shows a recoverable message when saving an out-of-date version', async () => {
    mocks.get.mockResolvedValue(settings); mocks.save.mockRejectedValue(Object.assign(new Error('conflict'), { status: 409, name: 'StorefrontSettingsApiError' }));
    const wrapper = mount(SettingsView, { global: { stubs: { DocumentLegalEntitiesPanel: true } } });
    await flushPromises();
    await wrapper.findAll('button').find(button => button.text() === 'Сайт')!.trigger('click');
    await wrapper.get('input[type="email"]').setValue('public@example.test');
    await wrapper.findAll('button').find(button => button.text() === 'Сохранить')!.trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('изменились у другого пользователя');
  });

  it('uploads a storefront logo and asks for publication through Save', async () => {
    mocks.get.mockResolvedValue(settings);
    mocks.uploadLogo.mockResolvedValue({ id: 42, url: '/media/library/original/logo.svg' });
    mocks.save.mockResolvedValue(settings);
    const wrapper = mount(SettingsView, { global: { stubs: { DocumentLegalEntitiesPanel: true } } });
    await flushPromises();
    await wrapper.findAll('button').find(button => button.text() === 'Сайт')!.trigger('click');
    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['logo'], 'logo.svg', { type: 'image/svg+xml' })] });
    await input.trigger('change');
    await flushPromises();
    expect(wrapper.text()).toContain('Сохраните настройки');
    await wrapper.findAll('button').find(button => button.text() === 'Сохранить')!.trigger('click');
    expect(mocks.save).toHaveBeenCalledWith(expect.objectContaining({ site: expect.objectContaining({ logo_asset_id: 42 }) }));
  });
});
