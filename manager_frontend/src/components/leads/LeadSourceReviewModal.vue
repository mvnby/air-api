<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { getApiErrorMessage } from '../../utils/api-errors';
import { api } from '../../api';
import {
  orderSourceReviewApi,
  type OrderSourceApplyPayload,
  type OrderSourcePreview,
  type SourceCustomer,
  type SourceObject,
  type SourceAppliedEvent,
  type SourceCommandHook, type SourceCommandEndHook, downloadSourceOriginal,
} from '../../services/order-source-review';
import CustomerSearchSelect from '../customers/CustomerSearchSelect.vue';
import type { ManagerCatalogCustomerItemResponse } from '../../client';
import type { OrderScenarioOption } from '../orders/OrderScenarioSelector.vue';

const props = defineProps<{ open: boolean; orderId: number; leadStatus?: string | null;
  beforeApply?: SourceCommandHook; afterApply?: SourceCommandHook; endApply?: SourceCommandEndHook;
}>();
const emit = defineEmits<{ close: []; applied: [result: SourceAppliedEvent]; }>();

const preview = ref<OrderSourcePreview | null>(null);
const loading = ref(false);
const applying = ref(false);
const error = ref('');
const customerAction = ref<'existing' | 'create' | 'skip'>('create');
const customer = ref<SourceCustomer>({});
const workSummary = ref('');
const equipmentDetails = ref('');
const objects = ref<SourceObject[]>([]);
const scenarioOptions = ref<OrderScenarioOption[]>([]);
const scenarioKey = ref('');
const scenarioChangedByManager = ref(false);
const fieldSources = ref<Record<string, string>>({});
const selectedDocumentIds = ref<string[]>([]);
const analysisSource = ref<'source' | 'ai' | 'reviewed'>('source');
const analyzedDocumentIds = ref<string[]>([]);
const selectedExistingCustomer = ref<ManagerCatalogCustomerItemResponse | null>(null);
const expandedDocuments = ref<Record<string, boolean>>({});
const analyzing = ref(false);
const draftsChanged = ref(false);
const analysisOverwriteConfirmed = ref(false);
const confirmed = ref(false);
const downloadingDocumentId = ref<string | null>(null);
let scopeVersion = 0;
const sameScope = (orderId: number, version: number) => props.open && props.orderId === orderId && scopeVersion === version;
const close = () => { if (!applying.value) emit('close'); };
const downloadDocument = async (document: OrderSourcePreview['documents'][number]) => {
  if (downloadingDocumentId.value) return;
  const orderId = props.orderId;
  downloadingDocumentId.value = document.id;
  try { await downloadSourceOriginal(orderId, document.id, document.name, () => props.orderId === orderId && props.open); }
  catch (reason) { if (props.orderId === orderId) error.value = getApiErrorMessage(reason); }
  finally { if (props.orderId === orderId) downloadingDocumentId.value = null; }
};
const isNewLead = computed(() => props.leadStatus === 'new_lead');
const keyForScenario = (value: { workflow_type: string; service_type?: string | null }) => `${value.workflow_type}:${value.service_type || ''}`;
const selectedScenario = computed(() => scenarioOptions.value.find((item) => keyForScenario(item) === scenarioKey.value) || null);
const prefillWarnings = computed(() => (preview.value?.equipment_prefill?.warnings || [])
  .filter((warning) => !preview.value?.equipment_prefill?.skipped.some((item) => item.message === warning)));
const hasCustomerSelection = computed(() => customerAction.value === 'skip'
  || (customerAction.value === 'existing' && Boolean(selectedExistingCustomer.value?.id))
  || (customerAction.value === 'create' && Boolean(customer.value.name?.trim())));
