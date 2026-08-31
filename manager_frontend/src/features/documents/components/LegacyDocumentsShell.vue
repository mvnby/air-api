<script setup lang="ts">
import type { ManagerOrderDetailResponse, ManagerOrderDocumentItem } from '../../../client';
import type { OrderDocumentAccess } from '../../../components/orders/order-document-access';
import type { ToastType } from '../model/document-types';
import DocumentSendModal from '../../../components/orders/DocumentSendModal.vue';
import OrderEmailHistory from '../../../components/orders/OrderEmailHistory.vue';
import DocumentGenerationForm from './DocumentGenerationForm.vue';
import DocumentList from './DocumentList.vue';

defineProps<{
  order: ManagerOrderDetailResponse;
  documents: ManagerOrderDocumentItem[];
  access: OrderDocumentAccess;
  summary: string;
  setupWarning: boolean;
  canSend: boolean;
  uploading: boolean;
  generating: boolean;
  processingId: number | null;
  emailHistoryRefreshKey: number;
}>();
const emit = defineEmits<{
  sent: [];
  settled: [];
  create: [];
  upload: [];
  download: [document: ManagerOrderDocumentItem];
  attach: [document: ManagerOrderDocumentItem, event: Event];
  delete: [documentId: number];
  toast: [message: string, type?: ToastType];
}>();
const sendOpen = defineModel<boolean>('sendOpen', { required: true });
const forwardAttach = (document: ManagerOrderDocumentItem, event: Event) => emit('attach', document, event);
</script>

<template>
  <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700/60 dark:bg-slate-900/60 sm:p-5">
    <DocumentSendModal v-model="sendOpen" :order="order" :documents="documents" @sent="emit('sent')" @settled="emit('settled')" />
    <div class="mb-4 flex flex-col gap-3 border-b border-slate-100 pb-4 dark:border-slate-800 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h3 class="font-['Space_Grotesk'] text-lg font-bold text-slate-900 dark:text-white">Google Docs</h3>
        <p class="mt-1 text-xs font-medium" :class="setupWarning ? 'text-amber-600 dark:text-amber-400' : 'text-slate-500 dark:text-slate-400'">{{ summary }}</p>
        <p v-if="access.mode === 'history'" class="mt-1 text-xs text-slate-500 dark:text-slate-400">{{ access.summary }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-2 sm:justify-end">
        <button class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-teal-600 px-3 text-sm font-semibold text-white shadow-sm hover:bg-teal-700 disabled:opacity-50" :disabled="uploading || !!processingId || generating || !canSend" @click="sendOpen = true"><span class="material-icons-round text-[18px]">send</span>Письмо</button>
        <button v-if="documents.length && access.canCreate" class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[#007f80] px-3 text-sm font-semibold text-white shadow-sm hover:bg-teal-600 disabled:opacity-50" :disabled="generating || !!processingId || uploading" @click="emit('create')"><span class="material-icons-round text-[18px]">add_circle</span>Создать</button>
        <button v-if="access.canUpload" class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-slate-700 px-3 text-sm font-semibold text-white shadow-sm hover:bg-slate-600 disabled:opacity-50" :disabled="uploading || !!processingId || generating" @click="emit('upload')"><span class="material-icons-round text-[18px]" :class="uploading ? 'animate-spin' : ''">{{ uploading ? 'loop' : 'upload_file' }}</span>Загрузить</button>
      </div>
    </div>
    <OrderEmailHistory class="mb-4" :order-id="order.id" :refresh-key="emailHistoryRefreshKey" @toast="emit('toast', $event.message, $event.type || 'success')" />
    <div class="flex flex-col gap-3">
      <DocumentList :documents="documents" :proposals="order.proposals || []" :can-create="access.canCreate" :can-replace="access.canReplace" :can-delete="access.canDelete" :access-summary="access.summary" :processing-document-id="processingId" @create="emit('create')" @download="emit('download', $event)" @attach="forwardAttach" @delete="emit('delete', $event)" />
      <DocumentGenerationForm :customer="order.customer" />
    </div>
  </section>
</template>
