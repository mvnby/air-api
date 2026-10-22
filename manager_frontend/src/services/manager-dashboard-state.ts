import { computed, ref, shallowRef, watch } from 'vue';
import { api, type DashboardStatsResponse } from '../api';
import type { DashboardOverviewResponse } from '../client';
import { hasManagerCapability, MANAGER_CAPABILITY } from '../manager-capabilities';
import { managerSession } from './manager-session';
import { managerStorefrontSelection } from './manager-storefront-selection';

// One in-memory context only. A logout or permission/context transition also
// clears retained data while Home is unmounted; no business data in storage.
export const dashboardContextKey = computed(() => {
  const auth = managerSession.auth.value;
  if (!auth || !managerSession.isAuthenticated.value || managerSession.recoveryRequired.value
    || managerSession.bootstrapping.value || managerStorefrontSelection.switching.value) return null;
  const tenantId = managerStorefrontSelection.selectedTenantId.value;
  const selectedSite = managerStorefrontSelection.storefronts.value.find(site => site.slug === managerStorefrontSelection.selectedSlug.value);
  if ((tenantId !== null && tenantId !== auth.tenant_id)
    || (typeof selectedSite?.id === 'number' && selectedSite.id !== auth.storefront_id)) return null;
  return JSON.stringify([
    auth.staff_user_id, auth.username, auth.tenant_id, auth.storefront_id,
    managerStorefrontSelection.selectedTenantId.value, managerStorefrontSelection.selectedSlug.value,
    auth.tenant_membership_id, auth.role, auth.status, [...auth.capabilities || []].sort(),
    auth.access_kind, auth.auth_source, auth.is_system_tenant, auth.is_platform_owner,
    auth.demo_read_only, auth.must_change_password,
  ]);
});

const scopedResource = <T>(load: () => PromiseLike<T>, enabled = () => true) => {
  const data = shallowRef<T | null>(null);
  const loading = ref(false);
  const error = ref(false);
  const updatedAt = ref<string | null>(null);
  let generation = 0;
  let inFlight: Promise<void> | null = null;
  const followUpGuards = new Set<() => boolean>();
  const reset = () => {
    generation++;
    data.value = null; error.value = false; loading.value = false; updatedAt.value = null;
    inFlight = null; followUpGuards.clear();
  };
  watch(dashboardContextKey, reset, { flush: 'sync' });
  const refresh = (freshWithinMs = 0, followUpIfBusy?: () => boolean): Promise<void> => {
    const key = dashboardContextKey.value;
    if (!key || !enabled()) return Promise.resolve();
    if (inFlight) {
      if (followUpIfBusy) followUpGuards.add(followUpIfBusy);
      return inFlight;
    }
    if (updatedAt.value && Date.now() - Date.parse(updatedAt.value) < freshWithinMs) return Promise.resolve();
    const revision = generation;
    loading.value = true;
    // Retain the last result and any previous error until a successful read.
    const task = Promise.resolve().then(() => {
      if (revision !== generation || key !== dashboardContextKey.value) return;
      return load();
    }).then(result => {
      if (result === undefined || revision !== generation || key !== dashboardContextKey.value) return;
      data.value = result; error.value = false; updatedAt.value = new Date().toISOString();
    }).catch(failure => {
      if (revision !== generation || key !== dashboardContextKey.value) return;
      if (failure?.status === 401 || failure?.status === 403) {
        // A denied read cannot keep a formerly authorised business snapshot.
        data.value = null; updatedAt.value = null; followUpGuards.clear();
      }
      error.value = true;
    }).finally(() => {
      if (revision !== generation || key !== dashboardContextKey.value) return;
      loading.value = false; inFlight = null;
      // A mutation may have completed after this read began. Collapse such
      // invalidations into one later read, only while a subscriber still needs it.
      const guards = [...followUpGuards]; followUpGuards.clear();
      if (guards.some(guard => guard())) void refresh();
    });
    inFlight = task;
    return task;
  };
  return { data, loading, error, updatedAt, refresh };
};

export const dashboardOverviewState = scopedResource<DashboardOverviewResponse>(() => api.getDashboardOverview());
export const dashboardOperationsState = scopedResource<DashboardStatsResponse>(() => api.getDashboardStats());
// The personal unread count is never part of a shared tenant snapshot.
export const managerLeadsCounterState = scopedResource<{ count: number }>(() => api.getLeadsCounter(), () => (
  hasManagerCapability(managerSession.auth.value, MANAGER_CAPABILITY.crmManage)
));
