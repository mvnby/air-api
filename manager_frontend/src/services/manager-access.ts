import { ManagerAccessService, type ManagerAccessItem, type ManagerAccessUpdate } from '../client';

export const catalogPermissions = {
  edit: 'catalog.master.edit',
  delete: 'catalog.master.delete',
} as const;

export const managerAccessApi = {
  list: (page: number, search?: string) => ManagerAccessService.listManagerAccess(page, 50, search),
  update: (item: ManagerAccessItem, permissions: string[]) => ManagerAccessService.updateManagerAccess(item.membership_id, {
    permissions: permissions.filter((value): value is ManagerAccessUpdate['permissions'][number] =>
      value === catalogPermissions.edit || value === catalogPermissions.delete),
    expected_updated_at: item.updated_at,
  } satisfies ManagerAccessUpdate),
};

export const toggleCatalogPermission = (permissions: string[], permission: 'edit' | 'delete', enabled: boolean): string[] => {
  const next = new Set(permissions);
  if (enabled) {
    next.add(catalogPermissions[permission]);
    if (permission === 'delete') next.add(catalogPermissions.edit);
  } else {
    next.delete(catalogPermissions[permission]);
    if (permission === 'edit') next.delete(catalogPermissions.delete);
  }
  return [...next];
};
