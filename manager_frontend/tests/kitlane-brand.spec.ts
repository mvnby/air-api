import { flushPromises, mount } from '@vue/test-utils';
import { defineComponent, nextTick } from 'vue';
import { afterEach, describe, expect, it, vi } from 'vitest';
import KitlanePartnerIdentity from '../src/components/kitlane/KitlanePartnerIdentity.vue';
import KitlanePlatformBrand from '../src/components/kitlane/KitlanePlatformBrand.vue';
import KitlaneShell from '../src/components/kitlane/KitlaneShell.vue';
import ManagerStorefrontSwitcherHost from '../src/components/manager/ManagerStorefrontSwitcherHost.vue';
import { useKitlaneIdentity } from '../src/composables/useKitlaneIdentity';
import { clearManagerSession, managerSession } from '../src/services/manager-session';
import { managerStorefrontSelection as selection } from '../src/services/manager-storefront-selection';

const brandApi = vi.hoisted(() => vi.fn());
vi.mock('../src/features/settings/storefront-settings-api', () => ({ storefrontSettingsApi: { brand: brandApi } }));

const storefront = (slug: string, name: string) => ({ slug, display_name: name, city: 'Город', default_locale: 'ru-BY', currency: 'BYN', is_default: false, is_current: false });
afterEach(() => { clearManagerSession(); brandApi.mockReset(); document.title = ''; });

describe('KitLane brand presentation', () => {
  it('uses a neutral workspace before the company context is known', () => {
    const wrapper = mount(KitlanePartnerIdentity);
    expect(wrapper.attributes('aria-label')).toBe('Рабочее пространство');
    expect(wrapper.find('img').exists()).toBe(false);
    expect(wrapper.get('.kitlane-partner-full').text()).toContain('РП');
  });

  it('keeps the complete long company name accessible', () => {
    const name = 'Демонстрационная компания с очень длинным названием';
    const wrapper = mount(KitlanePartnerIdentity, { props: { name, compact: true } });
    expect(wrapper.attributes('title')).toBe(name);
    expect(wrapper.attributes('aria-label')).toBe(name);
    expect(wrapper.get('.kitlane-partner-compact').text()).toBe('ДК');
  });

  it('falls back on a failed image and retries for a new company context', async () => {
    const wrapper = mount(KitlanePartnerIdentity, { props: { name: 'Демо Север', contextKey: 'one', logoUrl: '/media/logo.svg' } });
    const logo = wrapper.get('img');
    expect(logo.attributes('alt')).toBe('Демо Север');
    await logo.trigger('error');
    expect(wrapper.find('img').exists()).toBe(false);
    expect(wrapper.get('.kitlane-partner-full').text()).toContain('ДС');
    await wrapper.setProps({ name: 'Демо Юг', contextKey: 'two' });
    expect(wrapper.get('img').attributes('alt')).toBe('Демо Юг');
    await wrapper.setProps({ logoUrl: null });
    expect(wrapper.find('img').exists()).toBe(false);
    expect(wrapper.get('.kitlane-partner-full').text()).toContain('ДЮ');
  });

  it('uses a dedicated compact mark with independent error fallback', async () => {
    const wrapper = mount(KitlanePartnerIdentity, { props: { name: 'Демо Север', logoUrl: '/media/wide.svg', compactLogoUrl: '/media/mark.svg', desktopCompact: true } });
    await wrapper.get('.kitlane-partner-compact img').trigger('error');
    expect(wrapper.get('.kitlane-partner-full img').attributes('src')).toBe('/media/wide.svg');
    expect(wrapper.get('.kitlane-partner-compact').text()).toBe('ДС');
  });

  it('has an accessible platform label without an invented link', () => {
    const wrapper = mount(KitlanePlatformBrand);
    expect(wrapper.attributes('aria-label')).toBe('На платформе KitLane');
    expect(wrapper.text()).toContain('KitLane');
    expect(wrapper.find('a').exists()).toBe(false);
    expect(wrapper.get('img').attributes('src')).toContain('/assets/kitlane-mark.svg');
  });

  it('keeps one compact theme control and the existing storefront host', async () => {
    const wrapper = mount(KitlaneShell, { props: { name: 'Демо', contextKey: 'one', collapsed: false, mobileOpen: false, theme: 'light' }, global: { stubs: { ManagerStorefrontSwitcherHost: true } } });
    expect(wrapper.findAll('button[aria-label="Тёмная тема"]')).toHaveLength(1);
    await wrapper.get('button[aria-label="Тёмная тема"]').trigger('click');
    expect(wrapper.emitted('toggleTheme')).toHaveLength(1);
    expect(wrapper.findComponent({ name: 'ManagerStorefrontSwitcherHost' }).exists()).toBe(true);
    await wrapper.get('button[aria-label="Свернуть меню"]').trigger('click');
    expect(wrapper.emitted('update:collapsed')).toEqual([[true]]);
    wrapper.unmount();
  });
});

