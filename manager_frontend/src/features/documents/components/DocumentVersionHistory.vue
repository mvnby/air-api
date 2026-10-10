<script setup lang="ts">
import type { ManagedDocumentItem } from '../../../client';
import { documentArtifactName, managedDocumentStatus, managedDocumentStatusClass, officialDocumentTitle } from '../model/native-document-options';

defineProps<{
  documents: ManagedDocumentItem[];
  title?: string;
  testId?: string;
}>();
const emit = defineEmits<{ download: [artifactId: string, filename: string] }>();
const formatDate = (value: string) => new Date(value.length === 10 ? `${value}T00:00:00` : value).toLocaleDateString('ru-RU');
</script>

<template>
  <details v-if="documents.length" class="document-history" :data-testid="testId || 'document-version-history'">
    <summary class="cursor-pointer rounded-lg px-2 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-500 dark:text-slate-300 dark:hover:bg-slate-800">
      {{ title || 'Предыдущие версии' }} <span class="font-normal text-slate-500">({{ documents.length }})</span>
    </summary>
    <ul class="mt-2 space-y-3 border-l-2 border-slate-200 pl-3 dark:border-slate-700">
      <li v-for="document in documents" :key="document.id" class="min-w-0 rounded-lg bg-slate-50 p-3 dark:bg-slate-800/50" :data-testid="`historical-document-${document.id}`">
        <div class="flex flex-wrap items-center gap-2">
          <p class="break-words text-sm font-semibold text-slate-700 dark:text-slate-200">{{ officialDocumentTitle(document) }}</p>
          <span class="rounded-full px-2 py-0.5 text-[11px] font-semibold" :class="managedDocumentStatusClass(document.status)">{{ managedDocumentStatus(document.status) }}</span>
        </div>
        <p class="mt-1 text-xs text-slate-500">от {{ formatDate(document.official_date || document.date) }}</p>
        <p v-if="document.void_reason" class="mt-1 break-words text-xs text-slate-500">Причина аннулирования: {{ document.void_reason }}</p>
        <div v-if="document.artifacts?.length || document.maintenance_source_order_id" class="mt-2 flex flex-wrap gap-2">
          <button v-for="artifact in document.artifacts" :key="artifact.id" type="button" class="history-download" @click="emit('download', artifact.id, artifact.filename)">
            <span class="material-icons-round text-[15px]" aria-hidden="true">download</span>{{ documentArtifactName(artifact.kind) }}
          </button>
          <a v-if="document.maintenance_source_order_id" :href="`/manager/orders/kanban?orderId=${document.maintenance_source_order_id}`" target="_blank" rel="noopener" class="history-download">Исходное ТО #{{ document.maintenance_source_order_id }}</a>
        </div>
      </li>
    </ul>
  </details>
</template>

<style scoped>
.history-download { @apply inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs font-medium text-slate-600 hover:border-brand-300 hover:text-brand-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300; }
</style>
