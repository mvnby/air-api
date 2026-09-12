import { computed, watch } from 'vue';
import { managerSession } from '../services/manager-session';
import { managerStorefrontSelection } from '../services/manager-storefront-selection';

// Presentation only: use the list already authorized by the session bootstrap.
// Company logos are not exposed by this contract yet.
export function useKitlaneIdentity() {
  const storefront = computed(() => {
    if (!managerSession.isAuthenticated.value || managerSession.recoveryRequired.value
      || managerStorefrontSelection.loading.value || managerStorefrontSelection.switching.value) return null;
    const { storefronts, selectedSlug } = managerStorefrontSelection;
    return storefronts.value.find(item => selectedSlug.value
      ? item.slug === selectedSlug.value : item.is_current) ?? null;
  });
  const name = computed(() => storefront.value?.display_name.trim() || null);
  const contextKey = computed(() => `${managerSession.auth.value?.tenant_id ?? ''}:${storefront.value?.slug ?? ''}`);
  watch(name, value => { document.title = value ? `${value} · KitLane` : 'KitLane'; }, { immediate: true, flush: 'sync' });
  return { name, contextKey };
}
