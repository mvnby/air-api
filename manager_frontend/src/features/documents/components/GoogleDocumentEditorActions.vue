<script setup lang="ts">
import { computed } from 'vue';
import type { GoogleDocumentEditSession } from '../integrations/google-document-editor-api';

const props = withDefaults(defineProps<{
  session?: GoogleDocumentEditSession | null;
  busy?: boolean;
  editable?: boolean;
}>(), {
  session: null,
  busy: false,
  editable: true,
});
const emit = defineEmits<{ open: []; sync: [] }>();

const statusLabel = computed(() => {
  if (!props.session) return '';
  if (props.session.status === 'changed') return 'Есть изменения в Google';
  if (props.session.status === 'syncing') return 'Синхронизируем…';
  if (props.session.status === 'error') return props.session.detail || 'Ошибка синхронизации';
  return 'Синхронизировано';
});
</script>

<template>
  <div class="flex flex-wrap items-center gap-2" data-testid="google-document-editor-actions">
    <span
      v-if="statusLabel"
      class="text-[11px] font-semibold"
      :class="session?.status === 'changed' ? 'text-amber-700 dark:text-amber-300' : session?.status === 'error' ? 'text-rose-700 dark:text-rose-300' : 'text-slate-500'"
    >{{ statusLabel }}</span>
    <button class="google-editor-action" type="button" :disabled="busy" @click="emit('open')">
      <span class="material-icons-round text-[17px]">open_in_new</span>
      {{ session?.edit_url ? 'Открыть' : editable ? 'Редактировать в Google Docs' : 'Открыть в Google Docs' }}
    </button>
    <button
      v-if="session?.edit_url && editable"
      class="google-editor-action"
      type="button"
      :disabled="busy"
      @click="emit('sync')"
    >
      <span class="material-icons-round text-[17px]">sync</span>Забрать изменения
    </button>
  </div>
</template>

<style scoped>
.google-editor-action { @apply inline-flex h-9 items-center justify-center gap-1 rounded-lg border border-slate-200 px-3 text-xs font-semibold text-slate-600 hover:border-teal-400 hover:text-teal-700 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:text-slate-300; }
</style>
