<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import {
  ChevronDown,
  KeyRound,
  Link2,
  Loader2,
  LogOut,
  Settings,
} from 'lucide-vue-next';

import type { ManagerAuthStatusResponse } from '../../client';
import { MANAGER_CAPABILITY, hasManagerCapability } from '../../manager-capabilities';
import { managerStorefrontSelection } from '../../services/manager-storefront-selection';
import {
  clearManagerSession,
  logoutManager,
} from '../../services/manager-session';
import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{ auth: ManagerAuthStatusResponse }>();
const emit = defineEmits<{
  navigate: [path: string];
  loggedOut: [];
  error: [message: string];
}>();

const root = ref<HTMLElement | null>(null);
const open = ref(false);
const logoutLoading = ref(false);

const accountName = computed(() => (
  String(props.auth.display_name || props.auth.username || 'Аккаунт').trim()
));
const avatarLetter = computed(() => accountName.value.charAt(0).toUpperCase() || 'А');
const currentStorefront = computed(() => {
  const selected = managerStorefrontSelection.selectedSlug.value;
  return managerStorefrontSelection.storefronts.value.find(
    storefront => storefront.slug === selected,
  )?.display_name || 'Текущий филиал';
});
const canManageAnalytics = computed(() => (
  hasManagerCapability(props.auth, MANAGER_CAPABILITY.analyticsManage)
));
const canManageInfrastructure = computed(() => (
  hasManagerCapability(props.auth, MANAGER_CAPABILITY.infrastructureManage)
));

const navigate = (path: string) => {
  open.value = false;
  emit('navigate', path);
};

const logout = async () => {
  if (logoutLoading.value) return;
  logoutLoading.value = true;
  try {
    await logoutManager();
    clearManagerSession();
    emit('loggedOut');
  } catch (error) {
    emit('error', getApiErrorMessage(error) || 'Не удалось выйти');
  } finally {
    logoutLoading.value = false;
  }
};

const onDocumentClick = (event: MouseEvent) => {
  if (!root.value?.contains(event.target as Node)) open.value = false;
};
const onEscape = (event: KeyboardEvent) => {
  if (event.key === 'Escape') open.value = false;
};

onMounted(() => {
  document.addEventListener('click', onDocumentClick);
  document.addEventListener('keydown', onEscape);
});
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick);
  document.removeEventListener('keydown', onEscape);
});
</script>

<template>
  <div ref="root" data-testid="manager-account-menu" class="relative">
    <button
      type="button"
      class="flex items-center gap-2 rounded-full border border-gray-200 bg-white py-1.5 pl-1.5 pr-3 text-left shadow-sm transition hover:border-teal-200 hover:shadow"
      :aria-expanded="open"
      aria-haspopup="menu"
      @click="open = !open"
    >
      <span class="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-teal-500 to-cyan-600 text-sm font-bold text-white">
        {{ avatarLetter }}
      </span>
      <span class="hidden min-w-0 sm:block">
        <span class="block max-w-44 truncate text-sm font-semibold text-gray-900">{{ accountName }}</span>
        <span class="block max-w-44 truncate text-[11px] text-gray-500">{{ currentStorefront }}</span>
      </span>
      <ChevronDown class="h-4 w-4 text-gray-400 transition" :class="open ? 'rotate-180' : ''" />
    </button>

    <div
      v-show="open"
      role="menu"
      class="absolute right-0 mt-2 w-64 overflow-hidden rounded-2xl border border-gray-200 bg-white p-2 shadow-xl"
    >
      <div class="border-b border-gray-100 px-3 py-2.5">
        <p class="truncate text-sm font-semibold text-gray-900">{{ accountName }}</p>
        <p class="mt-0.5 truncate text-xs text-gray-500">{{ props.auth.username }}</p>
      </div>
      <button class="account-menu-item text-gray-700 hover:bg-gray-50 hover:text-gray-900 dark:text-slate-200 dark:hover:bg-slate-800 dark:hover:text-white" type="button" role="menuitem" @click="navigate('/manager/profile')">
        <KeyRound class="h-4 w-4" />
        Профиль и пароль
      </button>
      <button
        v-if="canManageAnalytics"
        class="account-menu-item text-gray-700 hover:bg-gray-50 hover:text-gray-900 dark:text-slate-200 dark:hover:bg-slate-800 dark:hover:text-white"
        type="button"
        role="menuitem"
        @click="navigate('/manager/integrations')"
      >
        <Link2 class="h-4 w-4" />
        Интеграции
      </button>
      <button
        v-if="canManageInfrastructure"
        class="account-menu-item text-gray-700 hover:bg-gray-50 hover:text-gray-900 dark:text-slate-200 dark:hover:bg-slate-800 dark:hover:text-white"
        type="button"
        role="menuitem"
        @click="navigate('/manager/settings')"
      >
        <Settings class="h-4 w-4" />
        Настройки сайта
      </button>
      <div class="my-1 border-t border-gray-100" />
      <button
        data-testid="manager-logout"
        class="account-menu-item text-red-600 hover:bg-red-50 hover:text-red-700 dark:text-red-400 dark:hover:bg-red-950/40 dark:hover:text-red-300"
        type="button"
        role="menuitem"
        :disabled="logoutLoading"
        @click="logout"
      >
        <Loader2 v-if="logoutLoading" class="h-4 w-4 animate-spin" />
        <LogOut v-else class="h-4 w-4" />
        {{ logoutLoading ? 'Выходим...' : 'Выйти' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.account-menu-item {
  @apply mt-1 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-60;
}

</style>
