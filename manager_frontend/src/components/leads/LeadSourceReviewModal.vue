<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { getApiErrorMessage } from '../../utils/api-errors';
import {
  orderSourceReviewApi,
  type OrderSourceApplyPayload,
  type OrderSourcePreview,
  type SourceCustomer,
  type SourceObject,
} from '../../services/order-source-review';
import CustomerSearchSelect from '../customers/CustomerSearchSelect.vue';
import type { ManagerCatalogCustomerItemResponse } from '../../client';

const props = defineProps<{ open: boolean; orderId: number; leadStatus?: string | null }>();
const emit = defineEmits<{ close: []; applied: [result: { orderId: number; customerId: number | null; appliedFields: string[]; customerAction: string }]; }>();

const preview = ref<OrderSourcePreview | null>(null);
const loading = ref(false);
const applying = ref(false);
const error = ref('');
const customerAction = ref<'existing' | 'create' | 'skip'>('create');
const customer = ref<SourceCustomer>({});
const workSummary = ref('');
const equipmentDetails = ref('');
const objects = ref<SourceObject[]>([]);
const selectedDocumentIds = ref<string[]>([]);
const analysisSource = ref<'source' | 'ai' | 'reviewed'>('source');
const analyzedDocumentIds = ref<string[]>([]);
const selectedExistingCustomer = ref<ManagerCatalogCustomerItemResponse | null>(null);
const expandedDocuments = ref<Record<string, boolean>>({});
const analyzing = ref(false);
const draftsChanged = ref(false);
const analysisOverwriteConfirmed = ref(false);
const confirmed = ref(false);
const isNewLead = computed(() => props.leadStatus === 'new_lead');
const hasCustomerSelection = computed(() => customerAction.value === 'skip'
  || (customerAction.value === 'existing' && Boolean(selectedExistingCustomer.value?.id))
  || (customerAction.value === 'create' && Boolean(customer.value.name?.trim())));
const canApply = computed(() => confirmed.value && !applying.value && hasCustomerSelection.value && (!isNewLead.value || customerAction.value !== 'skip'));
const safeSourceUrl = computed(() => {
  const value = preview.value?.source_url;
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null;
  } catch { return null; }
});
const safeDocumentUrl = (value: string) => (
  value.startsWith(`/api/manager/orders/${props.orderId}/source-documents/`) ? value : null
);
const documentExcerpt = (value: string) => value.length > 1_200 ? `${value.slice(0, 1_200)}…` : value;
const markDraftChanged = () => { draftsChanged.value = true; analysisOverwriteConfirmed.value = false; confirmed.value = false; };
const analyze = async () => {
  if (!selectedDocumentIds.value.length || analyzing.value) return;
  if (draftsChanged.value && !analysisOverwriteConfirmed.value) {
    analysisOverwriteConfirmed.value = true;
    error.value = 'Черновик уже редактировался. Нажмите «Заменить черновик ИИ», если хотите заменить состав работ и объекты.';
    return;
  }
  analyzing.value = true;
  error.value = '';
  try {
    const analyzed = await orderSourceReviewApi.analyze(props.orderId, selectedDocumentIds.value);
    workSummary.value = analyzed.work_summary || '';
    equipmentDetails.value = analyzed.equipment_details || '';
    objects.value = analyzed.objects.map((item) => ({ ...item, equipment: item.equipment.map((equipment) => ({ ...equipment })) }));
    draftsChanged.value = false;
    analysisOverwriteConfirmed.value = false;
    confirmed.value = false;
    preview.value = { ...preview.value!, warnings: analyzed.warnings };
    analysisSource.value = analyzed.analysis_source || 'ai';
    analyzedDocumentIds.value = analyzed.analyzed_document_ids || [...selectedDocumentIds.value];
  } catch (reason) { error.value = getApiErrorMessage(reason); }
  finally { analyzing.value = false; }
};

