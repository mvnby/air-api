<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue';
import { LayoutGrid, ListChecks } from 'lucide-vue-next';
import type { ManagerAuthStatusResponse } from '../../client';
import { activeNavPath, selectionItems, workspaceNavigation, type NavItem } from '../../manager-navigation';
import { managerStorefrontStorageKey } from '../../services/manager-storefront-selection';
import { managerTaskRemindersState } from '../../services/manager-dashboard-state';
import { personalTasksChangedEvent } from '../../services/personal-tasks-api';
import KitlaneSectionDirectory from './KitlaneSectionDirectory.vue';

const props = defineProps<{ auth: ManagerAuthStatusResponse; path: string; collapsed: boolean; mobileOpen: boolean; leadsCount: number }>();
const emit = defineEmits<{ navigate: [path: string]; closeDrawer: [] }>();
const nav = computed(() => workspaceNavigation(props.auth));
const hasDirectory = computed(() => nav.value.groups.some(group => group.id !== 'daily'));
const panel = ref<'personal' | 'all' | null>(null);
const current = computed(() => activeNavPath(props.path, nav.value.groups));
const primaryActive = (item: NavItem) => current.value === item.path || (item.path === '/manager/catalog-decision' && selectionItems.some(child => child.path === current.value));
const storageKey = computed(() => managerStorefrontStorageKey(props.auth) + ':nav-pins:v1');
const pins = ref<string[]>([]);
const readPins = () => {
  try { const data: unknown = JSON.parse(localStorage.getItem(storageKey.value) || '[]');
    return Array.isArray(data) ? [...new Set(data.filter((path): path is string => typeof path === 'string'))] : [];
  } catch { return []; }
};
const available = computed(() => nav.value.groups.filter(group => group.id !== 'daily').flatMap(group => group.items));
const pinned = computed(() => pins.value.flatMap(path => available.value.find(item => item.path === path) || []));
const hasPersonal = computed(() => nav.value.personal.some(item => item.path === '/manager/tasks'));
const reminders = computed(() => hasPersonal.value ? managerTaskRemindersState.data.value?.due_reminder_count || 0 : 0);
const refreshReminders = () => { if (hasPersonal.value) void managerTaskRemindersState.refresh(0, () => hasPersonal.value); };
const togglePin = (path: string) => {
  if (!available.value.some(item => item.path === path)) return;
  pins.value = pins.value.includes(path) ? pins.value.filter(value => value !== path) : [...pins.value, path];
  try { localStorage.setItem(storageKey.value, JSON.stringify(pins.value)); } catch { /* Pins still work for this session. */ }
};
const syncPins = (event: StorageEvent) => { if (event.key === null || event.key === storageKey.value) pins.value = readPins(); };
watch(storageKey, () => { pins.value = readPins(); panel.value = null; }, { immediate: true });
watch(() => props.path, () => { panel.value = null; });
onMounted(() => {
  window.addEventListener('storage', syncPins);
  window.addEventListener(personalTasksChangedEvent, refreshReminders);
  if (hasPersonal.value) void managerTaskRemindersState.refresh(30_000);
});
onBeforeUnmount(() => { window.removeEventListener('storage', syncPins); window.removeEventListener(personalTasksChangedEvent, refreshReminders); });
const open = async (kind: 'personal' | 'all') => {
  if (props.mobileOpen) { emit('closeDrawer'); await nextTick(); }
  if (hasPersonal.value) void managerTaskRemindersState.refresh(30_000);
  panel.value = kind;
};
const go = (path: string) => { panel.value = null; emit('navigate', path); };
</script>

