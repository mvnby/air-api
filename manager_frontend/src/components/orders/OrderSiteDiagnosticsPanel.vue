<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue';
import {
  ManagerOrderDiagnosticsService,
  type ManagerOrderDetailResponse,
  type OrderInspectionRevisionItem,
  type OrderInspectionSavePayload,
  type OrderInspectionState,
  type OrderSiteEquipmentItem,
  type OrderSiteItem,
} from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
import { equipmentTitle } from '../equipment/registry';
import OrderSiteTechnicalActPanel from './OrderSiteTechnicalActPanel.vue';

const props = defineProps<{
  order: ManagerOrderDetailResponse;
  site: OrderSiteItem;
  equipment: OrderSiteEquipmentItem[];
  disabled: boolean;
  beforeAction: () => Promise<boolean>;
}>();
const emit = defineEmits<{ busy: [busy: boolean]; stale: [] }>();

type Status = OrderInspectionSavePayload['status'];
const statuses: Record<Status, string> = {
  defect_found: 'Обнаружен дефект',
  no_defect_found: 'Дефект не выявлен',
  inconclusive: 'Нужна дополнительная проверка',
  restored: 'Работа восстановлена',
};
const textFields = [
  { key: 'facts', label: 'Проверенные факты', required: true },
  { key: 'trial_result', label: 'Пробный запуск и текущая работа' },
  { key: 'event_history', label: 'События из журнала' },
  { key: 'recommendations', label: 'Рекомендации по дальнейшим работам' },
  { key: 'performed_actions', label: 'Фактически выполненные действия' },
] as const;
type InspectionDraft = Record<(typeof textFields)[number]['key'], string> & {
  status: Status | '';
  inspected_at: string;
  performer: string;
};
const localDateTime = (value?: string | null) => {
  if (!value) return '';
  const date = new Date(value);
  return Number.isFinite(date.valueOf())
    ? new Date(date.valueOf() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 19)
    : '';
};
const toDraft = (saved?: OrderInspectionRevisionItem | null): InspectionDraft => ({
  status: saved?.status ?? '',
  facts: saved?.facts ?? '',
  trial_result: saved?.trial_result ?? '',
  event_history: saved?.event_history ?? '',
  recommendations: saved?.recommendations ?? '',
  performed_actions: saved?.performed_actions ?? '',
  inspected_at: localDateTime(saved?.inspected_at),
  performer: saved?.performer ?? '',
});
const drafts = ref<Record<number, InspectionDraft>>({});
const draftVersions = ref<Record<number, number>>({});
const inspections = ref<Record<number, OrderInspectionState>>({});
const readErrors = ref<Record<number, string>>({});
const saveErrors = ref<Record<number, string>>({});
const conflicts = ref<Record<number, boolean>>({});
const pendingLoads = new Map<number, Promise<OrderInspectionState | undefined>>();
const loadingItems = ref(new Set<number>());
const expanded = ref(false);
const showAct = ref(false);
const activeEquipmentId = ref<number | null>(null);
const historical = ref<OrderInspectionRevisionItem | null>(null);
const historyDraft = ref<InspectionDraft | null>(null);
const historyLoading = ref(false);
const historyError = ref('');
const saving = ref(false);
const actBusy = ref(false);
const savedVersion = ref<number | null>(null);
let active = true;
let historyRequest = 0;
const intents = new Map<number, { fingerprint: string; request: OrderInspectionSavePayload }>();
onScopeDispose(() => { active = false; });

const draft = computed(() => activeEquipmentId.value === null ? undefined : drafts.value[activeEquipmentId.value]);
const displayDraft = computed(() => historyDraft.value || draft.value);
const current = computed(() => activeEquipmentId.value === null ? undefined : inspections.value[activeEquipmentId.value]);
const shownRecord = computed(() => historical.value || current.value?.inspection);
const readError = computed(() => readErrors.value[activeEquipmentId.value ?? 0]);
const saveError = computed(() => saveErrors.value[activeEquipmentId.value ?? 0]);
const loadedVersion = computed(() => current.value?.current_version ?? 0);
const isConflicted = computed(() => {
  const id = activeEquipmentId.value ?? 0;
  return conflicts.value[id] || (Boolean(drafts.value[id] && current.value) && draftVersions.value[id] !== loadedVersion.value);
});
const inspectionLoading = computed(() => loadingItems.value.has(activeEquipmentId.value ?? 0));
const busy = computed(() => saving.value || actBusy.value);
watch(busy, value => emit('busy', value), { flush: 'sync' });
const canSave = computed(() => !props.disabled && !busy.value && !inspectionLoading.value && !historyLoading.value
  && !historical.value && !isConflicted.value && !readError.value && Boolean(current.value && draft.value?.status
    && draft.value.facts.trim() && (draft.value.status !== 'restored' || draft.value.performed_actions.trim())));

