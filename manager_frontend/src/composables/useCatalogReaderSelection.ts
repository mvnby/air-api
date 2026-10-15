import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { managerSession } from '../services/manager-session';
import { MANAGER_CAPABILITY, hasManagerCapability } from '../manager-capabilities';
import {
  catalogDecisionSelectionStorageKey, loadCatalogDecisionSelection, saveCatalogDecisionSelection,
  type CatalogDecisionSelectionItem,
} from '../services/catalog-decision-selection';

/** The ordinary 24-hour equipment basket, shared by both catalog readers. */
export const useCatalogReaderSelection = () => {
  const items = ref<CatalogDecisionSelectionItem[]>([]);
  const error = ref('');
  const key = computed(() => {
    const auth = managerSession.auth.value;
    return auth && hasManagerCapability(auth, MANAGER_CAPABILITY.crmManage)
      ? catalogDecisionSelectionStorageKey(auth) : null;
  });
  const reload = () => { items.value = key.value ? loadCatalogDecisionSelection(key.value) : []; };
  watch(key, () => { error.value = ''; reload(); }, { immediate: true, flush: 'sync' });
  const onStorage = (event: StorageEvent) => {
    if (event.key === key.value || event.key === null) reload();
  };
  onMounted(() => window.addEventListener('storage', onStorage));
  onBeforeUnmount(() => window.removeEventListener('storage', onStorage));
  const toggle = (item: CatalogDecisionSelectionItem) => {
    if (!key.value) return;
    error.value = '';
    // Storage events synchronize other tabs; preserve local state if storage is blocked.
    const current = items.value;
    const exists = current.some(value => value.id === item.id);
    if (!exists && current.length >= 24) {
      error.value = 'В один подбор можно добавить до 24 моделей.';
      return;
    }
    items.value = exists ? current.filter(value => value.id !== item.id) : [...current, { id: item.id, title: item.title }];
    saveCatalogDecisionSelection(items.value, key.value);
  };
  return { items, error, toggle, has: (id: number) => items.value.some(item => item.id === id) };
};
