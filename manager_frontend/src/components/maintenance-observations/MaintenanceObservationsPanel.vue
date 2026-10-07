<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { ChevronDown, ChevronUp, LoaderCircle, Plus } from 'lucide-vue-next';
import {
  ApiError, ManagerMaintenanceObservationsService as api,
  type CreateMaintenanceObservation, type MaintenanceObservationDetail,
  type MaintenanceObservationItem, type ManagerEquipmentItemResponse,
} from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
import { listAllCustomerEquipment } from '../equipment/loadAllCustomerEquipment';
import MaintenanceDefectActsPanel from './MaintenanceDefectActsPanel.vue';
import ServiceAttachmentViewer from '../service-attachments/ServiceAttachmentViewer.vue';
import type { ServiceAttachmentItem } from '../service-attachments/types';

const props = defineProps<{
  orderId?: number;
  equipmentId?: number;
  customerId?: number | null;
  customerBranchId?: number | null;
}>();
const selectedIds = ref<number[]>([]);
const actLocked = ref(false);
const selectedObservations = computed(() => items.value.filter((item) => selectedIds.value.includes(item.id)).map((item) => ({ observation_id: item.id, expected_version: item.version })));
const expanded = ref(false);
const loaded = ref(false);
const loading = ref(false);
const saving = ref(false);
const error = ref('');
const message = ref('');
const items = ref<MaintenanceObservationItem[]>([]);
const total = ref(0);
const detail = ref<MaintenanceObservationDetail | null>(null);
const editing = ref(false);
const equipment = ref<ManagerEquipmentItemResponse[]>([]);
const equipmentLoading = ref(false);
const form = ref({ equipment_id: null as number | null, equipment_description: '', facts: '', recommendation: '', original_comment: '', observed_at: '' });
const pendingCreate = ref<CreateMaintenanceObservation | null>(null);
const photos = ref<{ file: File; key: string }[]>([]);
const viewerId = ref<number | null>(null);
let requestVersion = 0;
// Inputs stay independent when this panel is embedded in an equipment/order form.
const formOwner = computed(() => `maintenance-observation-${props.orderId ?? `equipment-${props.equipmentId}`}`);
const locked = computed(() => saving.value || Boolean(pendingCreate.value) || actLocked.value);
const photoItems = computed<ServiceAttachmentItem[]>(() => (detail.value?.photos || []).map((p) => ({
  ...p, file_kind: p.file_kind || 'image', category: p.category || 'defect', mime_type: p.mime_type || 'application/octet-stream', size_bytes: p.size_bytes ?? 0, source: p.source || 'manager_maintenance', processing_status: p.processing_status || 'ready', preview_available: Boolean(p.preview_available), id: p.id ?? null, caption: p.caption ?? null, transcript: p.transcript ?? null,
  processing_error: p.processing_error ?? null, captured_at: p.captured_at ?? null,
})));
const equipmentStateLabel = computed(() => detail.value?.equipment_link_state === 'archived'
  ? 'Оборудование архивировано; историческая связь сохранена.'
  : detail.value?.equipment_link_state === 'moved'
    ? 'Оборудование перенесено на другой объект; замечание относится к исходному объекту.' : '');
const dateLabel = (value: string) => new Date(`${value}${/Z$|[+-]\d\d:\d\d$/.test(value) ? '' : 'Z'}`).toLocaleString('ru-RU');
const localNow = () => { const now = new Date(); return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16); };
const content = () => ({ equipment_id: form.value.equipment_id, equipment_description: form.value.equipment_description.trim(), facts: form.value.facts.trim(), recommendation: form.value.recommendation.trim() });
const changed = () => !detail.value || Object.entries(content()).some(([k, v]) => v !== detail.value?.[k as keyof MaintenanceObservationDetail]);
const valid = computed(() => Boolean(form.value.equipment_description.trim() && form.value.facts.trim() && form.value.recommendation.trim()
  && (detail.value || (form.value.original_comment.trim() && form.value.observed_at))));

