<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import ManagerContextHeader from '../manager/ManagerContextHeader.vue';
import { inboxSourceOptions, type InboxScope, type InboxSource } from '../../services/lead-inbox';

const props = defineProps<{
  pendingCount: number;
  unreadCount: number;
  sourceCounts: Record<string, number>;
  total: number;
  loading: boolean;
  showEmailImport: boolean;
}>();
const emit = defineEmits<{ create: []; 'toggle-email': [] }>();
const scope = defineModel<InboxScope>('scope', { required: true });
const source = defineModel<InboxSource>('source', { required: true });
const search = defineModel<string>('search', { required: true });
const unreadOnly = defineModel<boolean>('unreadOnly', { required: true });
const sort = defineModel<'newest' | 'deadline'>('sort', { required: true });
const searchOpen = ref(Boolean(search.value));
const contextControls = ref<HTMLElement | null>(null);
const directSearch = ref(false);
const searchInput = ref<HTMLInputElement | null>(null);
const searchToggle = ref<HTMLButtonElement | null>(null);
let controlsObserver: ResizeObserver | null = null;
const measureControls = () => {
  const nextDirect = (contextControls.value?.getBoundingClientRect().width ?? 0) >= 520;
  if (nextDirect === directSearch.value) return;
  const focusedSearch = searchInput.value?.parentElement?.contains(document.activeElement)
    || document.activeElement === searchToggle.value;
  if (!nextDirect && focusedSearch) searchOpen.value = true;
  directSearch.value = nextDirect;
  if (focusedSearch) void nextTick(() => searchInput.value?.focus({ preventScroll: true }));
};
const onOutsideClick = (event: MouseEvent) => {
  if (!directSearch.value && searchOpen.value && !contextControls.value?.contains(event.target as Node)) searchOpen.value = false;
};
const onDocumentEscape = (event: KeyboardEvent) => {
  if (event.key !== 'Escape' || event.defaultPrevented || directSearch.value || !searchOpen.value) return;
  event.preventDefault();
  void toggleSearch();
};
onMounted(() => {
  measureControls();
  document.addEventListener('click', onOutsideClick, true);
  document.addEventListener('keydown', onDocumentEscape);
  if (typeof ResizeObserver !== 'undefined') {
    controlsObserver = new ResizeObserver(measureControls);
    if (contextControls.value) controlsObserver.observe(contextControls.value);
  }
});
onBeforeUnmount(() => {
  controlsObserver?.disconnect();
  document.removeEventListener('click', onOutsideClick, true);
  document.removeEventListener('keydown', onDocumentEscape);
});
const scopeOptions: { value: InboxScope; label: string; icon: string }[] = [
  { value: 'active', label: 'Активные', icon: 'inbox' },
  { value: 'archive', label: 'Архив', icon: 'inventory_2' },
];
const allCount = computed(() => Object.values(props.sourceCounts).reduce((sum, count) => sum + count, 0));
const visibleSources = computed(() => inboxSourceOptions.filter(option =>
  !option.value || (props.sourceCounts[option.value] ?? 0) > 0 || source.value === option.value));
watch(search, value => { if (value) searchOpen.value = true; });

const toggleSearch = async () => {
  searchOpen.value = !searchOpen.value;
  if (!searchOpen.value) search.value = '';
  await nextTick();
  if (searchOpen.value) searchInput.value?.focus({ preventScroll: true });
  else searchToggle.value?.focus({ preventScroll: true });
};
const onSearchEscape = () => {
  if (directSearch.value) { searchOpen.value = false; search.value = ''; searchInput.value?.focus({ preventScroll: true }); }
  else void toggleSearch();
};
</script>

