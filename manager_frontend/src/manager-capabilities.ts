import type { ManagerAuthStatusResponse } from './client';

export const MANAGER_CAPABILITY = {
  crmManage: 'crm.manage',
  catalogMasterRead: 'catalog.master.read',
  storefrontOffersRead: 'storefront.offers.read',
  storefrontCollectionsManage: 'storefront.collections.manage',
  platformManage: 'platform.manage',
  staffManage: 'staff.manage',
  infrastructureManage: 'infrastructure.manage',
  analyticsManage: 'analytics.manage',
} as const;

export type ManagerCapability = typeof MANAGER_CAPABILITY[keyof typeof MANAGER_CAPABILITY];

export const hasManagerCapability = (
  auth: Pick<ManagerAuthStatusResponse, 'capabilities'> | null | undefined,
  capability: ManagerCapability,
): boolean => Boolean(auth?.capabilities?.includes(capability));

export const requiredCapabilityForManagerPath = (path: string): ManagerCapability | null => {
  if (path === '/manager' || path === '/manager/' || path === '/manager/profile') return null;
  if (path.startsWith('/manager/integrations')) {
    return MANAGER_CAPABILITY.analyticsManage;
  }
  if (
    path.startsWith('/manager/leads')
    || path.startsWith('/manager/orders')
    || path.startsWith('/manager/calendar')
    || path.startsWith('/manager/customers')
    || path.startsWith('/manager/equipment')
  ) return MANAGER_CAPABILITY.crmManage;
  if (/^\/manager\/products\/\d+(?:\/|$)/.test(path)) {
    return MANAGER_CAPABILITY.platformManage;
  }
  if (path === '/manager/catalog-decision' || path === '/manager/catalog-decision/') {
    return MANAGER_CAPABILITY.platformManage;
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
    path.startsWith('/manager/staff')
    || path.startsWith('/manager/users')
    || path.startsWith('/manager/installers')
  ) return MANAGER_CAPABILITY.staffManage;
  if (path.startsWith('/manager/settings')) {
    return MANAGER_CAPABILITY.infrastructureManage;
  }
  return MANAGER_CAPABILITY.platformManage;
};

export const isManagerPathAllowed = (
  auth: Pick<ManagerAuthStatusResponse, 'capabilities'> | null | undefined,
  path: string,
): boolean => {
  const required = requiredCapabilityForManagerPath(path);
  return required === null || hasManagerCapability(auth, required);
};
