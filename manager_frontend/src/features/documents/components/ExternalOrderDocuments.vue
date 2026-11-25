<script setup lang="ts">
import { computed, nextTick, onScopeDispose, ref, watch } from 'vue';
import { Download, Eye, FileUp } from 'lucide-vue-next';
import { getApiErrorMessage } from '../../../utils/api-errors';
import { readOrderPage } from '../../../services/order-navigation';
import { formatDocumentDate } from '../composables/use-native-document-basis';
import {
  EXTERNAL_DOCUMENT_MAX_BYTES, EXTERNAL_DOCUMENT_TYPES, PRIVATE_DOCUMENT_FILE_ACCEPT, externalOrderDocumentsApi, matchesOrderDocumentSite,
  type ExternalDocumentFileRole, type ExternalDocumentSite, type ExternalDocumentType,
  type ExternalFileVersion, type OrderDocumentWithEvidence,
} from '../integrations/external-order-documents-api';
import ExternalOrderDocumentImport from './ExternalOrderDocumentImport.vue';

const props = defineProps<{
  orderId: number;
  proposalId?: number | null;
  scopeKey: string | null;
  canImport: boolean;
  canWrite: boolean;
  nativeRevision?: string;
}>();
const emit = defineEmits<{
  updated: [documents: OrderDocumentWithEvidence[]];
  siteFilter: [id: number | null];
  refresh: [];
  toast: [payload: { message: string; type?: 'success' | 'error' }];
}>();
const currentContext = computed(() => props.scopeKey ? `${props.scopeKey}:${props.orderId}` : '');
const records = ref<OrderDocumentWithEvidence[]>([]);
const sites = ref<ExternalDocumentSite[]>([]);
const siteFilter = ref<number | null>(null);
const loading = ref(false);
const loadError = ref('');
const siteError = ref('');
const importOpen = ref(false);
const importBusy = ref(false);
const initialType = ref<ExternalDocumentType>('contract');
const attachMode = ref<ExternalDocumentFileRole | null>(null);
const attachDocId = ref<number | null>(null);
const attachFile = ref<File | null>(null);
const attachBusy = ref(false);
const attachError = ref('');
const formHost = ref<HTMLElement | null>(null);
const linkedId = ref<number | null>(null);
let attached = true;
let reads = 0;
let attachIntent: { id: number; role: ExternalDocumentFileRole; version: number; file: File; key: string } | undefined;

const importedDocuments = computed(() => records.value.filter(record => record.origin === 'external_upload' || record.external_files?.length));
const filteredDocuments = computed(() => importedDocuments.value.filter(record => matchesOrderDocumentSite(record, siteFilter.value)));
watch(siteFilter, value => emit('siteFilter', value));
const contracts = computed(() => records.value.filter(record => (
  record.doc_type === 'contract' && (record.status == null || ['issued', 'sent', 'signed'].includes(record.status))
)));
const eligibleSignedDocuments = computed(() => records.value.filter(record => (
  ['contract', 'technical_inspection_act', 'defect_act', 'act'].includes(record.doc_type)
  && (record.status == null || ['issued', 'sent', 'signed'].includes(record.status))
)));
const isMutableOriginal = (record: OrderDocumentWithEvidence) => props.canImport
  && record.origin === 'external_upload' && record.external_status !== 'signed';
const attachOptions = computed(() => attachMode.value === 'original'
  ? records.value.filter(isMutableOriginal) : eligibleSignedDocuments.value);
const attachDoc = computed(() => attachOptions.value.find(record => record.id === attachDocId.value));
const typeName = (value: string) => EXTERNAL_DOCUMENT_TYPES.find(option => option.value === value)?.label || 'Документ';
const documentLabel = (record: OrderDocumentWithEvidence) => `${typeName(record.doc_type)} № ${record.number}`;