<template>
  <ManagerContextHeader compact>
    <header ref="contextControls" class="inbox-header inbox-context">
      <div class="inbox-context-line">
        <h1>Входящие</h1>
        <div class="inbox-context-scopes" aria-label="Очередь обращений">
          <button v-for="option in scopeOptions" :key="option.value" type="button" :aria-label="option.label" :title="option.label" :aria-pressed="scope === option.value" @click="scope = option.value">
            <span class="material-icons-round inbox-scope-icon" aria-hidden="true">{{ option.icon }}</span><span class="inbox-scope-label">{{ option.label }}</span>
          </button>
        </div>
        <button v-if="!directSearch" ref="searchToggle" type="button" class="inbox-context-icon" :class="{ 'has-query': Boolean(search) }" aria-label="Поиск по входящим обращениям" :title="search ? `Поиск: ${search}` : 'Поиск'" :aria-pressed="Boolean(search)" aria-controls="lead-inbox-search" :aria-expanded="searchOpen" @click="toggleSearch">
          <span class="material-icons-round" aria-hidden="true">{{ searchOpen ? 'close' : 'search' }}</span>
        </button>
        <label v-if="searchOpen || directSearch" id="lead-inbox-search" class="inbox-context-search" :class="{ 'is-direct': directSearch }">
          <span class="material-icons-round" aria-hidden="true">search</span><span class="sr-only">Найти обращение или клиента</span>
          <input ref="searchInput" v-model="search" type="search" aria-label="Найти обращение или клиента" placeholder="Найти обращение или клиента" @keydown.esc.prevent="onSearchEscape">
          <button v-if="search" type="button" aria-label="Очистить поиск" @click="search = ''; searchInput?.focus({ preventScroll: true })"><span class="material-icons-round" aria-hidden="true">close</span></button>
        </label>
        <button type="button" class="inbox-context-create" aria-label="Создать обращение" title="Создать обращение" @click="emit('create')">
          <span class="material-icons-round" aria-hidden="true">add</span><span class="inbox-create-label">Создать обращение</span>
        </button>
      </div>
      <p class="inbox-context-summary" :title="`Ожидают решения: ${pendingCount} · Непросмотрено: ${unreadCount}`">Ожидают: {{ pendingCount }} · Непросмотрено: {{ unreadCount }}</p>
    </header>
  </ManagerContextHeader>
  <section class="inbox-toolbar" aria-label="Фильтры обращений">
    <div class="channels" aria-label="Источник входящих">
      <button v-for="option in visibleSources" :key="option.value" type="button" :aria-pressed="source === option.value" @click="source = option.value">
        <span class="channel-label">{{ option.label }}</span><span class="channel-count">{{ option.value ? (sourceCounts[option.value] ?? 0) : allCount }}</span>
      </button>
    </div>
    <div class="inbox-filter-row">
      <div class="inbox-filters">
        <button type="button" :aria-pressed="unreadOnly" @click="unreadOnly = !unreadOnly"><span class="unread-dot" />Непросмотренные</button>
        <select v-model="sort" aria-label="Сортировка входящих"><option value="deadline">Ближайший срок</option><option value="newest">Сначала новые</option></select>
        <button type="button" class="inbox-button inbox-mail-check" aria-label="Проверить почту" title="Проверить почту" :aria-expanded="showEmailImport" @click="emit('toggle-email')">
          <span class="material-icons-round" aria-hidden="true">mail</span><span class="inbox-mail-label">Проверить почту</span>
        </button>
      </div>
      <p class="result-count" aria-live="polite">{{ loading ? 'Обновляем список…' : `Найдено: ${total}` }}</p>
    </div>
  </section>
  <slot name="email-import" />
</template>


