import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ companies: vi.fn(), managerMe: vi.fn(), managerSites: vi.fn(), request: vi.fn() }));
vi.mock('../src/services/manager-companies', () => ({ managerCompaniesApi: { choices: mocks.companies } }));
vi.mock('../src/client/core/request', () => ({ request: mocks.request }));
vi.mock('../src/client', () => ({ OpenAPI: {}, LoginService: {}, ManagerService: { readUserMe: mocks.managerMe, listManagerStorefronts: mocks.managerSites } }));
import { bootstrapManagerSession, clearManagerSession, managerSession } from '../src/services/manager-session';
import { refreshManagerIdentity } from '../src/services/manager-profile';
import { getManagerStorefrontRequestHeaders } from '../src/services/manager-storefront-selection';
import { canReadOwnInstallerWorks, isManagerPathAllowed } from '../src/manager-capabilities';
const company = { tenant_id: 2, slug: 'partner', display_name: 'Компания', role: 'installer', membership_id: 12, access_kind: 'membership', is_system: false, demo_read_only: false, default_storefront_slug: 'main' };
const sites = { items: [{ id: 5, slug: 'main', display_name: 'Сайт', is_default: true, is_current: true }] };
const auth = { username: 'worker', status: 'authenticated', staff_user_id: 4, tenant_id: 2, storefront_id: 5, role: 'installer', tenant_membership_id: 12, capabilities: ['installer.works.read'] };
beforeEach(() => {
  vi.resetAllMocks(); window.sessionStorage.clear(); window.history.replaceState({}, '', '/manager/my-work');
  mocks.companies.mockResolvedValue({ staff_user_id: 4, username: 'worker', default_tenant_id: 2, items: [company], total: 1, page: 1, limit: 100 });
  mocks.request.mockImplementation((_config, options) => Promise.resolve(options.url.endsWith('/storefronts') ? sites : auth));
});
afterEach(clearManagerSession);
describe('installer workspace boundary', () => {
  it('bootstraps without calling Manager business endpoints and scopes only business requests', async () => {
    await bootstrapManagerSession();
    expect(mocks.request.mock.calls.map(call => call[1].url)).toEqual(['/api/installer/storefronts', '/api/installer/me']);
    expect(mocks.managerMe).not.toHaveBeenCalled(); expect(mocks.managerSites).not.toHaveBeenCalled();
    expect(managerSession.isAuthenticated.value).toBe(true);
    expect(getManagerStorefrontRequestHeaders('/api/installer/works')).toEqual({ 'X-MVN-Manager-Tenant': '2', 'X-MVN-Manager-Storefront': 'main' });
    expect(getManagerStorefrontRequestHeaders('/api/manager/account/profile')).toEqual({});
    expect(getManagerStorefrontRequestHeaders('/api/manager/account/telegram/link-challenges')).toEqual({});
    expect(isManagerPathAllowed(auth, '/manager/my-work')).toBe(true);
    for (const path of ['/manager/orders', '/manager/products', '/manager/staff', '/manager/equipment', '/manager/settings', '/manager/my-workforce']) expect(isManagerPathAllowed(auth, path), path).toBe(false);
  });
  it('refreshes personal identity in the installer realm with a fresh object and unchanged context', async () => {
    await bootstrapManagerSession(); const previous = managerSession.auth.value;
    mocks.request.mockResolvedValue({ ...auth, display_name: 'Новое имя' }); await refreshManagerIdentity();
    expect(mocks.request.mock.lastCall?.[1].url).toBe('/api/installer/me'); expect(managerSession.auth.value).not.toBe(previous);
    expect(managerSession.auth.value?.display_name).toBe('Новое имя'); expect(mocks.companies).toHaveBeenCalledTimes(1); expect(mocks.managerMe).not.toHaveBeenCalled();
  });
  it('preserves Manager bootstrap for ordinary sales membership', async () => {
    mocks.companies.mockResolvedValue({ staff_user_id: 4, username: 'worker', default_tenant_id: 2, items: [{ ...company, role: 'manager' }], total: 1 });
    mocks.managerSites.mockResolvedValue(sites); mocks.managerMe.mockResolvedValue({ ...auth, role: 'manager', capabilities: ['crm.manage'] }); await bootstrapManagerSession();
    expect(mocks.managerSites).toHaveBeenCalledTimes(1); expect(mocks.managerMe).toHaveBeenCalledTimes(1); expect(mocks.request).not.toHaveBeenCalled();
  });
  it('offers personal work only to installer capability or real CRM members', () => {
    expect(canReadOwnInstallerWorks({ capabilities: ['crm.manage'], tenant_membership_id: 12 })).toBe(true);
    expect(isManagerPathAllowed({ capabilities: ['crm.manage'], tenant_membership_id: 12 }, '/manager/my-work/7')).toBe(true);
    expect(canReadOwnInstallerWorks({ capabilities: ['crm.manage'], tenant_membership_id: null })).toBe(false);
    expect(isManagerPathAllowed({ capabilities: ['crm.manage'] }, '/manager/my-work')).toBe(false);
  });
});
