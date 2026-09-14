<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import {
  ChevronDown,
  FileText,
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
const trigger = ref<HTMLButtonElement | null>(null);
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
const canManageDocuments = computed(() => (
  hasManagerCapability(props.auth, MANAGER_CAPABILITY.documentsManage)
));
const canManageSettings = computed(() => (
  hasManagerCapability(props.auth, MANAGER_CAPABILITY.settingsManage)
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
  if (event.key === 'Escape' && open.value) {
    open.value = false;
    trigger.value?.focus();
  }
};

const focusMenuItem = async (event: KeyboardEvent) => {
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
  event.preventDefault();
  open.value = true;
  await nextTick();
  const items = Array.from(root.value?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not(:disabled)') ?? []);
  const current = items.indexOf(document.activeElement as HTMLButtonElement);
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1
    : event.key === 'ArrowUp' ? (current <= 0 ? items.length - 1 : current - 1) : (current + 1) % items.length;
  items[next]?.focus();
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
  <div ref="root" data-testid="manager-account-menu" class="relative" @keydown="focusMenuItem">
    <button
      ref="trigger"
      type="button"
      class="kitlane-account-trigger"
      :aria-label="`Аккаунт: ${accountName}`"
      :aria-expanded="open"
      aria-haspopup="menu"
      @click="open = !open"
    >
      <span class="kitlane-account-avatar">
        {{ avatarLetter }}
      </span>
      <span class="hidden min-w-0 sm:block">
        <span class="block max-w-44 truncate text-sm font-semibold text-gray-900">{{ accountName }}</span>
        <span class="block max-w-44 truncate text-[11px] text-gray-500">{{ currentStorefront }}</span>
      </span>
      <ChevronDown class="h-4 w-4 text-gray-500 transition" :class="open ? 'rotate-180' : ''" />
    </button>

    <div
      v-show="open"
      role="menu"
      class="kitlane-account-popover absolute right-0 mt-2 w-64 overflow-hidden rounded-xl border border-gray-200 bg-white p-2 shadow-xl"
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
        v-if="canManageDocuments"
        data-testid="manager-document-settings"
        class="account-menu-item text-gray-700 hover:bg-gray-50 hover:text-gray-900 dark:text-slate-200 dark:hover:bg-slate-800 dark:hover:text-white"
        type="button"
        role="menuitem"
        @click="navigate('/manager/settings/documents')"
      >
        <FileText class="h-4 w-4" />
        Документы CRM
      </button>
      <button
        v-if="canManageSettings"
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

.kitlane-account-trigger { display: flex; align-items: center; gap: 8px; border-radius: 9px; padding: 4px; text-align: left; color: var(--kitlane-text); }
.kitlane-account-trigger:hover { background: var(--kitlane-bg); }
.kitlane-account-avatar { display: grid; place-items: center; width: 36px; height: 36px; border-radius: 50%; color: var(--kitlane-accent-text); background: var(--kitlane-accent-soft); font-size: 14px; font-weight: 700; }
@media (max-width: 639px) { .kitlane-account-popover { position: fixed; top: 64px; right: 12px; width: min(256px, calc(100vw - 24px)); } }
</style>