const loadInspection = async (id: number, force = false): Promise<OrderInspectionState | undefined> => {
  const existing = pendingLoads.get(id);
  if (existing) return existing;
  if (!force && inspections.value[id]) return inspections.value[id];
  if (!props.equipment.some(item => item.equipment_id === id)) return;
  delete readErrors.value[id];
  loadingItems.value.add(id);
  const request = Promise.resolve().then(async () => {
    try {
      const response = await ManagerOrderDiagnosticsService.getManagerOrderInspection(props.order.id, props.site.id, id);
      if (!active) return;
      inspections.value[id] = response;
      if (!drafts.value[id]) {
        drafts.value[id] = toDraft(response.inspection);
        draftVersions.value[id] = response.current_version;
      }
      return response;
    } catch (error) {
      if (active) readErrors.value[id] = getApiErrorMessage(error);
    } finally {
      pendingLoads.delete(id);
      if (active) loadingItems.value.delete(id);
    }
  });
  pendingLoads.set(id, request);
  return request;
};
const resetHistory = () => {
  historyRequest += 1;
  historical.value = null;
  historyDraft.value = null;
  historyLoading.value = false;
  historyError.value = '';
};
const selectEquipment = (id: number | null) => {
  activeEquipmentId.value = id;
  savedVersion.value = null;
  resetHistory();
  if (id !== null && expanded.value) void loadInspection(id);
};
watch(() => props.equipment.map(item => item.equipment_id), (ids) => {
  if (!ids.includes(activeEquipmentId.value ?? 0)) selectEquipment(ids[0] ?? null);
}, { immediate: true });
const toggle = () => {
  expanded.value = !expanded.value;
  if (expanded.value && activeEquipmentId.value !== null) void loadInspection(activeEquipmentId.value);
};
const readVersion = async (version: number) => {
  const id = activeEquipmentId.value;
  if (id === null || historyLoading.value || version < 1 || version >= loadedVersion.value) return;
  const request = ++historyRequest;
  historyLoading.value = true;
  historyError.value = '';
  try {
    const response = await ManagerOrderDiagnosticsService.getManagerOrderInspection(props.order.id, props.site.id, id, version);
    if (!active || request !== historyRequest || !response.inspection) return;
    historical.value = response.inspection;
    historyDraft.value = toDraft(response.inspection);
  } catch (error) {
    if (active && request === historyRequest) historyError.value = getApiErrorMessage(error);
  } finally {
    if (active && request === historyRequest) historyLoading.value = false;
  }
};
const reloadEditor = async () => {
  const id = activeEquipmentId.value;
  if (id === null) return;
  const response = await loadInspection(id, true);
  if (!response || !active) return;
  drafts.value[id] = toDraft(response.inspection);
  draftVersions.value[id] = response.current_version;
  delete conflicts.value[id];
  delete saveErrors.value[id];
  intents.delete(id);
};
const optional = (value: string) => value.trim() || null;
const save = async () => {
  const id = activeEquipmentId.value;
  const form = draft.value;
  if (id === null || !form?.status || !canSave.value) return;
  const payload = {
    expected_version: loadedVersion.value,
    status: form.status,
    facts: form.facts.trim(),
    trial_result: optional(form.trial_result),
    event_history: optional(form.event_history),
    recommendations: optional(form.recommendations),
    performed_actions: optional(form.performed_actions),
    inspected_at: form.inspected_at ? new Date(form.inspected_at).toISOString() : null,
    performer: optional(form.performer),
  };
  const fingerprint = JSON.stringify(payload);
  let intent = intents.get(id);
  if (intent?.fingerprint !== fingerprint) {
    intent = { fingerprint, request: { ...payload, idempotency_key: crypto.randomUUID() } };
    intents.set(id, intent);
  }
  saving.value = true;
  savedVersion.value = null;
  delete saveErrors.value[id];
  try {
    if (!await props.beforeAction() || !active) return;
    const response = await ManagerOrderDiagnosticsService.saveManagerOrderInspection(props.order.id, props.site.id, id, intent.request);
    if (!active) return;
    intents.delete(id);
    savedVersion.value = response.result.version;
    inspections.value[id] = { ...response.result, current_version: response.result.version, inspection: null };
    const refreshed = await loadInspection(id, true);
    if (refreshed && active) {
      drafts.value[id] = toDraft(refreshed.inspection);
      draftVersions.value[id] = refreshed.current_version;
    }
  } catch (error) {
    if (!active) return;
    saveErrors.value[id] = getApiErrorMessage(error);
    if ((error as { status?: number })?.status === 409) conflicts.value[id] = true;
  } finally {
    if (active) saving.value = false;
  }
};
</script>