const canApply = computed(() => confirmed.value && !loading.value && !analyzing.value && !applying.value && Boolean(selectedScenario.value) && hasCustomerSelection.value && (!isNewLead.value || customerAction.value !== 'skip'));
const chooseScenario = () => { scenarioChangedByManager.value = true; confirmed.value = false; };
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
const sourceFor = (key: string) => fieldSources.value[key] || 'Добавлено менеджером';
const markCustomerChanged = (key: string) => { fieldSources.value[key] = 'Исправлено менеджером'; confirmed.value = false; };
const markDraftChanged = (key?: string) => {
  draftsChanged.value = true; analysisOverwriteConfirmed.value = false; confirmed.value = false;
  if (key) fieldSources.value[key] = 'Исправлено менеджером';
};
const markObjectsChanged = () => {
  markDraftChanged();
  for (const key of Object.keys(fieldSources.value)) {
    if (key.startsWith('objects.')) fieldSources.value[key] = 'Исправлено менеджером';
  }
};
const addObject = () => { objects.value.push({ address: '', equipment: [] }); markObjectsChanged(); };
const removeObject = (index: number) => { objects.value.splice(index, 1); markObjectsChanged(); };
const addEquipment = (object: SourceObject) => { object.equipment.push({ brand: '', model: '', quantity: 1 }); markObjectsChanged(); };
const removeEquipment = (object: SourceObject, index: number) => { object.equipment.splice(index, 1); markObjectsChanged(); };
const analyze = async () => {
  if (!selectedDocumentIds.value.length || analyzing.value || applying.value) return;
  if (draftsChanged.value && !analysisOverwriteConfirmed.value) {
    analysisOverwriteConfirmed.value = true;
    error.value = 'Черновик уже редактировался. Нажмите «Заменить черновик ИИ», если хотите заменить состав работ и объекты.';
    return;
  }
  analyzing.value = true;
  error.value = '';
  const orderId = props.orderId; const version = scopeVersion;
  try {
    const analyzed = await orderSourceReviewApi.analyze(orderId, selectedDocumentIds.value);
    if (!sameScope(orderId, version)) return;
    workSummary.value = analyzed.work_summary || '';
    equipmentDetails.value = analyzed.equipment_details || '';
    objects.value = analyzed.objects.map((item) => ({ ...item, equipment: item.equipment.map((equipment) => ({ ...equipment })) }));
    draftsChanged.value = false;
    analysisOverwriteConfirmed.value = false;
    confirmed.value = false;
    preview.value = { ...preview.value!, warnings: analyzed.warnings };
    preview.value.suggested_scenario = analyzed.suggested_scenario;
    if (isNewLead.value && !scenarioChangedByManager.value) {
      scenarioKey.value = analyzed.suggested_scenario ? keyForScenario(analyzed.suggested_scenario) : '';
    }
    fieldSources.value = { ...analyzed.field_sources };
    analysisSource.value = analyzed.analysis_source || 'ai';
    analyzedDocumentIds.value = analyzed.analyzed_document_ids || [...selectedDocumentIds.value];
  } catch (reason) { if (sameScope(orderId, version)) error.value = getApiErrorMessage(reason); }
  finally { if (sameScope(orderId, version)) analyzing.value = false; }
};

const resetFromPreview = (value: OrderSourcePreview) => {
  preview.value = value;
  customerAction.value = value.existing_customer_id ? 'existing' : 'create';
  selectedExistingCustomer.value = value.existing_customer_id
    ? { id: value.existing_customer_id, name: value.customer.name || `Клиент #${value.existing_customer_id}` } as ManagerCatalogCustomerItemResponse
    : null;
  customer.value = { ...value.customer };
  scenarioKey.value = isNewLead.value
    ? (value.suggested_scenario ? keyForScenario(value.suggested_scenario) : '')
    : (value.current_scenario ? keyForScenario(value.current_scenario) : '');
  scenarioChangedByManager.value = false;
  workSummary.value = value.work_summary || '';
  equipmentDetails.value = value.equipment_details || '';
  objects.value = value.objects.map((item) => ({ ...item, equipment: item.equipment.map((equipment) => ({ ...equipment })) }));
  fieldSources.value = { ...value.field_sources };
  selectedDocumentIds.value = value.documents.map((document) => document.id);
  analysisSource.value = value.analysis_source || 'source';
  analyzedDocumentIds.value = value.analyzed_document_ids || [];
  expandedDocuments.value = {};
  draftsChanged.value = false;
  analysisOverwriteConfirmed.value = false;
  confirmed.value = false;
};

const load = async () => {
  const orderId = props.orderId; const version = scopeVersion;
  loading.value = true;
  error.value = '';
  preview.value = null;
  scenarioOptions.value = [];
  try {
    const [source, scenarios] = await Promise.allSettled([
      orderSourceReviewApi.preview(orderId), api.getManagerOrderScenarios(),
    ]);
    if (!sameScope(orderId, version)) return;
    if (source.status === 'rejected') throw source.reason;
    resetFromPreview(source.value);
    if (scenarios.status === 'fulfilled') scenarioOptions.value = scenarios.value.items;
    else error.value = 'Не удалось загрузить сценарии заказов. Повторно откройте проработку.';
  } catch (reason) {
    if (sameScope(orderId, version)) error.value = getApiErrorMessage(reason);
  } finally {
    if (sameScope(orderId, version)) loading.value = false;
  }
};