async function load(more = false) {
  const version = requestVersion;
  loading.value = true;
  error.value = '';
  try {
    const offset = more ? items.value.length : 0;
    const response = props.orderId !== undefined
      ? await api.listManagerOrderMaintenanceObservations(props.orderId, 50, offset)
      : await api.listManagerEquipmentMaintenanceObservations(props.equipmentId!, 50, offset);
    if (version !== requestVersion) return;
    items.value = more ? [...items.value, ...response.items] : response.items;
    total.value = response.total;
    selectedIds.value = selectedIds.value.filter((id) => items.value.some((item) => item.id === id));
    loaded.value = true;
  } catch (cause) { if (version === requestVersion) error.value = getApiErrorMessage(cause); }
  finally { if (version === requestVersion) loading.value = false; }
}
async function toggle() { expanded.value = !expanded.value; if (expanded.value && !loaded.value) await load(); }
async function loadEquipment(customerId: number, branchId: number | null) {
  const version = requestVersion;
  equipmentLoading.value = true;
  try {
    const all = await listAllCustomerEquipment({ customerId, customerBranchId: branchId });
    if (version === requestVersion) equipment.value = all.filter((e) => (e.customer_branch_id ?? null) === branchId);
  } catch (cause) { if (version === requestVersion) error.value = getApiErrorMessage(cause); }
  finally { if (version === requestVersion) equipmentLoading.value = false; }
}
async function start() {
  if (locked.value) return;
  detail.value = null;
  editing.value = true;
  error.value = ''; message.value = ''; photos.value = [];
  form.value = { equipment_id: null, equipment_description: '', facts: '', recommendation: '', original_comment: '', observed_at: localNow() };
  if (props.customerId) await loadEquipment(props.customerId, props.customerBranchId ?? null);
}
async function open(id: number) {
  if (locked.value) return;
  const version = requestVersion;
  loading.value = true;
  error.value = ''; message.value = '';
  try {
    const result = await api.getManagerMaintenanceObservation(id);
    if (version !== requestVersion) return;
    detail.value = result; editing.value = false; photos.value = [];
    form.value = { ...contentFrom(result), original_comment: result.original_comment, observed_at: result.observed_at };
  } catch (cause) { if (version === requestVersion) error.value = getApiErrorMessage(cause); }
  finally { if (version === requestVersion) loading.value = false; }
}
const contentFrom = (item: MaintenanceObservationItem) => ({ equipment_id: item.equipment_id ?? null, equipment_description: item.equipment_description, facts: item.facts, recommendation: item.recommendation });
async function edit() {
  if (!detail.value || locked.value) return;
  editing.value = true;
  await loadEquipment(detail.value.customer_id, detail.value.customer_branch_id);
}
function choosePhotos(event: Event) {
  const input = event.target as HTMLInputElement;
  for (const file of Array.from(input.files || [])) photos.value.push({ file, key: crypto.randomUUID() });
  input.value = '';
}
async function save() {
  if (saving.value || !valid.value) return;
  const version = requestVersion;
  saving.value = true; error.value = ''; message.value = '';
  try {
    if (!detail.value) {
      pendingCreate.value ||= { ...content(), original_comment: form.value.original_comment.trim(), observed_at: new Date(form.value.observed_at).toISOString(), command_key: crypto.randomUUID() };
      const result = await api.createManagerMaintenanceObservation(props.orderId!, pendingCreate.value);
      if (version !== requestVersion) return;
      detail.value = result; pendingCreate.value = null;
    } else if (changed()) {
      const result = await api.updateManagerMaintenanceObservation(detail.value.id, { ...content(), expected_version: detail.value.version });
      if (version !== requestVersion) return;
      detail.value = result;
    }
    while (photos.value.length) {
      const next = photos.value[0]!;
      const result = await api.uploadManagerMaintenanceObservationPhoto(detail.value!.id, { file: next.file, command_key: next.key });
      if (version !== requestVersion) return;
      detail.value!.photos = [...(detail.value!.photos || []).filter((p) => p.id !== result.id), result];
      photos.value.shift();
    }
    editing.value = false;
    message.value = `Замечание #${detail.value!.id} сохранено${detail.value!.photos?.length ? ' с фото' : ''}.`;
    await load();
  } catch (cause) {
    if (version !== requestVersion) return;
    if (cause instanceof ApiError && cause.status >= 400 && cause.status < 500) pendingCreate.value = null;
    error.value = getApiErrorMessage(cause);
    if (pendingCreate.value) error.value += ' Повторите сохранение: повтор команды безопасен.';
    if (detail.value && photos.value.length) error.value += ` Замечание #${detail.value.id} сохранено; повторите загрузку оставшихся фото.`;
  } finally { if (version === requestVersion) saving.value = false; }
}
watch(() => [props.orderId, props.equipmentId], () => {
  requestVersion++; selectedIds.value = []; actLocked.value = false; loaded.value = false; loading.value = false; saving.value = false;
  items.value = []; total.value = 0; detail.value = null; editing.value = false;
  error.value = ''; message.value = ''; pendingCreate.value = null; photos.value = []; equipment.value = [];
  if (expanded.value) void load();
});
onBeforeUnmount(() => { requestVersion++; });
</script>

