<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { ManagerOrderDetailResponse, ManagerRepairComplaintPresetResponse } from '../../client';
import { ManagerOrdersService, ManagerRepairComplaintsService } from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
import OrderDrawerSection from './OrderDrawerSection.vue';
import OrderRepairEquipmentPanel from './OrderRepairEquipmentPanel.vue';
import OrderRepairExpertFields from './OrderRepairExpertFields.vue';
import {
  CUSTOMER_APPROVAL_STATUS_OPTIONS,
  PARTS_STATUS_OPTIONS,
  REFRIGERANT_PRICING_MODE_OPTIONS,
  REPAIR_AI_DEFECT_TYPES,
  REPAIR_CHOICE_OPTIONS,
  REPAIR_WORKFLOW_STATUS_OPTIONS,
  labeledOptionsWithCurrent,
  normalizeRepairMeta,
  selectOptionsWithCurrent,
  type RepairMeta,
} from './repair-meta';

const props = defineProps<{
  order: ManagerOrderDetailResponse;
  orderTitle: string;
  measurementResult: string;
  customerBranchId: number | null;
  objectAddress: string;
}>();

const emit = defineEmits<{
  toast: [payload: { message: string; type: 'success' | 'error' }];
  reload: [orderId: number];
}>();

const expanded = defineModel<boolean>('expanded', { required: true });
const repairMeta = defineModel<RepairMeta>('repairMeta', { required: true });
const complaintPresets = ref<ManagerRepairComplaintPresetResponse[]>([]);
const complaintSearch = ref('');
const complaintsLoading = ref(false);
const aiDefectType = ref(REPAIR_AI_DEFECT_TYPES[0]?.value || '');
const aiAllowAssumptions = ref(false);
const aiPolishExisting = ref(true);
const aiGenerating = ref(false);

const notify = (message: string, type: 'success' | 'error') => {
  emit('toast', { message, type });
};

const workflowStatusLabel = computed(() => (
  REPAIR_WORKFLOW_STATUS_OPTIONS.find((item) => item.value === repairMeta.value.repair_status)?.label || ''
));

const summary = computed(() => {
  const parts: string[] = [];
  if (workflowStatusLabel.value) parts.push(workflowStatusLabel.value);
  if (repairMeta.value.equipment_name.trim()) parts.push(repairMeta.value.equipment_name.trim());
  const serial = repairMeta.value.equipment_serial_number.trim()
    || repairMeta.value.equipment_inventory_number.trim();
  if (serial) parts.push(serial);
  if (repairMeta.value.customer_complaint.trim()) parts.push('есть жалоба');
  if (repairMeta.value.diagnostic_result.trim()) parts.push('есть диагностика');
  if (repairMeta.value.repair_recommendation.trim() || repairMeta.value.technical_conclusion.trim()) {
    parts.push('есть вывод');
  }
  return parts.join(' · ') || 'данные для диагностики и дефектного акта';
});

const filteredPresets = computed(() => {
  const query = complaintSearch.value.trim().toLowerCase();
  return complaintPresets.value.filter((item) => {
    if (!query) return true;
    return [
      item.customer_phrase,
      item.document_wording,
      item.likely_diagnosis,
      item.complaint_group,
    ].some((value) => String(value || '').toLowerCase().includes(query));
  }).slice(0, 12);
});

const selectedAiDefect = computed(() => (
  REPAIR_AI_DEFECT_TYPES.find((item) => item.value === aiDefectType.value)
  || REPAIR_AI_DEFECT_TYPES[0]
));
const repairPossibleOptions = computed(() => (
  selectOptionsWithCurrent(REPAIR_CHOICE_OPTIONS, repairMeta.value.repair_possible)
));
const repairNotViableOptions = computed(() => (
  selectOptionsWithCurrent(REPAIR_CHOICE_OPTIONS, repairMeta.value.repair_not_viable)
));
const customerApprovalStatusOptions = computed(() => (
  labeledOptionsWithCurrent(
    CUSTOMER_APPROVAL_STATUS_OPTIONS,
    repairMeta.value.customer_approval_status,
  )
));
const partsStatusOptions = computed(() => (
  labeledOptionsWithCurrent(PARTS_STATUS_OPTIONS, repairMeta.value.parts_status)
));

const buildPayload = () => normalizeRepairMeta({
  ...repairMeta.value,
  fault_type: repairMeta.value.fault_type || aiDefectType.value,
}, { defaultRepairStatus: true });