const resetFromPreview = (value: OrderSourcePreview) => {
  preview.value = value;
  customerAction.value = value.existing_customer_id ? 'existing' : 'create';
  selectedExistingCustomer.value = value.existing_customer_id
    ? { id: value.existing_customer_id, name: value.customer.name || `Клиент #${value.existing_customer_id}` } as ManagerCatalogCustomerItemResponse
    : null;
  customer.value = { ...value.customer };
  workSummary.value = value.work_summary || '';
  equipmentDetails.value = value.equipment_details || '';
  objects.value = value.objects.map((item) => ({ ...item, equipment: item.equipment.map((equipment) => ({ ...equipment })) }));
  selectedDocumentIds.value = value.documents.map((document) => document.id);
  analysisSource.value = value.analysis_source || 'source';
  analyzedDocumentIds.value = value.analyzed_document_ids || [];
  expandedDocuments.value = {};
  draftsChanged.value = false;
  analysisOverwriteConfirmed.value = false;
  confirmed.value = false;
};

const load = async () => {
  loading.value = true;
  error.value = '';
  preview.value = null;
  try {
    resetFromPreview(await orderSourceReviewApi.preview(props.orderId));
  } catch (reason) {
    error.value = getApiErrorMessage(reason);
  } finally {
    loading.value = false;
  }
};

const apply = async () => {
  if (!canApply.value) return;
  const payload: OrderSourceApplyPayload = {
    customer_action: customerAction.value,
    work_summary: workSummary.value.trim() || undefined,
    equipment_details: equipmentDetails.value.trim() || undefined,
    objects: objects.value.filter((item) => item.address.trim()).map((item) => ({
      address: item.address.trim(), equipment: item.equipment.filter((equipment) => equipment.brand || equipment.model || equipment.quantity),
    })),
    document_ids: selectedDocumentIds.value,
    analysis_source: analysisSource.value,
    analyzed_document_ids: analyzedDocumentIds.value,
  };
  if (customerAction.value === 'existing' && selectedExistingCustomer.value?.id) payload.customer_id = selectedExistingCustomer.value.id;
  if (customerAction.value === 'create') payload.customer = { ...customer.value };
  applying.value = true;
  error.value = '';
  try {
    const result = await orderSourceReviewApi.apply(props.orderId, payload);
    emit('applied', { orderId: result.order_id, customerId: result.customer_id || null, appliedFields: result.applied_fields, customerAction: customerAction.value });
  } catch (reason) {
    error.value = getApiErrorMessage(reason);
  } finally {
    applying.value = false;
  }
};