<template>
  <section v-if="equipment.length" class="space-y-3 border-t border-slate-200 pt-3 dark:border-slate-700" data-testid="order-site-diagnostics">
    <button class="btn-mini-outline" type="button" :aria-expanded="expanded" :disabled="busy" @click="toggle">
      {{ expanded ? 'Свернуть результаты диагностики' : 'Результаты диагностики' }}
    </button>
    <div v-show="expanded" class="space-y-3">
      <label class="field-label">
        Осмотр оборудования
        <select
          :value="activeEquipmentId"
          class="field-input"
          data-testid="inspection-equipment"
          :disabled="busy"
          @change="selectEquipment(Number(($event.target as HTMLSelectElement).value))"
        >
          <option v-for="item in equipment" :key="item.equipment_id" :value="item.equipment_id">{{ equipmentTitle(item.equipment) }}</option>
        </select>
      </label>
      <div v-if="loadedVersion" class="flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
        <span>Версия {{ shownRecord?.version || loadedVersion }} из {{ loadedVersion }}</span>
        <span v-if="shownRecord?.recorded_by">· {{ shownRecord.recorded_by }}</span>
        <button
          v-if="(historical?.version || loadedVersion) > 1"
          type="button" class="underline" :disabled="busy || historyLoading"
          @click="readVersion((historical?.version || loadedVersion) - 1)"
        >Предыдущая версия</button>
        <button
          v-if="historical && historical.version + 1 < loadedVersion"
          type="button" class="underline" :disabled="historyLoading"
          @click="readVersion(historical.version + 1)"
        >Следующая версия</button>
        <button v-if="historical" type="button" class="underline" @click="resetHistory">К актуальной версии</button>
      </div>
      <p v-if="inspectionLoading || historyLoading" role="status" class="text-xs text-slate-500">Загружаем осмотр…</p>
      <p v-if="readError || historyError" role="alert" class="break-words text-sm text-red-700 dark:text-red-300">
        {{ readError || historyError }}
        <button v-if="readError" type="button" class="underline" @click="reloadEditor">Повторить загрузку</button>
      </p>
      <form v-if="displayDraft" class="space-y-3 rounded-lg border border-slate-200 p-3 dark:border-slate-700" data-testid="order-inspection-editor" @submit.prevent="save">
        <fieldset class="space-y-3" :disabled="disabled || busy || inspectionLoading || historyLoading || Boolean(historical)">
          <legend class="text-sm font-semibold">{{ historical ? 'История осмотра' : 'Факты осмотра' }}</legend>
          <label class="field-label">
            Состояние
            <select v-model="displayDraft.status" class="field-input" required>
              <option value="" disabled>Выберите состояние</option>
              <option v-for="(label, value) in statuses" :key="value" :value="value">{{ label }}</option>
            </select>
          </label>
          <div class="grid gap-3 sm:grid-cols-2">
            <label v-for="field in textFields" :key="field.key" class="field-label" :class="{ 'sm:col-span-2': field.key === 'facts' }">
              {{ field.label }}
              <textarea
                v-model="displayDraft[field.key]" class="field-input" :name="field.key" rows="2" maxlength="2000"
                :required="field.key === 'facts' || (field.key === 'performed_actions' && displayDraft.status === 'restored')"
              />
            </label>
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <label class="field-label">Когда осмотрели<input v-model="displayDraft.inspected_at" class="field-input" type="datetime-local" step="1" /></label>
            <label class="field-label">Кто осмотрел<input v-model="displayDraft.performer" class="field-input" maxlength="160" /></label>
          </div>
          <div v-if="!disabled && !historical" class="flex flex-wrap justify-end gap-2">
            <button class="btn-mini" type="submit" :disabled="!canSave">{{ saving ? 'Сохраняем…' : 'Сохранить осмотр' }}</button>
          </div>
        </fieldset>
        <p v-if="saveError || isConflicted" role="alert" class="space-x-1 text-sm text-red-700 dark:text-red-300">
          {{ saveError || 'Сохранённая версия изменилась.' }}
          <button v-if="isConflicted" class="underline" type="button" :disabled="inspectionLoading" @click="reloadEditor">Заменить мой черновик сохранённой версией</button>
        </p>
        <p v-if="savedVersion" role="status" class="text-xs text-emerald-700 dark:text-emerald-300">Сохранена версия {{ savedVersion }}.</p>
      </form>

      <button v-if="!showAct && !disabled" class="btn-mini-outline" type="button" :disabled="busy" @click="showAct = true">Подготовить технический акт</button>
      <OrderSiteTechnicalActPanel
        v-if="showAct"
        :order="order"
        :site="site"
        :equipment="equipment"
        :inspections="inspections"
        :load-inspection="loadInspection"
        :disabled="disabled || saving"
        :before-action="beforeAction"
        @busy="actBusy = $event"
        @stale="emit('stale')"
        @close="showAct = false"
      />
    </div>
  </section>
</template>
