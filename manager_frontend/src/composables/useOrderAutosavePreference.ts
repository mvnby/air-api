import { computed, ref, watch } from 'vue';
import { managerSession } from '../services/manager-session';

export const useOrderAutosavePreference = () => {
  const identity = computed(() => {
    const auth = managerSession.auth.value;
    return auth ? `${auth.tenant_id}:${auth.staff_user_id || auth.username}` : '';
  });
  const enabled = ref(true);
  watch(identity, (key) => {
    try {
      enabled.value = !key || window.localStorage.getItem(`manager:order-autosave:${key}`) !== 'off';
    } catch { enabled.value = true; }
  }, { immediate: true, flush: 'sync' });
  const toggle = () => {
    enabled.value = !enabled.value;
    try {
      if (identity.value) window.localStorage.setItem(`manager:order-autosave:${identity.value}`, enabled.value ? 'on' : 'off');
    } catch { /* The preference still applies for this mounted workspace. */ }
  };
  return { enabled, toggle, identity };
};
