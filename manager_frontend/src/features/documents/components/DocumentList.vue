<script setup lang="ts">
import type { ManagerOrderDocumentItem, OrderProposalResponse } from '../../../client';
import { DOCUMENT_FILE_ACCEPT } from '../model/document-constants';
import { documentScopeLabel, documentTypeLabel } from '../model/document-formatters';

const props = defineProps<{
  documents: ManagerOrderDocumentItem[];
  proposals?: OrderProposalResponse[];
  canCreate: boolean;
  canReplace: boolean;
  canDelete: boolean;
  accessSummary: string;
  processingDocumentId: number | null;
}>();

const emit = defineEmits<{
  create: [];
  download: [document: ManagerOrderDocumentItem];
  attach: [document: ManagerOrderDocumentItem, event: Event];
  delete: [documentId: number];
}>();

const documentProposalName = (doc: ManagerOrderDocumentItem) => {
  if (!doc.proposal_id) return '';
  const proposal = (props.proposals || []).find((item) => item.id === doc.proposal_id);
  return proposal?.name || `вариант #${doc.proposal_id}`;
};
</script>

<template>
  <div>
    <p class="mb-2 text-[11px] font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Документы</p>
    <div v-if="documents.length" class="space-y-2">
      <div
        v-for="doc in documents"
        :key="doc.id"
        class="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-3 text-slate-700 shadow-sm dark:border-slate-700/50 dark:bg-[#1e293b] dark:text-slate-300 dark:shadow-none"
      >
        <div class="flex min-w-0 items-center gap-3">
          <div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-teal-600 dark:bg-slate-800 dark:text-teal-400">
            <span class="material-icons-round text-[19px]">description</span>
          </div>
          <div class="min-w-0">
            <p class="truncate text-sm font-medium text-slate-900 dark:text-white">{{ doc.number || doc.doc_type }}</p>
            <p class="truncate text-xs text-slate-500 dark:text-slate-400">
              {{ new Date(doc.date).toLocaleDateString('ru-RU') }} · <span class="uppercase">{{ doc.doc_type }}</span>
              <span v-if="documentProposalName(doc)"> · {{ documentProposalName(doc) }}</span>
            </p>
            <p v-if="doc.base_document_number" class="truncate text-[11px] text-slate-400 dark:text-slate-500">
              Основание: {{ doc.base_document_type_label || documentTypeLabel(doc.base_document_type) }} · {{ doc.base_document_number }}
            </p>
            <p v-if="documentScopeLabel(doc)" class="truncate text-[11px] text-teal-600 dark:text-teal-300">
              Объект: {{ documentScopeLabel(doc) }}
            </p>
          </div>
        </div>
        <div class="flex shrink-0 items-center gap-1 sm:gap-2">
          <a
            v-if="doc.edit_url"
            :href="doc.edit_url"
            target="_blank"
            class="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-white"
            title="Открыть"
          >
            <span class="material-icons-round text-[18px]">open_in_new</span>
          </a>
          <button
            v-if="doc.is_downloadable"
            class="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-900 disabled:opacity-50 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-white"
            :disabled="processingDocumentId === doc.id"
            title="Скачать PDF"
            @click="emit('download', doc)"
          >
            <span class="material-icons-round text-[18px]">download</span>
          </button>
          <label
            v-else-if="canReplace"
            class="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-teal-600 hover:bg-teal-50 hover:text-teal-700 dark:text-teal-400 dark:hover:bg-teal-900/30 dark:hover:text-teal-300"
            title="Добавить файл"
          >
            <span class="material-icons-round text-[18px]">attach_file</span>
            <input type="file" class="hidden" :accept="DOCUMENT_FILE_ACCEPT" :disabled="processingDocumentId === doc.id" @change="emit('attach', doc, $event)" />
          </label>
          <button
            v-if="canDelete"
            class="flex h-8 w-8 items-center justify-center rounded-lg text-red-400 hover:bg-red-500/10 hover:text-red-500 disabled:opacity-50"
            :disabled="processingDocumentId === doc.id"
            title="Удалить"
            @click="emit('delete', doc.id)"
          >
            <span class="material-icons-round text-[18px]">delete</span>
          </button>
        </div>
      </div>
    </div>
    <div v-else class="flex flex-col items-center gap-2 rounded-xl border border-dashed border-slate-300 px-4 py-5 text-center dark:border-slate-700">
      <p class="text-sm font-medium text-slate-700 dark:text-slate-200">Документов нет</p>
      <button v-if="canCreate" type="button" class="btn-mini h-8 text-xs" @click="emit('create')">
        <span class="material-icons-round text-[15px]">add</span>
        Создать
      </button>
      <p v-else class="text-xs text-slate-500 dark:text-slate-400">{{ accessSummary }}</p>
    </div>
  </div>
</template>