const apply = async () => {
  if (!canApply.value) return;
  const chosenScenario = selectedScenario.value!;
  const payload: OrderSourceApplyPayload = {
    customer_action: customerAction.value,
    workflow_type: chosenScenario.workflow_type,
    service_type: chosenScenario.service_type ?? null,
    work_summary: workSummary.value.trim() || undefined,
    equipment_details: equipmentDetails.value.trim() || undefined,
    objects: objects.value.filter((item) => item.address.trim() || item.equipment.some((equipment) => equipment.model?.trim())).map((item) => ({
      address: item.address.trim(), equipment: item.equipment
        .filter((equipment) => equipment.brand?.trim() || equipment.model?.trim() || Number(equipment.quantity) > 0)
        .map((equipment) => ({
          brand: equipment.brand?.trim() || undefined,
          model: equipment.model?.trim() || undefined,
          quantity: Number(equipment.quantity) >= 1 && Number.isInteger(Number(equipment.quantity))
            ? Number(equipment.quantity) : undefined,
        })),
    })),
    document_ids: selectedDocumentIds.value,
    analysis_source: analysisSource.value,
    analyzed_document_ids: analyzedDocumentIds.value,
  };
  if (customerAction.value === 'existing' && selectedExistingCustomer.value?.id) payload.customer_id = selectedExistingCustomer.value.id;
  if (customerAction.value === 'create') payload.customer = { ...customer.value };
  applying.value = true;
  error.value = '';
  const orderId = props.orderId;
  const version = scopeVersion;
  let started = false;
  let applied = false;
  try {
    if (await props.beforeApply?.() === false) return;
    started = true;
    if (!sameScope(orderId, version)) return;
    const result = await orderSourceReviewApi.apply(orderId, payload);
    applied = true;
    if (!sameScope(orderId, version)) return;
    if (await props.afterApply?.() === false || !sameScope(orderId, version)) return;
    emit('applied', { orderId: result.order_id, customerId: result.customer_id || null, appliedFields: result.applied_fields, customerAction: customerAction.value, equipmentPrefill: result.equipment_prefill });
  } catch (reason) {
    if (sameScope(orderId, version)) error.value = `${applied ? 'Данные применены, но карточку не удалось обновить. Повторно откройте заказ. ' : ''}${getApiErrorMessage(reason)}`;
  } finally {
    if (started) props.endApply?.();
    applying.value = false;
  }
};