describe('authorized brand and document title', () => {
  it('follows only the current allowed storefront and clears during switching and logout', async () => {
    brandApi.mockRejectedValue(new Error('offline'));
    const Host = defineComponent({ setup: useKitlaneIdentity, template: '<span>{{ name }}</span>' });
    const wrapper = mount(Host);
    expect(document.title).toBe('KitLane');
    selection.storefronts.value = [storefront('north', 'Демо Север'), storefront('south', 'Демо Юг')];
    selection.selectedSlug.value = 'north';
    await nextTick();
    expect(wrapper.text()).toBe(''); // A cached list alone is not authorization.
    managerSession.isAuthenticated.value = true;
    await nextTick();
    expect(document.title).toBe('Демо Север · KitLane');
    managerSession.recoveryRequired.value = true;
    expect(document.title).toBe('KitLane');
    managerSession.recoveryRequired.value = false;
    selection.switching.value = true;
    expect(document.title).toBe('KitLane');
    selection.selectedSlug.value = 'south'; selection.switching.value = false;
    await nextTick();
    expect(wrapper.text()).toBe('Демо Юг');
    expect(document.title).toBe('Демо Юг · KitLane');
    selection.selectedSlug.value = 'unknown';
    expect(document.title).toBe('KitLane'); // Never choose an arbitrary first company.
    clearManagerSession();
    await nextTick();
    expect(wrapper.text()).toBe('');
    expect(document.title).toBe('KitLane');
    wrapper.unmount();
  });

  it('loads a scoped brand and drops a late response from the previous storefront', async () => {
    let resolveNorth!: (value: { display_name: string; logo_url: string; compact_logo_url: null }) => void;
    brandApi.mockImplementationOnce(() => new Promise(resolve => { resolveNorth = resolve; }));
    brandApi.mockResolvedValueOnce({ display_name: 'Юг сайт', logo_url: '/media/south.svg', compact_logo_url: null });
    selection.storefronts.value = [storefront('north', 'Север'), storefront('south', 'Юг')];
    selection.selectedSlug.value = 'north';
    const Host = defineComponent({ setup: useKitlaneIdentity, template: '<span>{{ name }}|{{ logoUrl }}</span>' });
    managerSession.isAuthenticated.value = true;
    const wrapper = mount(Host);
    selection.switching.value = true;
    expect(wrapper.text()).not.toContain('/media/');
    selection.selectedSlug.value = 'south';
    selection.switching.value = false;
    await flushPromises();
    expect(wrapper.text()).toContain('Юг сайт|/media/south.svg');
    resolveNorth({ display_name: 'Север сайт', logo_url: '/media/north.svg', compact_logo_url: null });
    await flushPromises();
    expect(wrapper.text()).toContain('Юг сайт|/media/south.svg');
    clearManagerSession();
    await nextTick();
    expect(wrapper.text()).not.toContain('/media/');
    wrapper.unmount();
  });
});

it('dispatches a storefront click with the selection instance intact', async () => {
  selection.storefronts.value = [storefront('north', 'Демо Север'), storefront('south', 'Демо Юг')];
  selection.selectedSlug.value = 'north';
  const switchTo = vi.spyOn(selection, 'switchTo').mockImplementation(function (this: typeof selection, slug) {
    expect(this).toBe(selection);
    expect(slug).toBe('south');
    return true;
  });
  const wrapper = mount(ManagerStorefrontSwitcherHost, { props: { collapsed: false } });
  await wrapper.get('button[aria-label="Переключиться: Демо Юг, Город"]').trigger('click');
  expect(switchTo).toHaveBeenCalledOnce();
  switchTo.mockRestore();
  wrapper.unmount();
});