<template>
  <section class="min-w-0 rounded-xl border border-gray-200 bg-white dark:border-slate-700 dark:bg-slate-800" aria-label="Замечания при ТО">
    <button type="button" data-testid="observations-toggle" class="flex w-full items-center justify-between gap-3 px-4 py-3 text-left font-semibold text-gray-950 dark:text-white" :aria-expanded="expanded" @click="toggle">
      <span>Замечания при ТО<span v-if="loaded"> · {{ total }}</span></span><ChevronUp v-if="expanded" class="h-5 w-5" /><ChevronDown v-else class="h-5 w-5" />
    </button>
    <div v-if="expanded" class="space-y-3 border-t border-gray-100 p-4 dark:border-slate-700">
      <p class="text-sm text-gray-600 dark:text-slate-300">Одно замечание — один блок или проблема. Неизвестное оборудование можно уточнить позже.</p>
      <button v-if="orderId" type="button" data-testid="observation-new" class="observation-button" :disabled="locked || loading" @click="start"><Plus class="h-4 w-4" />Добавить замечание</button>
      <p v-if="loading" role="status" class="text-sm text-gray-500">Загружаем…</p>
      <p v-if="loaded && !items.length" class="text-sm text-gray-500">Замечаний пока нет.</p>
      <div class="space-y-2">
        <div v-for="item in items" :key="item.id" class="flex min-w-0 items-start gap-2">
          <label v-if="orderId" class="shrink-0 pt-3"><input :form="formOwner" v-model="selectedIds" :value="item.id" type="checkbox" :aria-label="`Выбрать замечание #${item.id} для акта`" :disabled="locked || loading" class="h-5 w-5" /></label>
        <button type="button" class="w-full rounded-lg border border-gray-200 p-3 text-left disabled:opacity-50 dark:border-slate-600" :disabled="locked || loading" @click="open(item.id)">
          <span class="block text-sm font-semibold text-gray-950 dark:text-white">#{{ item.id }} · {{ item.equipment_description }}</span>
          <span class="mt-1 block whitespace-pre-wrap break-words text-sm text-gray-700 dark:text-slate-200">{{ item.facts }}</span>
          <span class="mt-1 block text-xs text-gray-500">ТО #{{ item.source_order_id }} · {{ dateLabel(item.observed_at) }} · {{ item.created_by }}</span>
        </button>
        </div>
      </div>
      <button v-if="items.length < total" type="button" class="observation-button" :disabled="loading || locked" @click="load(true)">Показать ещё</button>
      <MaintenanceDefectActsPanel v-if="orderId" :order-id="orderId" :selected="selectedObservations" @lock="actLocked = $event" @refresh="selectedIds = []; load()" />
      <div v-if="editing || detail" class="space-y-3 rounded-lg bg-gray-50 p-3 dark:bg-slate-900/40">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h3 class="font-semibold text-gray-950 dark:text-white">{{ detail ? `Замечание #${detail.id}` : 'Новое замечание' }}</h3>
          <button v-if="detail && !editing" type="button" class="observation-button" :disabled="locked" @click="edit">Уточнить замечание</button>
        </div>
        <template v-if="detail">
          <p class="text-xs text-gray-500">ТО #{{ detail.source_order_id }} · {{ detail.created_by }} · {{ dateLabel(detail.created_at) }} · Версия {{ detail.version }}</p>
          <div><p class="text-xs font-semibold text-gray-500">Исходный комментарий</p><p class="whitespace-pre-wrap break-words text-sm text-gray-800 dark:text-slate-200">{{ detail.original_comment }}</p></div>
        </template>
        <p v-if="equipmentStateLabel" role="status" class="text-sm text-amber-700 dark:text-amber-300">{{ equipmentStateLabel }} Связь можно сохранить, убрать или уточнить.</p>
        <fieldset v-if="editing" :disabled="locked" class="space-y-3">
          <label v-if="!detail" class="observation-label">Дата обнаружения<input :form="formOwner" v-model="form.observed_at" data-testid="observed-at" type="datetime-local" required class="observation-input" /></label>
          <label v-if="!detail" class="observation-label">Исходный комментарий<textarea :form="formOwner" v-model="form.original_comment" data-testid="original-comment" rows="2" maxlength="10000" required class="observation-input" /></label>
          <label class="observation-label">Блок или место проблемы<input :form="formOwner" v-model="form.equipment_description" data-testid="equipment-description" maxlength="2000" required class="observation-input" placeholder="Например, наружный блок у входа" /></label>
          <label class="observation-label">Оборудование (необязательно)<select :form="formOwner" v-model="form.equipment_id" data-testid="equipment-id" class="observation-input" :disabled="equipmentLoading">
            <option :value="null">Пока неизвестно</option>
            <option v-if="form.equipment_id && !equipment.some((e) => e.id === form.equipment_id)" :value="form.equipment_id">Оборудование #{{ form.equipment_id }} (историческая связь)</option>
            <option v-for="item in equipment" :key="item.id" :value="item.id">{{ item.display_name || [item.brand, item.model].filter(Boolean).join(' ') || `Оборудование #${item.id}` }}</option>
          </select></label>
          <label class="observation-label">Подтверждённые факты<textarea :form="formOwner" v-model="form.facts" data-testid="facts" rows="3" maxlength="10000" required class="observation-input" placeholder="Что обнаружено при осмотре" /></label>
          <label class="observation-label">Рекомендация<textarea :form="formOwner" v-model="form.recommendation" data-testid="recommendation" rows="2" maxlength="10000" required class="observation-input" placeholder="Что рекомендуется уточнить или сделать" /></label>
          <label class="observation-label">Фото<input :form="formOwner" type="file" data-testid="photos" accept="image/jpeg,image/png,image/webp,image/heic,image/heif" multiple class="observation-input" @change="choosePhotos" /></label>
          <ul v-if="photos.length" class="text-xs text-gray-600 dark:text-slate-300"><li v-for="(photo, index) in photos" :key="photo.key" class="flex items-center gap-2"><span class="min-w-0 break-all">{{ photo.file.name }}</span><button type="button" class="shrink-0 underline" @click="photos.splice(index, 1)">Убрать</button></li></ul>
        </fieldset>
        <template v-else-if="detail">
          <p class="text-sm text-gray-700 dark:text-slate-200">{{ detail.equipment_description }} · {{ detail.equipment_id ? `Оборудование #${detail.equipment_id}` : 'Оборудование пока неизвестно' }}</p>
          <div><p class="text-xs font-semibold text-gray-500">Факты</p><p class="whitespace-pre-wrap break-words text-sm text-gray-800 dark:text-slate-200">{{ detail.facts }}</p></div>
          <div><p class="text-xs font-semibold text-gray-500">Рекомендация</p><p class="whitespace-pre-wrap break-words text-sm text-gray-800 dark:text-slate-200">{{ detail.recommendation }}</p></div>
        </template>
        <div v-if="photoItems.length" class="flex flex-wrap gap-2"><button v-for="photo in photoItems" :key="photo.id!" type="button" class="observation-button max-w-full break-all text-left" @click="viewerId = photo.id">{{ photo.filename }}</button></div>
        <details v-if="detail?.revisions?.length" class="text-sm text-gray-600 dark:text-slate-300"><summary class="cursor-pointer">История уточнений</summary><div v-for="revision in detail.revisions" :key="revision.version" class="mt-2 space-y-1 border-t border-gray-200 pt-2 dark:border-slate-700"><p class="text-xs">Версия {{ revision.version }} · {{ revision.actor }} · {{ dateLabel(revision.created_at) }}</p><p class="whitespace-pre-wrap break-words">{{ revision.snapshot.equipment_description }} · {{ revision.snapshot.facts }}</p><p class="whitespace-pre-wrap break-words">{{ revision.snapshot.recommendation }}</p></div></details>
        <div v-if="editing" class="flex flex-wrap gap-2">
          <button type="button" data-testid="observation-save" class="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" :disabled="saving || !valid" @click="save"><LoaderCircle v-if="saving" class="h-4 w-4 animate-spin" />{{ saving ? 'Сохраняем…' : 'Сохранить замечание' }}</button>
          <button type="button" class="observation-button" :disabled="locked" @click="editing = false; photos = []">Отмена</button>
          <button v-if="detail && error" type="button" class="observation-button" :disabled="locked" @click="open(detail.id)">Открыть актуальную версию</button>
        </div>
      </div>
      <p v-if="error" role="alert" class="text-sm text-red-700 dark:text-red-300">{{ error }}</p>
      <button v-if="error && !editing" type="button" class="observation-button" :disabled="loading" @click="load()">Обновить список</button>
      <p v-if="message" role="status" class="text-sm text-emerald-700 dark:text-emerald-300">{{ message }}</p>
    </div>
    <ServiceAttachmentViewer v-model="viewerId" :items="photoItems" />
  </section>
</template>

<style scoped>
.observation-label { @apply flex flex-col gap-1 text-sm font-semibold text-gray-700 dark:text-slate-200; }
.observation-input { @apply w-full min-w-0 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-normal text-gray-950 dark:border-slate-600 dark:bg-slate-800 dark:text-white; }
.observation-button { @apply inline-flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-2 text-sm font-semibold text-gray-700 disabled:opacity-50 dark:border-slate-600 dark:text-slate-200; }
</style>