const closeAttach = () => {
  attachMode.value = null;
  attachDocId.value = null;
  attachFile.value = null;
  attachError.value = '';
  attachIntent = undefined;
};
const focusForm = (field: string) => {
  void nextTick(() => {
    formHost.value?.scrollIntoView?.({ block: 'nearest' });
    formHost.value?.querySelector<HTMLElement>(field)?.focus({ preventScroll: true });
  });
};
const openImport = (type: ExternalDocumentType = 'contract') => {
  if (!props.canImport || importBusy.value) return;
  closeAttach();
  initialType.value = type;
  importOpen.value = true;
  focusForm('select');
};
const openAttach = (role: ExternalDocumentFileRole, documentId: number | null = null) => {
  if (!props.canWrite || importBusy.value || (role === 'original' && !props.canImport)) return;
  closeAttach();
  importOpen.value = false;
  attachMode.value = role;
  attachDocId.value = documentId;
  focusForm(documentId ? 'input' : 'select');
};
const refresh = async (applyLink = false, refreshSites = true) => {
  if (!currentContext.value) return;
  const context = currentContext.value;
  const requestId = ++reads;
  const orderId = props.orderId;
  loading.value = true;
  loadError.value = '';
  if (refreshSites) siteError.value = '';
  const [docs, locations] = await Promise.allSettled([
    externalOrderDocumentsApi.list(orderId), refreshSites ? externalOrderDocumentsApi.sites(orderId) : Promise.resolve(null),
  ]);
  if (!attached || requestId !== reads || context !== currentContext.value) return;
  loading.value = false;
  if (docs.status === 'fulfilled') {
    records.value = docs.value.items;
    emit('updated', records.value);
  } else loadError.value = getApiErrorMessage(docs.reason);
  if (locations.status === 'rejected') siteError.value = getApiErrorMessage(locations.reason);
  else if (locations.value) sites.value = locations.value.items;
  if (!applyLink) return;
  const url = new URL(window.location.href);
  if (readOrderPage(url.href)?.orderId !== orderId || url.searchParams.get('section') !== 'documents') return;
  const documentId = url.searchParams.get('documentId');
  const id = documentId && /^[1-9]\d*$/.test(documentId) && Number.isSafeInteger(Number(documentId)) ? Number(documentId) : null;
  const target = url.searchParams.get('action');
  if (target === 'uploadExternalDocument') {
    const type = EXTERNAL_DOCUMENT_TYPES.find(option => option.value === url.searchParams.get('documentType'))?.value;
    openImport(type);
  } else if (target === 'attachExternalDocument' && id) {
    const original = url.searchParams.get('fileRole') === 'original';
    const choices = original ? records.value.filter(isMutableOriginal) : eligibleSignedDocuments.value;
    if (choices.some(record => record.id === id)) openAttach(original ? 'original' : 'signed_copy', id);
  } else if (id && importedDocuments.value.some(record => record.id === id)) {
    linkedId.value = id;
    await nextTick();
    const card = formHost.value?.parentElement?.querySelector<HTMLElement>(`[data-testid="external-document-${id}"]`);
    card?.focus({ preventScroll: true });
    card?.scrollIntoView?.({ block: 'center' });
  }
};

const saveResult = (document: OrderDocumentWithEvidence) => {
  const recordsById = new Map(records.value.map(record => [record.id, record]));
  recordsById.set(document.id, document);
  records.value = [...recordsById.values()];
  emit('updated', records.value);
  emit('refresh');
  emit('toast', { message: 'Документ сохранён.' });
};
const imported = (document: OrderDocumentWithEvidence) => {
  importBusy.value = false;
  importOpen.value = false;
  siteFilter.value = null;
  saveResult(document);
};
const pickAttachment = (event: Event) => { attachFile.value = (event.target as HTMLInputElement).files?.[0] || null; };
const saveAttachment = async () => {
  const file = attachFile.value;
  const document = attachDoc.value;
  const role = attachMode.value;
  if (attachBusy.value || !props.canWrite || !file || !document || !role) return;
  attachError.value = '';
  if (!file.size || file.size > EXTERNAL_DOCUMENT_MAX_BYTES) {
    attachError.value = 'Размер файла должен быть от 1 байта до 10 МБ.';
    return;
  }
  const version = document.file_version || 0;
  if (attachIntent?.id !== document.id || attachIntent.role !== role || attachIntent.version !== version || attachIntent.file !== file) {
    attachIntent = { id: document.id, role, version, file, key: crypto.randomUUID() };
  }
  const context = currentContext.value;
  attachBusy.value = true;
  try {
    const saved = await externalOrderDocumentsApi.attach(document.id, role, version, file, attachIntent.key);
    if (!attached || context !== currentContext.value) return;
    closeAttach();
    saveResult(saved);
  } catch (failure) {
    if (!attached || context !== currentContext.value) return;
    attachError.value = getApiErrorMessage(failure);
    if ((failure as { status?: number }).status === 409) void refresh();
  } finally {
    if (attached && context === currentContext.value) attachBusy.value = false;
  }
};

