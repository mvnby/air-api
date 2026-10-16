import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import InstallerWorksView from '../src/views/InstallerWorksView.vue';
import InstallerCollectionInstruction from '../src/components/installer/InstallerCollectionInstruction.vue';
import InstallerMaterials from '../src/components/installer/InstallerMaterials.vue';
import { installerWorkspaceApi, loadInstallerMaterial } from '../src/services/installer-workspace';
import { managerSession, clearManagerSession } from '../src/services/manager-session';
import { managerStorefrontSelection } from '../src/services/manager-storefront-selection';
vi.mock('../src/services/installer-workspace', () => ({ installerWorkspaceApi: { works: vi.fn(), detail: vi.fn() }, loadInstallerMaterial: vi.fn() }));
const summary = { id: 9, order_id: 55, work_stage_id: 2, version: 0, title: 'Монтаж блока', status: 'planned', start_time: null, customer_name: 'Анна', address: 'ул. Садовая, 7', collection: { status: 'ready' as const, amount: '0.00', currency: 'EUR' as const, recipient_name: 'Монтажник', updated_at: null } };
const detail = { ...summary, customer_phone: '+375 29 111-22-33', instructions: 'Крепление на стену', equipment: [{ key: 'e1', name: 'Наружный блок', brand: 'Brand', model: 'X2', serial: 'SN-77', quantity: 1, technical_specs: [{ label: 'Мощность', value: '2.5 кВт' }] }], materials: [] };
let wrapper: VueWrapper | undefined;
beforeEach(() => {
  vi.resetAllMocks(); window.history.replaceState({}, '', '/manager/my-work'); managerSession.isAuthenticated.value = true; managerSession.auth.value = { username: 'installer', status: 'authenticated', staff_user_id: 3, tenant_id: 2, storefront_id: 5, capabilities: ['installer.works.read'] };
  managerStorefrontSelection.selectedTenantId.value = 2; managerStorefrontSelection.selectedSlug.value = 'main';
  vi.mocked(installerWorkspaceApi.works).mockResolvedValue({ items: [summary], total: 31, page: 1, limit: 30 }); vi.mocked(installerWorkspaceApi.detail).mockResolvedValue(detail);
});
afterEach(() => { wrapper?.unmount(); wrapper = undefined; clearManagerSession(); vi.restoreAllMocks(); });
describe('personal installer works', () => {
  it('loads a paginated read-only list, opens the safe technical card and preserves explicit zero currency', async () => {
    wrapper = mount(InstallerWorksView); await flushPromises();
    expect(installerWorkspaceApi.works).toHaveBeenCalledWith(1, 'all'); expect(wrapper.text()).toContain('0.00 EUR');
    await wrapper.get('[aria-label="Следующая страница"]').trigger('click'); await flushPromises(); expect(installerWorkspaceApi.works).toHaveBeenLastCalledWith(2, 'all');
    await wrapper.get('[aria-label="Открыть работу: Монтаж блока"]').trigger('click'); await flushPromises();
    expect(installerWorkspaceApi.detail).toHaveBeenCalledWith(9); expect(wrapper.text()).toContain('2.5 кВт'); expect(wrapper.text()).toContain('SN-77'); expect(wrapper.get('a[href^="tel:"]').attributes('href')).toBe('tel:+375291112233');
    expect(wrapper.findAll('input,select,textarea')).toHaveLength(0); expect(wrapper.text()).not.toMatch(/Маржа|Закупка|Подтвердить оплату|Зарплата/);
  });
  it('resets the page for a changed period and ignores a stale context response', async () => {
    let resolve!: (value: any) => void; vi.mocked(installerWorkspaceApi.works).mockImplementationOnce(() => new Promise(done => { resolve = done; }));
    wrapper = mount(InstallerWorksView); await flushPromises();
    managerStorefrontSelection.selectedTenantId.value = 8; await flushPromises();
    resolve({ items: [{ ...summary, title: 'Старые работы другой компании' }], total: 1, page: 1, limit: 30 }); await flushPromises(); expect(wrapper.text()).not.toContain('Старые работы другой компании');
    await wrapper.get('[aria-label="Следующая страница"]').trigger('click'); await flushPromises();
    await wrapper.findAll('button').find(button => button.text() === 'Сегодня')!.trigger('click'); await flushPromises(); expect(installerWorkspaceApi.works).toHaveBeenLastCalledWith(1, 'today');
  });
  it('opens a verified bot detail URL through only the safe detail endpoint', async () => {
    window.history.replaceState({}, '', '/manager/my-work/9?company=2&site=main'); wrapper = mount(InstallerWorksView); await flushPromises(); expect(installerWorkspaceApi.detail).toHaveBeenCalledWith(9); expect(installerWorkspaceApi.works).not.toHaveBeenCalled(); expect(wrapper.text()).toContain('Крепление на стену');
  });
  it('does not retain removed assignment content after a detail denial', async () => {
    vi.mocked(installerWorkspaceApi.detail).mockRejectedValue({ status: 404, body: { detail: 'Работа недоступна' } }); wrapper = mount(InstallerWorksView); await flushPromises();
    await wrapper.get('[aria-label="Открыть работу: Монтаж блока"]').trigger('click'); await flushPromises(); expect(wrapper.find('[data-testid="installer-equipment"]').exists()).toBe(false); expect(wrapper.find('[role="alert"]').exists()).toBe(true);
  });
  it('hides all amounts for noncollectors, missing instructions and stale instructions', () => {
    for (const status of ['not_assigned', 'not_collector', 'requires_review'] as const) {
      const item = mount(InstallerCollectionInstruction, { props: { collection: { ...summary.collection, status, amount: 'SECRET-777' } } }); expect(item.text()).not.toContain('SECRET-777'); item.unmount();
    }
  });
  it('fetches only an explicitly published material and renders a local blob rather than a credentialless endpoint', async () => {
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:private-photo') }); Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
    vi.mocked(loadInstallerMaterial).mockResolvedValue(new Blob(['photo'], { type: 'image/webp' }));
    wrapper = mount(InstallerMaterials, { props: { materials: [{ id: 10, label: 'Разрешённая схема', file_kind: 'image', content_url: '/api/installer/works/9/materials/10/content' }] }, attachTo: document.body });
    await wrapper.get('button').trigger('click'); await flushPromises(); expect(loadInstallerMaterial).toHaveBeenCalledWith('/api/installer/works/9/materials/10/content'); expect(URL.createObjectURL).toHaveBeenCalledTimes(1); expect(document.querySelector('[role=dialog] img')?.getAttribute('src')).toBe('blob:private-photo');
    (document.querySelector('[aria-label="Закрыть материал"]') as HTMLButtonElement).click(); await flushPromises(); expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:private-photo');
  });
});