<style scoped>
.inbox-context {
  container-type: inline-size;
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  width: 100%;
  margin: 0;
  color: var(--kitlane-text, #1e293b);
}
.inbox-context-line { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; min-width: 0; }
.inbox-context h1 { margin: 0 4px 0 0; font-size: 16px; line-height: 1.25; font-weight: 700; letter-spacing: -.3px; white-space: nowrap; }
.inbox-context-scopes { display: flex; flex-shrink: 0; gap: 2px; padding: 2px; border-radius: 7px; background: var(--kitlane-bg, #f5f7fa); }
.inbox-context-scopes button { display: inline-flex; align-items: center; justify-content: center; min-height: 30px; min-width: 30px; padding: 0 4px; border-radius: 5px; color: var(--kitlane-muted, #67758a); font-size: 11px; white-space: nowrap; }
.inbox-context-scopes button[aria-pressed=true] { background: var(--kitlane-surface, #fff); color: var(--kitlane-accent-text, #255ddb); box-shadow: 0 1px 3px #0f172a14; font-weight: 600; }
.inbox-scope-label, .inbox-create-label { display: none; }
.inbox-scope-icon { font-size: 18px; }
.inbox-context-icon, .inbox-context-create { display: inline-flex; align-items: center; justify-content: center; flex: 0 0 auto; gap: 5px; min-height: 34px; min-width: 32px; padding: 0 4px; border-radius: 6px; color: inherit; }
.inbox-context-icon:hover, .inbox-context-icon[aria-expanded=true], .inbox-context-icon.has-query { color: var(--kitlane-accent-text, #255ddb); background: var(--kitlane-accent-soft, #edf3ff); }
.inbox-context-create { color: var(--kitlane-accent-text, #255ddb); border: 1px solid var(--kitlane-border, #e1e7ef); font-size: 11px; font-weight: 600; }
.inbox-context-create:hover { background: var(--kitlane-accent-soft, #edf3ff); }
.inbox-context-icon .material-icons-round, .inbox-context-create .material-icons-round { font-size: 20px; }
.inbox-context-summary { margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--kitlane-muted, #67758a); font-size: 10px; line-height: 14px; }
.inbox-context-search { position: absolute; top: calc(100% + 8px); left: 0; right: 0; z-index: 2; display: flex; align-items: center; gap: 6px; min-width: 0; min-height: 42px; padding: 0 8px; border: 1px solid var(--kitlane-border, #e1e7ef); border-radius: 7px; background: var(--kitlane-surface, #fff); box-shadow: 0 4px 12px #0f172a14; }
.inbox-context-search.is-direct { position: static; flex: 1 1 160px; min-height: 34px; box-shadow: none; }
.inbox-context-search input { min-width: 0; width: 100%; border: 0; padding: 0; color: inherit; background: transparent; font-size: 16px; }
.inbox-context-search.is-direct input { font-size: 12px; }
.inbox-context-search > .material-icons-round { color: var(--kitlane-muted, #67758a); font-size: 18px; }
.inbox-context-search button { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; width: 28px; min-height: 30px; border-radius: 4px; }
.inbox-context-search button .material-icons-round { font-size: 18px; }
.inbox-context button:focus-visible, .inbox-context input:focus-visible { outline: 2px solid var(--kitlane-accent-text, #255ddb); outline-offset: 2px; }
.inbox-mail-check { display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; }
.inbox-mail-check .material-icons-round { font-size: 17px; }
@media (max-width: 760px) {
  .inbox-filter-row .inbox-filters { width: auto; min-width: 0; flex: 1 1 260px; gap: 6px; justify-content: flex-start; }
  .inbox-filters select { min-width: 0; width: auto; max-width: 120px; flex: 1 1 100px; }
  .inbox-filters .inbox-mail-check { flex: 0 0 34px; width: 34px; min-width: 34px; min-height: 36px; padding: 0; justify-content: center; }
  .inbox-mail-label { display: none; }
}
@container (min-width: 340px) {
  .inbox-scope-icon { display: none; }
  .inbox-scope-label { display: inline; }
  .inbox-context-scopes button { padding-inline: 8px; }
}
@container (min-width: 720px) {
  .inbox-create-label { display: inline; }
  .inbox-context-create { padding-inline: 9px; }
}
</style>
