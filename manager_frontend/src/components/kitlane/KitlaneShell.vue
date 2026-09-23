<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { ChevronLeft, ChevronRight, Menu, Moon, Sun, X } from 'lucide-vue-next';
import KitlanePartnerIdentity from './KitlanePartnerIdentity.vue';
import KitlanePlatformBrand from './KitlanePlatformBrand.vue';
import ManagerStorefrontSwitcherHost from '../manager/ManagerStorefrontSwitcherHost.vue';

const props = defineProps<{ name: string | null; logoUrl?: string | null; compactLogoUrl?: string | null; contextKey: string; collapsed: boolean; mobileOpen: boolean; theme: 'light' | 'dark' }>();
const emit = defineEmits<{
  'update:collapsed': [value: boolean];
  'update:mobileOpen': [value: boolean];
  toggleTheme: [];
  home: [];
}>();
const sidebar = ref<HTMLElement | null>(null);
const menuButton = ref<HTMLButtonElement | null>(null);
const desktop = ref(true);
const drawerOpen = computed(() => props.mobileOpen && !desktop.value);
let breakpoint: MediaQueryList | null = null;
const updateDesktop = () => { desktop.value = breakpoint?.matches ?? true; };
const closeDrawer = () => emit('update:mobileOpen', false);
const onKeydown = (event: KeyboardEvent) => {
  if (!drawerOpen.value) return;
  if (event.key === 'Escape') { event.preventDefault(); closeDrawer(); }
  if (event.key !== 'Tab') return;
  const controls = Array.from(sidebar.value?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], [tabindex="0"]') ?? [])
    .filter(element => element.getClientRects().length > 0);
  const first = controls[0]; const last = controls[controls.length - 1];
  if (event.shiftKey && (document.activeElement === first || document.activeElement === sidebar.value)) { event.preventDefault(); last?.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
};
watch(drawerOpen, async open => {
  await nextTick();
  if (open) sidebar.value?.focus(); else if (!desktop.value) menuButton.value?.focus();
});
onMounted(() => {
  if (typeof window.matchMedia !== 'function') return;
  breakpoint = window.matchMedia('(min-width: 768px)');
  updateDesktop(); breakpoint.addEventListener('change', updateDesktop);
  document.addEventListener('keydown', onKeydown);
});
onBeforeUnmount(() => {
  breakpoint?.removeEventListener('change', updateDesktop);
  document.removeEventListener('keydown', onKeydown);
});
</script>

<template>
  <div class="kitlane-shell" :class="{ 'is-collapsed': collapsed, 'is-drawer-open': drawerOpen }">
    <div v-if="drawerOpen" class="kitlane-backdrop" aria-hidden="true" @click="closeDrawer" />
    <aside ref="sidebar" id="manager-mobile-navigation" class="kitlane-sidebar" :inert="!desktop && !drawerOpen" :role="drawerOpen ? 'dialog' : undefined" :aria-modal="drawerOpen || undefined" aria-label="Основная навигация" tabindex="-1">
      <div class="kitlane-sidebar-brand">
        <button class="kitlane-home" type="button" :aria-label="`${name || 'Рабочее пространство'} — главная`" @click="emit('home')">
          <KitlanePartnerIdentity :name="name" :logo-url="logoUrl" :compact-logo-url="compactLogoUrl" :context-key="contextKey" :desktop-compact="collapsed" />
        </button>
        <button class="kitlane-collapse" type="button" :aria-label="collapsed ? 'Развернуть меню' : 'Свернуть меню'" :aria-expanded="!collapsed" @click="emit('update:collapsed', !collapsed)">
          <ChevronRight v-if="collapsed" :size="16" /><ChevronLeft v-else :size="16" />
        </button>
        <button class="kitlane-icon-button kitlane-drawer-close" type="button" aria-label="Закрыть меню" @click="closeDrawer"><X :size="20" /></button>
      </div>
      <div class="kitlane-sidebar-scroll">
        <ManagerStorefrontSwitcherHost class="kitlane-storefront" :collapsed="collapsed" />
        <slot name="navigation" />
        <div class="kitlane-sidebar-footer"><slot name="footer" /></div>
      </div>
    </aside>
    <main class="kitlane-main" :inert="drawerOpen">
      <header class="kitlane-topbar">
        <div class="kitlane-mobile-company">
          <button ref="menuButton" class="kitlane-icon-button" type="button" aria-label="Открыть меню" aria-controls="manager-mobile-navigation" :aria-expanded="mobileOpen" @click="emit('update:mobileOpen', true)"><Menu :size="20" /></button>
          <button class="kitlane-home" type="button" :aria-label="`${name || 'Рабочее пространство'} — главная`" @click="emit('home')"><KitlanePartnerIdentity :name="name" :logo-url="logoUrl" :compact-logo-url="compactLogoUrl" :context-key="contextKey" compact /></button>
        </div>
        <div class="kitlane-topbar-actions">
          <button class="kitlane-icon-button" type="button" :aria-label="theme === 'light' ? 'Тёмная тема' : 'Светлая тема'" :title="theme === 'light' ? 'Тёмная тема' : 'Светлая тема'" @click="emit('toggleTheme')"><Moon v-if="theme === 'light'" :size="19" /><Sun v-else :size="19" /></button>
          <slot name="account" />
          <div class="kitlane-platform-divider"><KitlanePlatformBrand /></div>
        </div>
      </header>
      <slot />
    </main>
  </div>
</template>

<style scoped>
.kitlane-shell { display: flex; width: 100%; min-height: 100dvh; background: var(--kitlane-bg); color: var(--kitlane-text); }
.kitlane-sidebar { position: sticky; top: 0; display: flex; flex-direction: column; width: var(--kitlane-sidebar-width); height: 100dvh; flex-shrink: 0; background: var(--kitlane-sidebar); color: var(--kitlane-sidebar-text); z-index: 40; }
.kitlane-sidebar-brand { display: flex; align-items: center; position: relative; gap: 10px; height: var(--kitlane-header-height); min-height: var(--kitlane-header-height); padding: 0 20px; border-bottom: 1px solid var(--kitlane-sidebar-border); }
.kitlane-home { display: flex; min-width: 0; text-align: left; border-radius: 6px; }
.kitlane-collapse { position: absolute; right: -12px; top: 24px; display: grid; place-items: center; height: 24px; width: 24px; background: var(--kitlane-sidebar-hover); border: 1px solid #8092ac; color: #fff; border-radius: 8px; }
.kitlane-sidebar-scroll { display: flex; flex-direction: column; min-height: 0; flex: 1; overflow-y: auto; scrollbar-width: thin; scrollbar-color: #52657f transparent; }
.kitlane-storefront { margin: 16px 12px 8px; }
.kitlane-sidebar-footer { margin-top: auto; }
.kitlane-main { flex: 1; min-width: 0; }
.kitlane-topbar { position: sticky; top: 0; display: flex; align-items: center; justify-content: flex-end; height: var(--kitlane-header-height); padding: 0 28px; border-bottom: 1px solid var(--kitlane-border); background: var(--kitlane-surface); z-index: 30; }
.kitlane-topbar-actions { display: flex; align-items: center; gap: 16px; min-width: 0; }
.kitlane-platform-divider { display: flex; padding-left: 20px; border-left: 1px solid var(--kitlane-border); }
.kitlane-icon-button { display: inline-flex; align-items: center; justify-content: center; width: 36px; height: 36px; flex-shrink: 0; color: inherit; border-radius: var(--kitlane-control-radius); }
.kitlane-icon-button:hover { background: var(--kitlane-accent-soft); color: var(--kitlane-accent-text); }
.kitlane-mobile-company, .kitlane-drawer-close { display: none; }
.kitlane-backdrop { position: fixed; inset: 0; background: rgb(5 14 28 / .55); z-index: 45; }
@media (min-width: 768px) {
  .is-collapsed .kitlane-sidebar { width: var(--kitlane-sidebar-compact); }
}
@media (max-width: 767px) {
  .kitlane-sidebar { position: fixed; left: 0; transform: translateX(-100%); width: min(var(--kitlane-sidebar-width), calc(100vw - 32px)); z-index: 50; visibility: hidden; }
  .is-drawer-open .kitlane-sidebar { transform: translateX(0); visibility: visible; }
  .kitlane-sidebar-brand { padding: 0 12px; }
  .kitlane-collapse { display: none; }
  .kitlane-drawer-close { display: inline-flex; margin-left: auto; }
  .kitlane-mobile-company { display: flex; align-items: center; gap: 8px; }
  .kitlane-topbar { justify-content: space-between; padding: 0 12px; gap: 8px; }
  .kitlane-topbar-actions { gap: 6px; }
  .kitlane-platform-divider { padding-left: 8px; }
}
</style>