watch(() => [props.open, props.orderId] as const, ([open]) => {
  scopeVersion++; analyzing.value = false; downloadingDocumentId.value = null;
  if (open) void load();
  else preview.value = null;
}, { immediate: true });
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 p-4" @click.self="close">
    <section class="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl dark:bg-slate-900" role="dialog" aria-modal="true" aria-label="Проработка источника">
      <header class="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4 dark:border-slate-700">
        <div><h2 class="text-lg font-bold">Проработка источника</h2><p v-if="preview" class="mt-1 text-xs text-slate-500">{{ preview.source_code }} · {{ preview.external_id || 'без номера' }}</p></div>
        <button type="button" class="icon-action" aria-label="Закрыть" :disabled="applying" @click="close">×</button>
      </header>
      <div class="min-h-0 overflow-y-auto p-5">
        <p v-if="loading" class="text-sm text-slate-500">Загружаем исходные данные…</p>
        <div v-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</div>
        <template v-if="preview">
          <div class="flex flex-wrap gap-3 text-sm"><a v-if="safeSourceUrl" :href="safeSourceUrl" target="_blank" rel="noopener noreferrer" class="font-semibold text-brand-700 underline">Открыть источник</a><span v-if="preview.deadline_at">Срок: {{ new Date(preview.deadline_at).toLocaleDateString('ru-RU') }}</span></div>
          <p v-if="preview.title" class="mt-2 font-semibold">{{ preview.title }}</p>
          <div v-if="preview.warnings.length" class="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">{{ preview.warnings.join(' ') }}</div>
          <div v-if="preview.equipment_prefill" class="mt-3 text-sm" aria-label="Результат переноса оборудования">
            <p class="font-semibold">Последний перенос оборудования</p>
            <p v-for="(item, index) in preview.equipment_prefill.added" :key="`added-${index}`">{{ item.message }}</p>
            <p v-for="(item, index) in preview.equipment_prefill.skipped" :key="`skipped-${index}`" class="text-amber-800">{{ item.message }}</p>
            <p v-for="(warning, index) in prefillWarnings" :key="`warning-${index}`" class="text-amber-800">{{ warning }}</p>
          </div>

          <label class="mt-4 block text-sm font-semibold">Сценарий заказа
            <select v-model="scenarioKey" class="field-input mt-1" aria-label="Сценарий заказа" @change="chooseScenario">
              <option value="">Выберите сценарий</option>
              <option v-for="option in scenarioOptions" :key="keyForScenario(option)" :value="keyForScenario(option)">{{ option.label }}</option>
            </select>
          </label>
          <p v-if="preview.suggested_scenario" class="mt-1 text-xs text-slate-500">По смыслу работ предложено: {{ preview.suggested_scenario.label }}. Проверьте перед сохранением.</p>
          <p v-else-if="isNewLead" class="mt-1 text-xs text-amber-700">Сценарий не удалось определить однозначно. Выберите его вручную.</p>
          <p v-if="selectedScenario?.workflow_type === 'sales_installation'" class="mt-2 text-xs text-slate-500">При сохранении полные модели с единственным точным совпадением и достаточным наличием добавятся в черновик по текущей цене каталога. Количество по объектам суммируется; остальные позиции останутся для ручного подбора. Остаток не резервируется. Монтаж добавляется отдельно в предложении.</p>

          <section class="mt-4"><h3 class="text-sm font-semibold">Клиент</h3>
            <div class="mt-2 flex gap-2 text-sm">
              <button type="button" class="btn-mini-outline" :class="customerAction === 'existing' ? 'border-brand-500 text-brand-700' : ''" @click="customerAction = 'existing'">Выбрать существующего</button>
              <button type="button" class="btn-mini-outline" :class="customerAction === 'create' ? 'border-brand-500 text-brand-700' : ''" @click="customerAction = 'create'">Создать клиента</button>
              <button v-if="!isNewLead" type="button" class="btn-mini-outline" :class="customerAction === 'skip' ? 'border-brand-500 text-brand-700' : ''" @click="customerAction = 'skip'">Не менять клиента</button>
            </div>
            <div v-if="customerAction === 'existing'" class="mt-2"><p v-if="preview.existing_customer_id" class="mb-2 text-sm text-slate-600">Найден клиент #{{ preview.existing_customer_id }}. Можно выбрать другого.</p><CustomerSearchSelect v-model="selectedExistingCustomer" result-test-id-prefix="source-customer" /></div>
            <div v-if="customerAction === 'create'" class="mt-2 grid gap-2 sm:grid-cols-2">
              <label class="text-xs sm:col-span-2">Название · {{ sourceFor('customer.name') }}<input v-model="customer.name" class="field-input mt-1" placeholder="Название или имя" @input="markCustomerChanged('customer.name')" /></label>
              <label class="text-xs">Тип · {{ sourceFor('customer.type') }}<select v-model="customer.type" class="field-input mt-1" @change="markCustomerChanged('customer.type')"><option value="individual">Физлицо</option><option value="individual_entrepreneur">ИП</option><option value="company">Юрлицо</option></select></label>
              <label class="text-xs">УНП · {{ sourceFor('customer.inn') }}<input v-model="customer.inn" class="field-input mt-1" placeholder="УНП" @input="markCustomerChanged('customer.inn')" /></label>
              <label class="text-xs">Email · {{ sourceFor('customer.email') }}<input v-model="customer.email" class="field-input mt-1" placeholder="Email" @input="markCustomerChanged('customer.email')" /></label>
              <label class="text-xs">Телефон · {{ sourceFor('customer.phone') }}<input v-model="customer.phone" class="field-input mt-1" placeholder="Телефон" @input="markCustomerChanged('customer.phone')" /></label>
              <label class="text-xs sm:col-span-2">Юридический адрес · {{ sourceFor('customer.legal_address') }}<input v-model="customer.legal_address" class="field-input mt-1" placeholder="Юридический адрес" @input="markCustomerChanged('customer.legal_address')" /></label>
            </div>
          </section>

          <section class="mt-4"><h3 class="text-sm font-semibold">Работы</h3><label class="mt-2 block text-xs">Состав · {{ sourceFor('work_summary') }}<textarea v-model="workSummary" class="field-input mt-1 min-h-20" placeholder="Состав работ" @input="markDraftChanged('work_summary')" /></label><label class="mt-2 block text-xs">Оборудование · {{ sourceFor('equipment_details') }}<textarea v-model="equipmentDetails" class="field-input mt-1 min-h-16" placeholder="Оборудование" @input="markDraftChanged('equipment_details')" /></label></section>
          <section class="mt-4">
            <div class="flex items-center justify-between gap-3"><h3 class="text-sm font-semibold">Объекты</h3><button type="button" class="btn-mini-outline text-xs" @click="addObject">Добавить объект</button></div>
            <div v-for="(object, index) in objects" :key="index" class="mt-2 rounded-lg border border-slate-200 p-3 dark:border-slate-700">
              <p class="mb-1 text-xs text-slate-500">Адрес · {{ sourceFor(`objects.${index}.address`) }}</p>
              <div class="flex gap-2"><input v-model="object.address" class="field-input min-w-0 flex-1" :aria-label="`Адрес объекта ${index + 1}`" placeholder="Адрес объекта" @input="markDraftChanged(`objects.${index}.address`)" /><button type="button" class="btn-mini-outline text-xs" :aria-label="`Удалить объект ${index + 1}`" @click="removeObject(index)">Удалить</button></div>
              <div v-for="(equipment, equipmentIndex) in object.equipment" :key="equipmentIndex" class="mt-2 grid grid-cols-[1fr_1fr_5rem_auto] gap-2">
                <p class="col-span-4 text-xs text-slate-500">Оборудование · {{ sourceFor(`objects.${index}.equipment.${equipmentIndex}`) }}</p>
                <input v-model="equipment.brand" class="field-input min-w-0" :aria-label="`Бренд объекта ${index + 1}, строка ${equipmentIndex + 1}`" placeholder="Бренд" @input="markDraftChanged(`objects.${index}.equipment.${equipmentIndex}`)" />
                <input v-model="equipment.model" class="field-input min-w-0" :aria-label="`Модель объекта ${index + 1}, строка ${equipmentIndex + 1}`" placeholder="Модель" @input="markDraftChanged(`objects.${index}.equipment.${equipmentIndex}`)" />
                <input v-model.number="equipment.quantity" class="field-input min-w-0" :aria-label="`Количество объекта ${index + 1}, строка ${equipmentIndex + 1}`" type="number" min="1" placeholder="Шт." @input="markDraftChanged(`objects.${index}.equipment.${equipmentIndex}`)" />
                <button type="button" class="btn-mini-outline text-xs" :aria-label="`Удалить оборудование объекта ${index + 1}, строка ${equipmentIndex + 1}`" @click="removeEquipment(object, equipmentIndex)">×</button>
              </div>
              <button type="button" class="mt-2 text-xs font-semibold text-brand-700" @click="addEquipment(object)">Добавить оборудование</button>
            </div>
            <p v-if="!objects.length" class="mt-2 text-sm text-slate-500">Объекты не извлечены из источника.</p>
          </section>
          <section class="mt-4"><h3 class="text-sm font-semibold">Исходные документы</h3><label v-for="document in preview.documents" :key="document.id" class="mt-2 flex gap-2 rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700"><input v-model="selectedDocumentIds" type="checkbox" :value="document.id" /><span class="min-w-0"><button v-if="safeDocumentUrl(document.download_url)" type="button" :disabled="Boolean(downloadingDocumentId)" class="break-all text-left font-semibold text-brand-700 underline" @click.prevent="downloadDocument(document)">{{ downloadingDocumentId === document.id ? 'Скачиваем…' : document.name }}</button><span v-else class="font-semibold">{{ document.name }}</span><span v-if="document.extracted_text" class="mt-1 block whitespace-pre-line text-xs text-slate-500">{{ expandedDocuments[document.id] ? document.extracted_text : documentExcerpt(document.extracted_text) }}</span><button v-if="document.extracted_text && document.extracted_text.length > 1200" type="button" class="mt-1 text-xs font-semibold text-brand-700" @click="expandedDocuments[document.id] = !expandedDocuments[document.id]">{{ expandedDocuments[document.id] ? 'Свернуть' : 'Показать полностью' }}</button></span></label></section>
          <div class="mt-4"><button type="button" class="btn-mini-outline text-xs" :disabled="!selectedDocumentIds.length || analyzing" @click="analyze">{{ analyzing ? 'Обрабатываем ИИ…' : analysisOverwriteConfirmed ? 'Заменить черновик ИИ' : 'Обработать ИИ' }}</button></div><label class="mt-5 flex gap-2 text-sm"><input v-model="confirmed" type="checkbox" />Подтверждаю применение проверенных данных.</label>
        </template>
      </div>
      <footer class="flex justify-end gap-2 border-t border-slate-200 p-4 dark:border-slate-700"><button type="button" class="btn-mini-outline" @click="emit('close')">Отмена</button><button type="button" class="btn-mini" :disabled="!canApply" @click="apply">{{ applying ? 'Применяем…' : 'Применить' }}</button></footer>
    </section>
  </div>
</template>