const binaryBusy = ref(false);
const preview = ref<{ record: OrderDocumentWithEvidence; file: ExternalFileVersion; page: number; url: string } | null>(null);
const previewError = ref('');
let binaryRequest: AbortController | undefined;
const closePreview = () => {
  binaryRequest?.abort();
  binaryRequest = undefined;
  binaryBusy.value = false;
  if (preview.value) URL.revokeObjectURL(preview.value.url);
  preview.value = null;
  previewError.value = '';
};
const readFile = async (record: OrderDocumentWithEvidence, file: ExternalFileVersion, page?: number) => {
  if (binaryBusy.value) return;
  binaryBusy.value = true;
  previewError.value = '';
  const controller = new AbortController();
  binaryRequest = controller;
  try {
    const blob = await externalOrderDocumentsApi.file(record.id, file.version, controller.signal, page);
    if (controller.signal.aborted) return;
    const url = URL.createObjectURL(blob);
    if (page !== undefined) {
      if (preview.value) URL.revokeObjectURL(preview.value.url);
      preview.value = { record, file, page, url };
    } else {
      const link = document.createElement('a');
      link.href = url;
      link.download = file.filename;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 0);
    }
  } catch (failure) {
    if (controller.signal.aborted) return;
    const message = getApiErrorMessage(failure);
    if (page !== undefined && preview.value) previewError.value = message;
    else emit('toast', { message, type: 'error' });
  } finally {
    if (binaryRequest === controller) {
      binaryRequest = undefined;
      binaryBusy.value = false;
    }
  }
};
watch(currentContext, () => {
  closePreview();
  closeAttach();
  attachBusy.value = false;
  importOpen.value = false;
  importBusy.value = false;
  records.value = [];
  sites.value = [];
  loading.value = false;
  loadError.value = '';
  siteError.value = '';
  siteFilter.value = null;
  linkedId.value = null;
  void refresh(true);
}, { immediate: true });
watch(() => props.canImport, (enabled) => {
  if (enabled) return;
  importOpen.value = false;
  importBusy.value = false;
  if (attachMode.value === 'original') closeAttach();
});
watch(() => props.canWrite, (enabled) => { if (!enabled) closeAttach(); });
watch(() => props.nativeRevision, () => { if (!loading.value) void refresh(false, false); });
onScopeDispose(() => { attached = false; closePreview(); });
</script>

