import { computed } from 'vue';
import { hasManagerCapability, MANAGER_CAPABILITY } from '../manager-capabilities';
import { managerSession } from '../services/manager-session';

export const useCatalogAccess = () => ({
  canManagePlatform: computed(() => hasManagerCapability(managerSession.auth.value, MANAGER_CAPABILITY.platformManage)),
  canDeleteCatalog: computed(() => hasManagerCapability(managerSession.auth.value, MANAGER_CAPABILITY.catalogMasterDelete)),
});
