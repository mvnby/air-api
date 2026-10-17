import type { ManagerAuthStatusResponse } from './client';

export const MANAGER_CAPABILITY = {
  crmManage: 'crm.manage',
  workerPayRead: 'worker.pay.read',
  workerPayManage: 'worker.pay.manage',
  installerWorksRead: 'installer.works.read',
  catalogMasterRead: 'catalog.master.read',
  catalogMasterEdit: 'catalog.master.edit',
  catalogMasterDelete: 'catalog.master.delete',
  storefrontOffersRead: 'storefront.offers.read',
  storefrontCollectionsManage: 'storefront.collections.manage',
  platformManage: 'platform.manage',
  platformCompaniesManage: 'platform.companies.manage',
  staffManage: 'staff.manage',
  infrastructureManage: 'infrastructure.manage',
  analyticsManage: 'analytics.manage',
  documentsManage: 'documents.manage',
  settingsManage: 'settings.manage',
  servicesManage: 'services.manage',
  callRecordingsManage: 'call_recordings.manage',
} as const;

export type ManagerCapability = typeof MANAGER_CAPABILITY[keyof typeof MANAGER_CAPABILITY];

export const hasManagerCapability = (
  auth: Pick<ManagerAuthStatusResponse, 'capabilities'> & Partial<Pick<ManagerAuthStatusResponse, 'is_system_tenant'>> | null | undefined,
  capability: ManagerCapability,
): boolean => Boolean(auth?.capabilities?.includes(capability) && (![MANAGER_CAPABILITY.platformManage, MANAGER_CAPABILITY.infrastructureManage].some(value => value === capability) || auth.is_system_tenant !== false));

export const canReadOwnInstallerWorks = (
  auth: Pick<ManagerAuthStatusResponse, 'capabilities' | 'tenant_membership_id'> | null | undefined,
): boolean => hasManagerCapability(auth, MANAGER_CAPABILITY.installerWorksRead)
  || Boolean(auth?.tenant_membership_id && hasManagerCapability(auth, MANAGER_CAPABILITY.crmManage));

export const requiredCapabilityForManagerPath = (path: string): ManagerCapability | null => {
  if (path === '/manager' || path === '/manager/' || path === '/manager/profile') return null;
  if (path === '/manager/my-pay' || path === '/manager/my-money' || path === '/manager/my-work' || path.startsWith('/manager/my-work/')) return MANAGER_CAPABILITY.installerWorksRead;
  if (path.startsWith('/manager/worker-pay')) return MANAGER_CAPABILITY.workerPayRead;
  if (path.startsWith('/manager/settings/calls') || path.startsWith('/manager/calls')) {
    return MANAGER_CAPABILITY.callRecordingsManage;
  }
  if (path.startsWith('/manager/integrations')) {
    return MANAGER_CAPABILITY.analyticsManage;
  }
  if (path.startsWith('/manager/settings/documents')) {
    return MANAGER_CAPABILITY.documentsManage;
  }
  if (path.startsWith('/manager/platform/companies')) return MANAGER_CAPABILITY.platformCompaniesManage;
  if (path.startsWith('/manager/company/sites')) return MANAGER_CAPABILITY.staffManage;
  if (path.startsWith('/manager/platform/access')) return MANAGER_CAPABILITY.infrastructureManage;
  if (path.startsWith('/manager/brands') || path.startsWith('/manager/features') || path.startsWith('/manager/tags')) {
    return MANAGER_CAPABILITY.catalogMasterEdit;
  }
  if (path.startsWith('/manager/settings/platform') || path.startsWith('/manager/settings/backup')) {
    return MANAGER_CAPABILITY.infrastructureManage;
  }
  if (
    path.startsWith('/manager/worker-money')
    || path.startsWith('/manager/tasks')
    || path.startsWith('/manager/leads')
    || path.startsWith('/manager/orders')
    || path.startsWith('/manager/calendar')
    || path.startsWith('/manager/customers')
    || path.startsWith('/manager/equipment')
    || path.startsWith('/manager/mail')
  ) return MANAGER_CAPABILITY.crmManage;
  if (/^\/manager\/products\/\d+(?:\/|$)/.test(path)) {
    return MANAGER_CAPABILITY.catalogMasterEdit;
  }
  if (path === '/manager/catalog-decision' || path === '/manager/catalog-decision/') {
    return MANAGER_CAPABILITY.crmManage;
  }
  if (path.startsWith('/manager/installation-discounts')) {
    return MANAGER_CAPABILITY.platformManage;
  }
  if (path === '/manager/products' || path === '/manager/products/') {
    return MANAGER_CAPABILITY.catalogMasterRead;
  }
  if (path.startsWith('/manager/product-collections')) {
    return MANAGER_CAPABILITY.storefrontCollectionsManage;
  }
  if (
    path.startsWith('/manager/installation-rates')
    || path.startsWith('/manager/tariffs')
    || path.startsWith('/manager/service-estimates')
  ) return MANAGER_CAPABILITY.servicesManage;
  if (
    path.startsWith('/manager/staff')
    || path.startsWith('/manager/users')
    || path.startsWith('/manager/installers')
  ) return MANAGER_CAPABILITY.staffManage;
  if (path.startsWith('/manager/settings')) {
    return MANAGER_CAPABILITY.settingsManage;
  }
  return MANAGER_CAPABILITY.platformManage;
};

export const isManagerPathAllowed = (
  auth: Pick<ManagerAuthStatusResponse, 'capabilities'> & Partial<Pick<ManagerAuthStatusResponse, 'tenant_membership_id'>> | null | undefined,
  path: string,
): boolean => {
  if (path === '/manager/my-pay' || path === '/manager/my-money' || path === '/manager/my-work' || path.startsWith('/manager/my-work/')) return canReadOwnInstallerWorks(auth);
  const required = requiredCapabilityForManagerPath(path);
  return required === null || hasManagerCapability(auth, required);
};