<template>
  <nav class="workspace-nav" :class="{ compact: collapsed }" aria-label="Разделы кабинета">
    <a v-for="item in nav.primary" :key="item.path" :href="item.path" :aria-current="primaryActive(item) ? 'page' : undefined" :title="collapsed ? item.label : undefined" :aria-label="item.label" @click.exact.prevent="go(item.path)">
      <component :is="item.icon" :size="19" /><span class="nav-label">{{ item.label }}</span>
      <span v-if="item.path === '/manager/leads' && leadsCount" class="nav-count" data-testid="manager-leads-count">{{ leadsCount }}</span>
    </a>
    <div v-if="hasDirectory" class="nav-tools">
      <button v-if="nav.personal.length" type="button" aria-label="Моя работа" :title="collapsed ? 'Моя работа' : undefined" aria-haspopup="dialog" @click="open('personal')">
        <ListChecks :size="19" /><span class="nav-label">Моя работа</span><span v-if="reminders" class="nav-count due" :aria-label="'Напоминаний: ' + reminders">{{ reminders }}</span>
      </button>
      <button type="button" aria-label="Все разделы" :title="collapsed ? 'Все разделы' : undefined" aria-haspopup="dialog" @click="open('all')">
        <LayoutGrid :size="19" /><span class="nav-label">Все разделы</span>
      </button>
    </div>
    <div v-if="pinned.length" class="nav-tools">
      <span class="pins-title nav-label">Закреплённые</span>
      <a v-for="item in pinned" :key="item.path" :href="item.path" :aria-current="current === item.path ? 'page' : undefined" :aria-label="item.label" :title="collapsed ? item.label : undefined" @click.exact.prevent="go(item.path)"><component :is="item.icon" :size="18" /><span class="nav-label">{{ item.label }}</span></a>
    </div>
  </nav>
  <Teleport to="body">
    <nav v-if="nav.primary.length" v-show="!mobileOpen && !panel" class="kitlane-mobile-dock" aria-label="Быстрая навигация">
      <a v-for="item in nav.primary" :key="item.path" :href="item.path" :aria-current="primaryActive(item) ? 'page' : undefined" :aria-label="item.label" @click.exact.prevent="go(item.path)">
        <component :is="item.icon" :size="19" /><span>{{ item.shortLabel || item.label }}</span>
        <i v-if="item.path === '/manager/leads' && leadsCount" :aria-label="'Непросмотрено: ' + leadsCount"></i>
      </a>
      <button v-if="hasDirectory" type="button" aria-haspopup="dialog" @click="open('all')"><LayoutGrid :size="19" /><span>Ещё</span></button>
    </nav>
  </Teleport>
  <KitlaneSectionDirectory v-if="panel" :personal="panel === 'personal'" :groups="nav.groups" :pins="pins" :active="current" :reminders="reminders" @close="panel = null" @navigate="go" @pin="togglePin" />
</template>

<style scoped>
.workspace-nav { padding:.45rem .75rem .75rem; }
.workspace-nav a,.workspace-nav button { display:flex; align-items:center; gap:.75rem; position:relative; width:100%; min-height:44px; padding:.5rem .75rem; border-radius:.55rem; color:var(--kitlane-sidebar-text); text-align:left; font-size:.9rem; font-weight:550; }
.workspace-nav a:hover,.workspace-nav button:hover { background:var(--kitlane-sidebar-hover); }
.workspace-nav a[aria-current=page] { background:var(--kitlane-sidebar-selected); color:white; box-shadow:inset 3px 0 #80b1ff; }
.workspace-nav svg { flex-shrink:0; }
.nav-tools { display:grid; gap:2px; border-top:1px solid var(--kitlane-sidebar-border); margin-top:.45rem; padding-top:.45rem; }
.pins-title { padding:.35rem .75rem; color:var(--kitlane-sidebar-muted); font-size:.75rem; }
.nav-count { margin-left:auto; line-height:1.4; padding:0 .4rem; border-radius:1rem; background:#b83a48; color:white; font-size:.75rem; }
.nav-count.due { background:#774a18; }
.kitlane-mobile-dock { display:none; }
@media(min-width:768px){ .compact .nav-label{display:none;} .compact a,.compact button{justify-content:center;padding-inline:0;} .compact .nav-count{position:absolute;top:1px;right:0;} }
@media(max-width:767px){
  .kitlane-mobile-dock { position:fixed; inset:auto 0 0; z-index:35; display:flex; align-items:stretch; border-top:1px solid var(--kitlane-border); background:var(--kitlane-surface); color:var(--kitlane-muted); padding-bottom:env(safe-area-inset-bottom); }
  .kitlane-mobile-dock a,.kitlane-mobile-dock button { position:relative; min-width:0; min-height:52px; flex:1; display:flex; align-items:center; justify-content:center; flex-direction:column; gap:2px; font-size:.68rem; line-height:1.15; }
  .kitlane-mobile-dock [aria-current=page] { color:var(--kitlane-accent-text); background:var(--kitlane-accent-soft); font-weight:700; }
  .kitlane-mobile-dock i { width:7px; height:7px; position:absolute; left:calc(50% + 8px); top:5px; border-radius:50%; background:#b83a48; }
}
@media(prefers-reduced-motion:no-preference){.workspace-nav a,.workspace-nav button{transition:background-color 140ms ease;}}
</style>