const loadComplaintPresets = async () => {
  if (complaintsLoading.value) return;
  complaintsLoading.value = true;
  try {
    const response = await ManagerRepairComplaintsService.listManagerRepairComplaintPresets(
      '',
      null,
      false,
      false,
      100,
    );
    complaintPresets.value = response.items || [];
  } catch (error) {
    console.warn('Failed to load repair complaint presets', error);
  } finally {
    complaintsLoading.value = false;
  }
};

const applyComplaintPreset = (preset: ManagerRepairComplaintPresetResponse) => {
  repairMeta.value.customer_complaint = preset.customer_phrase
    || repairMeta.value.customer_complaint;
  repairMeta.value.complaint_official = preset.document_wording
    || repairMeta.value.complaint_official;
  repairMeta.value.likely_diagnosis = preset.likely_diagnosis
    || repairMeta.value.likely_diagnosis;
};

const generateAiDraft = async () => {
  const defect = selectedAiDefect.value;
  if (!defect || aiGenerating.value) return;
  aiGenerating.value = true;
  try {
    const response = await ManagerRepairComplaintsService.generateManagerRepairActAiDraft({
      defect_type: defect.value,
      defect_label: defect.label,
      allow_assumptions: aiAllowAssumptions.value,
      polish_existing: aiPolishExisting.value,
      equipment_name: repairMeta.value.equipment_name || props.orderTitle || props.order.title || '',
      equipment_brand: repairMeta.value.equipment_brand,
      equipment_model: repairMeta.value.equipment_model,
      equipment_power: repairMeta.value.equipment_power,
      customer_complaint: repairMeta.value.customer_complaint,
      complaint_official: repairMeta.value.complaint_official,
      likely_diagnosis: repairMeta.value.likely_diagnosis,
      diagnostic_notes: repairMeta.value.diagnostic_notes,
      refrigerant_type: repairMeta.value.refrigerant_type,
      refrigerant_amount: repairMeta.value.refrigerant_amount,
      extra_context: repairMeta.value.diagnostic_notes || defect.hint,
      current_meta: repairMeta.value as any,
    });
    repairMeta.value = normalizeRepairMeta({
      ...repairMeta.value,
      ...((response.repair_meta || {}) as Partial<RepairMeta>),
    });
    await ManagerOrdersService.patchManagerOrder(props.order.id, {
      repair_meta: buildPayload() as any,
      measurement_result: props.measurementResult,
    });
    emit('reload', props.order.id);
    notify('Черновик дефектного акта заполнен и сохранен', 'success');
  } catch (error) {
    notify(`AI не смог подготовить черновик: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    aiGenerating.value = false;
  }
};

watch(
  () => props.order.id,
  () => {
    const savedFaultType = repairMeta.value.fault_type
      || (repairMeta.value.structured_diagnosis || {}).fault_type;
    if (savedFaultType && REPAIR_AI_DEFECT_TYPES.some((item) => item.value === savedFaultType)) {
      aiDefectType.value = savedFaultType;
    } else {
      repairMeta.value.fault_type = aiDefectType.value;
    }
    complaintSearch.value = '';
    void loadComplaintPresets();
  },
  { immediate: true },
);

watch(aiDefectType, (value) => {
  repairMeta.value.fault_type = value;
});
</script>

<template>
  <OrderDrawerSection
    v-model:expanded="expanded"
    title="Ремонт / диагностика"
    :summary="summary"
    tone="default"
  >
    <div class="grid gap-3 md:grid-cols-2">
      <div class="md:col-span-2 rounded-xl border border-teal-100 bg-teal-50/50 p-3">
        <div class="mb-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p class="text-sm font-semibold text-teal-900">Библиотека жалоб</p>
            <p class="text-xs text-teal-700/80">Выберите типовую жалобу, чтобы заполнить формулировку и вероятный диагноз.</p>
          </div>
          <button type="button" data-testid="reload-repair-presets" class="btn-mini-outline justify-center whitespace-nowrap text-xs" :disabled="complaintsLoading" @click="loadComplaintPresets">
            <span class="material-icons-round text-[15px]" :class="{ 'animate-spin': complaintsLoading }">refresh</span>
            Обновить
          </button>
        </div>
        <input v-model="complaintSearch" type="search" class="field-input mb-2" placeholder="Найти: не холодит, капает, шумит..." />
        <div v-if="filteredPresets.length" class="flex max-h-44 flex-wrap gap-2 overflow-auto pr-1">
          <button
            v-for="preset in filteredPresets"
            :key="preset.id"
            type="button"
            :data-testid="`repair-preset-${preset.id}`"
            class="rounded-lg border bg-white px-3 py-2 text-left text-xs shadow-sm transition hover:border-teal-300 hover:text-teal-800"
            :class="preset.is_favorite ? 'border-teal-200 text-teal-900' : 'border-slate-200 text-slate-700'"
            @click="applyComplaintPreset(preset)"
          >
            <span class="flex items-center gap-1 font-semibold">
              <span v-if="preset.is_favorite" class="material-icons-round text-[14px] text-amber-500">star</span>
              {{ preset.customer_phrase }}
            </span>
            <span v-if="preset.document_wording" class="mt-1 line-clamp-2 block max-w-[260px] opacity-75">{{ preset.document_wording }}</span>
          </button>
        </div>
        <p v-else class="rounded-lg border border-dashed border-teal-200 bg-white/70 px-3 py-3 text-xs text-teal-700">
          {{ complaintsLoading ? 'Загружаем пресеты...' : 'Подходящих пресетов пока нет.' }}
        </p>
      </div>

      <div class="md:col-span-2 rounded-xl border border-violet-100 bg-violet-50/60 p-3">
        <div class="mb-2 flex flex-col gap-2 lg:flex-row lg:items-end">
          <div class="min-w-0 flex-1">
            <p class="text-sm font-semibold text-violet-950">AI-черновик по выбранной неисправности</p>
            <p class="mt-1 truncate text-xs text-violet-700/80">{{ selectedAiDefect?.label || 'Базовая неисправность не выбрана' }}</p>
          </div>
          <button type="button" data-testid="generate-repair-ai" class="btn-mini h-[42px] justify-center whitespace-nowrap bg-violet-600 hover:bg-violet-700" :disabled="aiGenerating" @click="generateAiDraft">
            <span v-if="aiGenerating" class="material-icons-round animate-spin text-[16px]">loop</span>
            <span v-else class="material-icons-round text-[16px]">auto_awesome</span>
            AI-черновик
          </button>
        </div>
        <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p class="text-xs text-violet-700/80">{{ selectedAiDefect?.hint }}</p>
          <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
            <label class="inline-flex items-center gap-2 rounded-lg bg-white/70 px-2.5 py-1.5 text-xs font-semibold text-violet-800">
              <input v-model="aiPolishExisting" type="checkbox" class="h-4 w-4 rounded border-violet-300 text-violet-600 focus:ring-violet-500" />
              Причесать заполненное
            </label>
            <label class="inline-flex items-center gap-2 rounded-lg bg-white/70 px-2.5 py-1.5 text-xs font-semibold text-violet-800">
              <input v-model="aiAllowAssumptions" type="checkbox" class="h-4 w-4 rounded border-violet-300 text-violet-600 focus:ring-violet-500" />
              Заполнить на усмотрение
            </label>
          </div>
        </div>
      </div>

      <details class="md:col-span-2 rounded-xl border border-slate-200 bg-slate-50 p-3">
        <summary class="cursor-pointer select-none text-sm font-semibold text-slate-900">
          Статусы, согласование и запчасти
          <span class="ml-2 text-xs font-normal text-slate-500">{{ workflowStatusLabel || 'не указано' }}</span>
        </summary>
        <div class="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          <label class="field-label">
            Этап ремонта
            <select v-model="repairMeta.repair_status" class="field-input bg-white">
              <option v-for="option in REPAIR_WORKFLOW_STATUS_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>
          <label class="field-label">
            Согласование клиента
            <select v-model="repairMeta.customer_approval_status" class="field-input bg-white">
              <option v-for="option in customerApprovalStatusOptions" :key="`approval-${option.value || 'empty'}`" :value="option.value">{{ option.label }}</option>
            </select>
          </label>
          <label class="field-label">
            Запчасти
            <select v-model="repairMeta.parts_status" class="field-input bg-white">
              <option v-for="option in partsStatusOptions" :key="`parts-${option.value || 'empty'}`" :value="option.value">{{ option.label }}</option>
            </select>
          </label>
          <label class="field-label">
            Комментарий согласования
            <textarea v-model="repairMeta.customer_approval_note" class="field-input min-h-[64px] bg-white" placeholder="Кто согласовал, когда, условия" />
          </label>
          <label class="field-label">
            Комментарий по запчастям
            <textarea v-model="repairMeta.parts_note" class="field-input min-h-[64px] bg-white" placeholder="Что нужно, сроки, поставщик" />
          </label>
          <label class="field-label">
            Итог ремонта
            <textarea v-model="repairMeta.repair_completion_note" class="field-input min-h-[64px] bg-white" placeholder="Что выполнено или почему закрыто" />
          </label>
        </div>
      </details>

      <label class="field-label md:col-span-2">
        Жалоба клиента
        <textarea v-model="repairMeta.customer_complaint" class="field-input min-h-[72px]" placeholder="Например: не охлаждает, шумит, течет вода..." />
      </label>
      <label class="field-label">
        Базовая неисправность
        <select v-model="aiDefectType" data-testid="repair-defect-type" class="field-input">
          <option v-for="item in REPAIR_AI_DEFECT_TYPES" :key="`main-${item.value}`" :value="item.value">{{ item.label }}</option>
        </select>
      </label>
      <label class="field-label md:col-span-2">
        Детали диагностики / заметки инженера
        <textarea v-model="repairMeta.diagnostic_notes" class="field-input min-h-[72px]" placeholder="Что увидел инженер: симптомы, проверки, ограничения, важные нюансы" />
      </label>
      <label class="field-label">
        Результат диагностики
        <textarea v-model="repairMeta.diagnostic_result" class="field-input min-h-[88px]" placeholder="Что выявлено при диагностике, без лишних чисел и предположений" />
      </label>
      <label class="field-label">
        Рекомендация по ремонту
        <textarea v-model="repairMeta.repair_recommendation" class="field-input min-h-[88px]" placeholder="Что сделать: устранить утечку, заменить узел, дозаправить..." />
      </label>
      <label class="field-label md:col-span-2">
        Формулировка для сметы ремонта
        <textarea v-model="repairMeta.repair_estimate_text" class="field-input min-h-[72px]" placeholder="Короткая строка работ для сметы" />
      </label>
      <label class="field-label">
        Возможен ремонт
        <select v-model="repairMeta.repair_possible" class="field-input">
          <option v-for="option in repairPossibleOptions" :key="`repair-possible-${option || 'empty'}`" :value="option">{{ option || 'Не указано' }}</option>
        </select>
      </label>
      <label class="field-label">
        Ремонт невозможен / нецелесообразен
        <select v-model="repairMeta.repair_not_viable" class="field-input">
          <option v-for="option in repairNotViableOptions" :key="`repair-not-viable-${option || 'empty'}`" :value="option">{{ option || 'Не указано' }}</option>
        </select>
      </label>
      <label class="field-label">
        Хладагент
        <input v-model="repairMeta.refrigerant_type" class="field-input" placeholder="R32, R410A..." />
      </label>
      <label class="field-label">
        Количество хладагента
        <input v-model="repairMeta.refrigerant_amount" class="field-input" placeholder="0,45 кг или по факту" />
      </label>
      <label class="field-label md:col-span-2">
        Расчет хладагента
        <input v-model="repairMeta.refrigerant_pricing_mode" list="refrigerant-pricing-mode-options" class="field-input" placeholder="по фактической массе, включен в стоимость..." />
        <datalist id="refrigerant-pricing-mode-options">
          <option v-for="option in REFRIGERANT_PRICING_MODE_OPTIONS" :key="option" :value="option" />
        </datalist>
      </label>
      <label class="field-label md:col-span-2">
        Причина неремонтопригодности
        <textarea v-model="repairMeta.repair_not_viable_reason" class="field-input min-h-[72px]" placeholder="Заполняйте, если ремонт невозможен или экономически нецелесообразен" />
      </label>

      <OrderRepairEquipmentPanel
        v-model:repair-meta="repairMeta"
        :order-id="order.id"
        :order-title="orderTitle"
        :customer-id="order.customer?.id || null"
        :customer-branch-id="customerBranchId"
        :object-address="objectAddress"
        @toast="emit('toast', $event)"
      />
      <OrderRepairExpertFields v-model:repair-meta="repairMeta" />
    </div>
  </OrderDrawerSection>
</template>