watch(() => [props.open, props.orderId] as const, ([open]) => {
  if (open) void load();
  else preview.value = null;
}, { immediate: true });
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 p-4" @click.self="emit('close')">
    <section class="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl dark:bg-slate-900" role="dialog" aria-modal="true" aria-label="Проработка источника">
      <header class="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4 dark:border-slate-700">
        <div><h2 class="text-lg font-bold">Проработка источника</h2><p v-if="preview" class="mt-1 text-xs text-slate-500">{{ preview.source_code }} · {{ preview.external_id || 'без номера' }}</p></div>
        <button type="button" class="icon-action" aria-label="Закрыть" @click="emit('close')">×</button>
      </header>
      <div class="min-h-0 overflow-y-auto p-5">
        <p v-if="loading" class="text-sm text-slate-500">Загружаем исходные данные…</p>
        <div v-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</div>
        <template v-if="preview">
          <div class="flex flex-wrap gap-3 text-sm"><a v-if="safeSourceUrl" :href="safeSourceUrl" target="_blank" rel="noopener noreferrer" class="font-semibold text-brand-700 underline">Открыть источник</a><span v-if="preview.deadline_at">Срок: {{ new Date(preview.deadline_at).toLocaleDateString('ru-RU') }}</span></div>
          <p v-if="preview.title" class="mt-2 font-semibold">{{ preview.title }}</p>
          <div v-if="preview.warnings.length" class="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">{{ preview.warnings.join(' ') }}</div>

          <section class="mt-4"><h3 class="text-sm font-semibold">Клиент</h3>
            <div class="mt-2 flex gap-2 text-sm">
              <button type="button" class="btn-mini-outline" :class="customerAction === 'existing' ? 'border-brand-500 text-brand-700' : ''" @click="customerAction = 'existing'">Выбрать существующего</button>
              <button type="button" class="btn-mini-outline" :class="customerAction === 'create' ? 'border-brand-500 text-brand-700' : ''" @click="customerAction = 'create'">Создать клиента</button>
              <button v-if="!isNewLead" type="button" class="btn-mini-outline" :class="customerAction === 'skip' ? 'border-brand-500 text-brand-700' : ''" @click="customerAction = 'skip'">Не менять клиента</button>
            </div>
            <div v-if="customerAction === 'existing'" class="mt-2"><p v-if="preview.existing_customer_id" class="mb-2 text-sm text-slate-600">Найден клиент #{{ preview.existing_customer_id }}. Можно выбрать другого.</p><CustomerSearchSelect v-model="selectedExistingCustomer" result-test-id-prefix="source-customer" /></div>
            <div v-if="customerAction === 'create'" class="mt-2 grid gap-2 sm:grid-cols-2"><input v-model="customer.name" class="field-input sm:col-span-2" placeholder="Название или имя" /><select v-model="customer.type" class="field-input"><option value="individual">Физлицо</option><option value="individual_entrepreneur">ИП</option><option value="company">Юрлицо</option></select><input v-model="customer.inn" class="field-input" placeholder="УНП" /><input v-model="customer.email" class="field-input" placeholder="Email" /><input v-model="customer.phone" class="field-input" placeholder="Телефон" /><input v-model="customer.legal_address" class="field-input sm:col-span-2" placeholder="Юридический адрес" /></div>
          </section>

          <section class="mt-4"><h3 class="text-sm font-semibold">Работы</h3><textarea v-model="workSummary" class="field-input mt-2 min-h-20" placeholder="Состав работ" @input="markDraftChanged" /><textarea v-model="equipmentDetails" class="field-input mt-2 min-h-16" placeholder="Оборудование" @input="markDraftChanged" /></section>
          <section class="mt-4"><h3 class="text-sm font-semibold">Объекты</h3><div v-for="(object, index) in objects" :key="index" class="mt-2 rounded-lg border border-slate-200 p-3 dark:border-slate-700"><input v-model="object.address" class="field-input" placeholder="Адрес объекта" @input="markDraftChanged" /><p v-if="object.equipment.length" class="mt-2 text-xs text-slate-600">{{ object.equipment.map((item) => [item.brand, item.model, item.quantity && `×${item.quantity}`].filter(Boolean).join(' ')).join('; ') }}</p></div><p v-if="!objects.length" class="mt-2 text-sm text-slate-500">Объекты не извлечены из источника.</p></section>
          <section class="mt-4"><h3 class="text-sm font-semibold">Исходные документы</h3><label v-for="document in preview.documents" :key="document.id" class="mt-2 flex gap-2 rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700"><input v-model="selectedDocumentIds" type="checkbox" :value="document.id" /><span class="min-w-0"><a v-if="safeDocumentUrl(document.download_url)" :href="safeDocumentUrl(document.download_url)!" target="_blank" rel="noopener noreferrer" class="font-semibold text-brand-700 underline">{{ document.name }}</a><span v-else class="font-semibold">{{ document.name }}</span><span v-if="document.extracted_text" class="mt-1 block whitespace-pre-line text-xs text-slate-500">{{ expandedDocuments[document.id] ? document.extracted_text : documentExcerpt(document.extracted_text) }}</span><button v-if="document.extracted_text && document.extracted_text.length > 1200" type="button" class="mt-1 text-xs font-semibold text-brand-700" @click="expandedDocuments[document.id] = !expandedDocuments[document.id]">{{ expandedDocuments[document.id] ? 'Свернуть' : 'Показать полностью' }}</button></span></label></section>
          <div class="mt-4"><button type="button" class="btn-mini-outline text-xs" :disabled="!selectedDocumentIds.length || analyzing" @click="analyze">{{ analyzing ? 'Обрабатываем ИИ…' : analysisOverwriteConfirmed ? 'Заменить черновик ИИ' : 'Обработать ИИ' }}</button></div><label class="mt-5 flex gap-2 text-sm"><input v-model="confirmed" type="checkbox" />Подтверждаю применение проверенных данных. Цена не устанавливается.</label>
        </template>
      </div>
      <footer class="flex justify-end gap-2 border-t border-slate-200 p-4 dark:border-slate-700"><button type="button" class="btn-mini-outline" @click="emit('close')">Отмена</button><button type="button" class="btn-mini" :disabled="!canApply" @click="apply">{{ applying ? 'Применяем…' : 'Применить' }}</button></footer>
    </section>
  </div>
</template>