<template>
  <section v-if="scopeKey" class="mt-5 space-y-3 rounded-xl border border-slate-200 p-4 dark:border-slate-700" data-testid="external-order-documents">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h4 class="text-sm font-bold text-slate-900 dark:text-white">Внешние документы</h4>
      <div class="flex flex-wrap gap-2">
        <button v-if="canImport" type="button" class="btn-mini inline-flex items-center gap-1.5 px-3 py-2" :disabled="attachBusy || importBusy || loading" data-testid="open-external-document-import" @click="openImport(); refresh()"><FileUp :size="16" aria-hidden="true" />Импортировать документ</button>
        <button v-if="canWrite && eligibleSignedDocuments.length" type="button" class="btn-mini px-3 py-2" :disabled="attachBusy || importBusy" data-testid="open-signed-document-attachment" @click="openAttach('signed_copy')">Прикрепить подписанный PDF</button>
      </div>
    </div>
    <div ref="formHost">
      <ExternalOrderDocumentImport v-if="importOpen && canImport" :key="`${currentContext}:${initialType}`" :order-id="orderId" :proposal-id="proposalId" :initial-type="initialType" :sites="sites" :contracts="contracts" @busy="importBusy = $event" @saved="imported" @cancel="importOpen = false" />
      <form v-if="attachMode && canWrite" class="space-y-3 rounded-xl border border-slate-200 p-4 dark:border-slate-700" data-testid="external-document-attach-form" @submit.prevent="saveAttachment">
        <h5 class="font-bold text-slate-900 dark:text-white">{{ attachMode === 'signed_copy' ? 'Подписанный экземпляр' : 'Новая версия оригинала' }}</h5>
        <fieldset class="grid gap-3 sm:grid-cols-2" :disabled="attachBusy">
          <label class="grid gap-1 text-xs font-semibold text-slate-600 dark:text-slate-300">Документ
            <select v-model="attachDocId" class="evidence-input" required data-testid="external-attach-document">
              <option :value="null">Выберите документ</option>
              <option v-for="record in attachOptions" :key="record.id" :value="record.id">{{ documentLabel(record) }} от {{ formatDocumentDate(record.date) }}</option>
            </select>
          </label>
          <label class="grid gap-1 text-xs font-semibold text-slate-600 dark:text-slate-300">Файл · {{ attachMode === 'signed_copy' ? 'PDF' : 'DOC, DOCX, PDF' }} до 10 МБ
            <input required type="file" :accept="attachMode === 'signed_copy' ? '.pdf' : PRIVATE_DOCUMENT_FILE_ACCEPT" class="text-sm font-normal" data-testid="external-attach-file" @change="pickAttachment" />
          </label>
        </fieldset>
        <p v-if="attachError" role="alert" class="text-sm text-rose-700 dark:text-rose-300">{{ attachError }}</p>
        <div class="flex flex-wrap gap-2">
          <button type="submit" class="rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" :disabled="attachBusy || !attachDocId || !attachFile" data-testid="save-external-attachment">{{ attachBusy ? 'Прикрепляем…' : 'Прикрепить файл' }}</button>
          <button type="button" class="btn-mini px-4 py-2" :disabled="attachBusy" @click="closeAttach">Отмена</button>
        </div>
      </form>
    </div>
    <p v-if="loading" role="status" class="text-sm text-slate-500">Загружаем внешние документы…</p>
    <div v-if="loadError || (siteError && canWrite)" class="flex flex-wrap items-center gap-2 text-sm text-rose-700 dark:text-rose-300" role="alert">
      {{ loadError || siteError }} <button type="button" class="underline" @click="refresh()">Обновить</button>
    </div>
    <label v-if="sites.length && records.length" class="flex flex-wrap items-center gap-2 text-xs font-semibold text-slate-600 dark:text-slate-300">Документы объекта
      <select v-model="siteFilter" class="evidence-input w-auto" data-testid="external-document-site-filter">
        <option :value="null">Все документы заказа</option>
        <option v-for="site in sites" :key="site.id" :value="site.id">{{ site.title }}</option>
      </select>
    </label>
    <p v-if="!loading && !loadError && !filteredDocuments.length" class="text-sm text-slate-500">{{ siteFilter ? 'У этого объекта пока нет внешних документов.' : 'Внешних документов пока нет.' }}</p>
    <article v-for="record in filteredDocuments" :key="record.id" class="space-y-2 rounded-lg border border-slate-200 px-3 py-2.5 dark:border-slate-700" :class="{ 'ring-2 ring-brand-500': linkedId === record.id }" :tabindex="linkedId === record.id ? -1 : undefined" :data-testid="`external-document-${record.id}`">
      <div class="flex flex-wrap justify-between gap-2">
        <div class="min-w-0">
          <h5 class="break-words text-sm font-semibold text-slate-900 dark:text-white">{{ documentLabel(record) }} от {{ formatDocumentDate(record.date) }}</h5>
          <p class="text-xs text-slate-500">
            {{ record.origin === 'external_upload' ? (record.external_status === 'signed' ? 'Подписан вне CRM' : 'Получен') : 'Подписанный экземпляр к документу CRM' }}
            <span v-if="record.scope_title"> · {{ record.scope_title }}<template v-if="record.scope_address">, {{ record.scope_address }}</template></span>
            <span v-if="record.base_document_number"> · Договор № {{ record.base_document_number }}</span>
          </p>
        </div>
        <button v-if="isMutableOriginal(record)" type="button" class="btn-mini px-2.5 py-1" :disabled="attachBusy || importBusy" :data-testid="`replace-external-original-${record.id}`" @click="openAttach('original', record.id)">{{ record.file_version ? 'Добавить версию' : 'Прикрепить оригинал' }}</button>
      </div>
      <details v-if="record.external_files?.length" :open="linkedId === record.id">
        <summary class="cursor-pointer text-xs font-semibold text-brand-700 dark:text-brand-300">Файлы и версии · {{ record.external_files.length }}</summary>
        <ul class="mt-2 space-y-2">
          <li v-for="file in record.external_files" :key="file.version" class="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-50 p-2 text-sm dark:bg-slate-800">
            <div class="min-w-0 break-all"><span>{{ file.filename }}</span> <span class="text-xs text-slate-500">· {{ file.role === 'original' ? 'Оригинал' : 'Подписанный экземпляр' }} · версия {{ file.version }} · {{ formatDocumentDate(file.uploaded_at) }} · {{ file.uploaded_by }}</span></div>
            <div class="flex gap-2">
              <button v-if="file.mime_type === 'application/pdf'" type="button" class="btn-mini inline-flex items-center gap-1 px-2.5 py-1" :disabled="binaryBusy" :data-testid="`preview-external-file-${record.id}-${file.version}`" @click="readFile(record, file, 1)"><Eye :size="15" aria-hidden="true" />Просмотр</button>
              <button type="button" class="btn-mini inline-flex items-center gap-1 px-2.5 py-1" :disabled="binaryBusy" :data-testid="`download-external-file-${record.id}-${file.version}`" @click="readFile(record, file)"><Download :size="15" aria-hidden="true" />Скачать</button>
            </div>
          </li>
        </ul>
      </details>
    </article>
    <div v-if="preview" class="space-y-2 rounded-xl border border-slate-200 p-3 dark:border-slate-700" data-testid="external-pdf-preview">
      <div class="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span class="break-words font-semibold">{{ preview.file.filename }} · страница {{ preview.page }}</span>
        <div class="flex flex-wrap gap-2">
          <button type="button" class="btn-mini px-2.5 py-1" :disabled="binaryBusy || preview.page === 1" @click="readFile(preview.record, preview.file, preview.page - 1)">Назад</button>
          <button type="button" class="btn-mini px-2.5 py-1" :disabled="binaryBusy || preview.page === 100" @click="readFile(preview.record, preview.file, preview.page + 1)">Следующая страница</button>
          <button type="button" class="btn-mini px-2.5 py-1" @click="closePreview">Закрыть</button>
        </div>
      </div>
      <p v-if="previewError" role="alert" class="text-sm text-rose-700 dark:text-rose-300">{{ previewError }}</p>
      <img :src="preview.url" :alt="`Страница ${preview.page} документа ${preview.file.filename}`" class="mx-auto max-h-[75vh] max-w-full" />
    </div>
  </section>
</template>

<style scoped>
.evidence-input { @apply min-h-9 rounded-lg border border-slate-200 bg-white px-2 text-sm font-normal text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/15 dark:border-slate-700 dark:bg-slate-900 dark:text-white; }
</style>
