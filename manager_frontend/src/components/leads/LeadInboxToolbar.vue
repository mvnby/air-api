<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
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
const searchInput = ref<HTMLInputElement | null>(null);
const searchToggle = ref<HTMLButtonElement | null>(null);
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
  if (searchOpen.value) searchInput.value?.focus();
  else searchToggle.value?.focus();
};
</script>

<template>
  <header class="inbox-header">
    <div class="inbox-summary-row">
      <span class="eyebrow">ПЕРВИЧНЫЙ РАЗБОР</span>
      <p class="inbox-summary">
        <span><span class="summary-label-full">Ожидают решения</span><span class="summary-label-short">Ожидают</span>: {{ pendingCount }}</span>
        <span aria-hidden="true"> · </span><span>Непросмотрено: {{ unreadCount }}</span>
      </p>
    </div>
    <div class="inbox-title-row">
      <h1>Входящие</h1>
      <div class="inbox-primary-controls">
        <div class="segments" aria-label="Очередь обращений">
          <button v-for="option in scopeOptions" :key="option.value" type="button" :aria-label="option.label" :title="option.label" :aria-pressed="scope === option.value" @click="scope = option.value">
            <span class="material-icons-round scope-icon" aria-hidden="true">{{ option.icon }}</span><span class="scope-label">{{ option.label }}</span>
          </button>
        </div>
        <button ref="searchToggle" type="button" class="inbox-icon-button search-toggle" aria-label="Поиск по входящим обращениям" title="Поиск" aria-controls="lead-inbox-search" :aria-expanded="searchOpen" @click="toggleSearch">
          <span class="material-icons-round" aria-hidden="true">{{ searchOpen ? 'close' : 'search' }}</span>
        </button>
      </div>
      <div class="header-actions">
        <button type="button" class="inbox-button" aria-label="Проверить почту" title="Проверить почту" :aria-expanded="showEmailImport" @click="emit('toggle-email')">
          <span class="material-icons-round" aria-hidden="true">mail</span><span class="action-label">Проверить почту</span>
        </button>
        <button type="button" class="inbox-button" aria-label="Создать обращение" title="Создать обращение" @click="emit('create')">
          <span class="material-icons-round" aria-hidden="true">add</span><span class="action-label">Создать обращение</span>
        </button>
      </div>
    </div>
    <label v-if="searchOpen" id="lead-inbox-search" class="inbox-search">
      <span class="material-icons-round" aria-hidden="true">search</span><span class="sr-only">Найти обращение или клиента</span>
      <input ref="searchInput" v-model="search" type="search" placeholder="Найти обращение или клиента" @keydown.esc.prevent="toggleSearch">
      <button v-if="search" type="button" aria-label="Очистить поиск" @click="search = ''; searchInput?.focus()"><span class="material-icons-round" aria-hidden="true">close</span></button>
    </label>
  </header>
  <slot name="email-import" />
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
      </div>
      <p class="result-count" aria-live="polite">{{ loading ? 'Обновляем список…' : `Найдено: ${total}` }}</p>
    </div>
  </section>
</template>
