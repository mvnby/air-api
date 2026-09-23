import { computed, ref, watch } from 'vue';
import { storefrontSettingsApi } from '../features/settings/storefront-settings-api';
import { managerSession } from '../services/manager-session';
import { managerStorefrontSelection } from '../services/manager-storefront-selection';

export function useKitlaneIdentity() {
  const brand = ref<{ display_name: string; logo_url: string | null; compact_logo_url: string | null } | null>(null);
  let generation = 0;
  const storefront = computed(() => {
    if (!managerSession.isAuthenticated.value || managerSession.recoveryRequired.value
      || managerStorefrontSelection.loading.value || managerStorefrontSelection.switching.value
      || managerStorefrontSelection.error.value) return null;
    const { storefronts, selectedSlug } = managerStorefrontSelection;
    return storefronts.value.find(item => selectedSlug.value
      ? item.slug === selectedSlug.value : item.is_current) ?? null;
  });
  const contextKey = computed(() => `${managerSession.auth.value?.tenant_id ?? ''}:${storefront.value?.slug ?? ''}`);
  watch([storefront, contextKey, brandRevision], async ([current]) => {
    const requestGeneration = ++generation;
    brand.value = null;
    if (!current) return;
    try {
      const result = await storefrontSettingsApi.brand();
      if (generation === requestGeneration) brand.value = result;
    } catch {
      // Keep the authorized storefront name and initials if the brand read fails.
    }
  }, { immediate: true, flush: 'sync' });
  const name = computed(() => brand.value?.display_name.trim() || storefront.value?.display_name.trim() || null);
  const logoUrl = computed(() => storefront.value ? brand.value?.logo_url ?? null : null);
  const compactLogoUrl = computed(() => storefront.value ? brand.value?.compact_logo_url ?? null : null);
  watch(name, value => { document.title = value ? `${value} · KitLane` : 'KitLane'; }, { immediate: true, flush: 'sync' });
  return { name, logoUrl, compactLogoUrl, contextKey };
}

const brandRevision = ref(0);
export const refreshKitlaneBrand = () => { brandRevision.value += 1; };
