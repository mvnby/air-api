<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { LoaderCircle, X } from 'lucide-vue-next';
import { ManagerEquipmentService, type ManagerEquipmentDetailResponse } from '../../client';
import { useDialogA11y } from '../../composables/useDialogA11y';
import { getApiErrorMessage } from '../../utils/api-errors';
import { equipmentLocation, equipmentTitle, formatEquipmentDate, phoneHref, serviceContactPhone } from './registry';
import { equipmentWarrantySummary } from './equipmentWarrantySummary';
import {
  addCalendarMonths, equipmentEditError, equipmentEditForm, equipmentEditPayload, maintenancePreview,
  type EquipmentEditForm,
} from './equipmentEditForm';

const props = defineProps<{ equipmentId: number | null }>();
const emit = defineEmits<{ close: []; saved: [] }>();
const equipment = ref<ManagerEquipmentDetailResponse | null>(null);
const form = ref<EquipmentEditForm | null>(null);
const initial = ref<EquipmentEditForm | null>(null);
const loading = ref(false);
const saving = ref(false);
const error = ref('');
const dialogRef = ref<HTMLElement | null>(null);
const closeButton = ref<HTMLElement | null>(null);
let requestVersion = 0;
let pendingLoad: ReturnType<typeof ManagerEquipmentService.getManagerEquipment> | null = null;
const close = () => { if (!saving.value) emit('close'); };
useDialogA11y({ open: computed(() => props.equipmentId !== null), dialogRef, initialFocusRef: closeButton, close });

const load = async () => {
  const version = ++requestVersion;
  pendingLoad?.cancel?.();
  equipment.value = null;
  form.value = null;
  initial.value = null;
  error.value = '';
  if (props.equipmentId === null) { loading.value = false; return; }
  loading.value = true;
  try {
    pendingLoad = ManagerEquipmentService.getManagerEquipment(props.equipmentId);
    const item = await pendingLoad;
    if (version !== requestVersion) return;
    equipment.value = item;
    initial.value = equipmentEditForm(item);
    form.value = { ...initial.value };
  } catch (cause) {
    if (version === requestVersion) error.value = getApiErrorMessage(cause);
  } finally {
    if (version === requestVersion) { loading.value = false; pendingLoad = null; }
  }
};
watch(() => props.equipmentId, load, { immediate: true });
onBeforeUnmount(() => { requestVersion++; pendingLoad?.cancel?.(); });

const changed = computed(() => Boolean(form.value && initial.value
  && (Object.keys(equipmentEditPayload(form.value, initial.value)).length
    || (form.value.maintenanceEnabled && String(form.value.maintenanceMonths) !== String(initial.value.maintenanceMonths)))));
const validation = computed(() => form.value ? equipmentEditError(form.value, initial.value) : '');
const nextMaintenance = computed(() => form.value ? maintenancePreview(form.value, equipment.value?.last_service_at) : '');
const warrantyEnd = computed(() => {
  if (form.value?.warrantyMode !== 'manual') return equipment.value?.warranty_expires_at;
  if (initial.value?.warrantyMode === 'manual' && form.value.warrantyStart === initial.value.warrantyStart
    && String(form.value.warrantyMonths) === String(initial.value.warrantyMonths)) return equipment.value?.warranty_expires_at;
  return addCalendarMonths(form.value.warrantyStart, Number(form.value.warrantyMonths));
});
const requiredMaintenance = computed(() => (equipment.value?.coverages || [])
  .filter((coverage) => coverage.maintenance_required && coverage.decision_status !== 'voided'
    && (form.value?.warrantyMode !== 'none' || coverage.coverage_type === 'mvn_work')));
const modes = [
  { value: 'auto', label: 'По условиям гарантии' },
  { value: 'manual', label: 'Указать вручную' },
  { value: 'none', label: 'Без гарантии' },
] as const;
const chooseWarrantyMode = (mode: EquipmentEditForm['warrantyMode']) => {
  if (!form.value) return;
  form.value.warrantyMode = mode;
  if (mode === 'manual' && !form.value.warrantyStart) {
    form.value.warrantyStart = form.value.commissionedAt || form.value.installedAt;
  }
};
const save = async () => {
  if (!form.value || !initial.value || props.equipmentId === null || saving.value || !changed.value) return;
  if (validation.value) { error.value = validation.value; return; }
  const version = requestVersion;
  saving.value = true;
  error.value = '';
  try {
    await ManagerEquipmentService.patchManagerEquipment(props.equipmentId, equipmentEditPayload(form.value, initial.value));
    if (version === requestVersion) emit('saved');
  } catch (cause) {
    if (version === requestVersion) error.value = getApiErrorMessage(cause);
  } finally {
    saving.value = false;
  }
};
</script>

<template>
  <Teleport to="body">
    <div v-if="equipmentId !== null" class="fixed inset-0 z-[120] flex items-end justify-center bg-black/50 sm:items-center sm:p-4" @click.self="close">
      <section ref="dialogRef" role="dialog" aria-modal="true" aria-labelledby="equipment-edit-title" tabindex="-1"
        class="flex max-h-[95dvh] w-full max-w-2xl flex-col overflow-hidden rounded-t-xl bg-white shadow-2xl sm:rounded-xl dark:bg-slate-800">
        <header class="flex shrink-0 items-start justify-between gap-3 border-b border-gray-200 px-5 py-4 dark:border-slate-700">
          <div class="min-w-0">
            <h2 id="equipment-edit-title" class="text-lg font-semibold text-gray-950 dark:text-white">Карточка оборудования</h2>
            <p v-if="equipment" class="mt-1 break-words text-sm text-gray-500 dark:text-slate-400">{{ equipmentTitle(equipment) }}</p>
          </div>
          <button ref="closeButton" type="button" class="rounded-md p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-slate-700" :disabled="saving" aria-label="Закрыть карточку" @click="close"><X class="h-5 w-5" /></button>
        </header>

        <div v-if="loading" role="status" class="flex items-center justify-center gap-2 p-12 text-sm text-gray-500"><LoaderCircle class="h-5 w-5 animate-spin" />Загружаем карточку…</div>
        <div v-else-if="!form || !equipment" class="space-y-3 p-5">
          <p role="alert" class="text-sm text-red-700 dark:text-red-300">{{ error }}</p>
          <button type="button" class="text-sm font-semibold text-teal-700 dark:text-teal-300" @click="load">Повторить загрузку</button>
        </div>

        <form v-else class="flex min-h-0 flex-1 flex-col" novalidate @submit.prevent="save">
          <div class="min-h-0 flex-1 overflow-y-auto">
          <fieldset :disabled="saving" class="min-w-0 space-y-6 px-5 py-5">
            <div class="text-sm">
              <p class="font-semibold text-gray-900 dark:text-white">{{ equipment.customer_name || `Клиент #${equipment.customer_id}` }}</p>
              <p v-if="equipmentLocation(equipment)" class="mt-1 text-gray-500 dark:text-slate-400">{{ equipmentLocation(equipment) }}</p>
              <a v-if="serviceContactPhone(equipment)" :href="phoneHref(serviceContactPhone(equipment))" class="mt-1 inline-block font-medium text-teal-700 hover:underline dark:text-teal-300">{{ equipment.service_contact_name ? `${equipment.service_contact_name} · ` : '' }}{{ serviceContactPhone(equipment) }}</a>
            </div>

            <div class="grid gap-3 sm:grid-cols-2">
              <label class="edit-label">Название<input v-model="form.displayName" class="edit-input" autocomplete="off" /></label>
              <label class="edit-label">Происхождение<select v-model="form.source" class="edit-input"><option value="unknown">Не уточнено</option><option value="sold_by_us">Продано нами</option><option value="installed_by_us">Установлено нами</option><option value="customer_owned">Оборудование клиента</option></select></label>
              <label class="edit-label">Дата установки<input v-model="form.installedAt" type="date" class="edit-input" /></label>
              <label class="edit-label">Ввод в эксплуатацию<input v-model="form.commissionedAt" type="date" class="edit-input" /></label>
            </div>

            <section class="space-y-3 border-t border-gray-200 pt-4 dark:border-slate-700" aria-labelledby="equipment-warranty-title">
              <h3 id="equipment-warranty-title" class="text-sm font-semibold text-gray-950 dark:text-white">Гарантия на оборудование</h3>
              <div class="flex flex-wrap gap-2" role="group" aria-label="Условия гарантии оборудования">
                <button v-for="mode in modes" :key="mode.value" type="button" :aria-pressed="form.warrantyMode === mode.value"
                  class="min-h-9 rounded-md border px-3 py-2 text-xs font-semibold transition"
                  :class="form.warrantyMode === mode.value ? 'border-teal-600 bg-teal-50 text-teal-800 dark:bg-teal-500/15 dark:text-teal-200' : 'border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700'"
                  @click="chooseWarrantyMode(mode.value)">{{ mode.label }}</button>
              </div>
              <template v-if="form.warrantyMode === 'manual'">
                <div class="grid gap-3 sm:grid-cols-2">
                  <label class="edit-label">Начало гарантии<input v-model="form.warrantyStart" type="date" required class="edit-input" /></label>
                  <label class="edit-label">Срок гарантии, месяцев<input v-model="form.warrantyMonths" type="number" min="1" max="240" step="1" required class="edit-input" placeholder="Например, 36" /></label>
                </div>
                <p class="text-sm text-gray-700 dark:text-slate-200">Гарантия до: <strong>{{ formatEquipmentDate(warrantyEnd) }}</strong></p>
                <label class="edit-label">Условия и уточнения<textarea v-model="form.warrantyTerms" rows="2" class="edit-input" placeholder="Основание или условия гарантии" /></label>
              </template>
              <p v-else-if="form.warrantyMode === 'none'" class="text-sm leading-6 text-gray-600 dark:text-slate-300">Гарантийный ремонт оборудования не предусмотрен. Напоминания об обслуживании можно включить ниже.</p>
              <template v-else>
                <p v-if="initial?.warrantyMode !== 'auto'" class="text-sm leading-6 text-gray-600 dark:text-slate-300">После сохранения вернутся исходные условия гарантии. Если их не было, гарантию потребуется уточнить.</p>
                <p v-else class="text-sm leading-6 text-gray-600 dark:text-slate-300">{{ equipmentWarrantySummary(equipment).label }}<template v-if="equipment.warranty_expires_at"> · до {{ formatEquipmentDate(equipment.warranty_expires_at) }}</template></p>
                <p class="text-xs text-gray-500 dark:text-slate-400">Чтобы уточнить дату и срок, выберите «Указать вручную».</p>
              </template>
              <p v-for="coverage in requiredMaintenance" :key="coverage.id" class="text-xs leading-5 text-gray-500 dark:text-slate-400">По условиям {{ coverage.coverage_type === 'mvn_work' ? 'гарантии на работы' : 'гарантии' }} обязательно ТО каждые {{ coverage.maintenance_interval_months }} мес.<template v-if="coverage.next_maintenance_due_at"> Ближайшее — {{ formatEquipmentDate(coverage.next_maintenance_due_at) }}.</template></p>
            </section>

            <div class="space-y-3 border-t border-gray-200 pt-4 dark:border-slate-700">
              <label class="flex cursor-pointer items-center gap-2.5 text-sm font-semibold text-gray-950 dark:text-white"><input v-model="form.maintenanceEnabled" type="checkbox" class="h-4 w-4 rounded border-gray-300 accent-teal-600" />Напоминать о ТО</label>
              <template v-if="form.maintenanceEnabled">
                <div class="grid gap-3 sm:grid-cols-2">
                  <label class="edit-label">Интервал ТО, месяцев<input v-model="form.maintenanceMonths" type="number" min="1" max="120" step="1" required class="edit-input" /></label>
                  <label class="edit-label">Отсчитывать ТО с даты<input v-model="form.maintenanceAnchor" type="date" class="edit-input" /><span class="text-xs font-normal leading-5 text-gray-500 dark:text-slate-400">Если не заполнено — с ввода в эксплуатацию или установки.</span></label>
                </div>
                <p class="text-sm text-gray-700 dark:text-slate-200">Следующее ТО: <strong>{{ formatEquipmentDate(nextMaintenance) }}</strong></p>
                <p class="text-xs leading-5 text-gray-500 dark:text-slate-400">В календаре появится напоминание позвонить клиенту и предложить ТО. После зарегистрированного обслуживания дата пересчитается. Напоминание не назначает выезд.</p>
                <p v-if="equipment.last_service_at" class="text-xs text-gray-500 dark:text-slate-400">Последнее ТО: {{ formatEquipmentDate(equipment.last_service_at) }}</p>
              </template>
              <p v-if="requiredMaintenance.length" class="text-xs leading-5 text-gray-500 dark:text-slate-400">Эта галочка управляет напоминанием в календаре. Обязательное ТО по гарантии учитывается отдельно.</p>
            </div>
            <div class="grid gap-3 border-t border-gray-200 pt-4 sm:grid-cols-2 dark:border-slate-700">
              <label class="edit-label">Бренд<input v-model="form.brand" class="edit-input" /></label>
              <label class="edit-label">Модель<input v-model="form.model" class="edit-input" /></label>
              <label class="edit-label">Серийный номер<input v-model="form.serial" class="edit-input" /></label>
              <label class="edit-label">Инвентарный номер<input v-model="form.inventoryNumber" class="edit-input" /></label>
              <label class="edit-label sm:col-span-2">Место установки<input v-model="form.locationHint" class="edit-input" placeholder="Например, серверная" /></label>
              <label class="edit-label sm:col-span-2">Заметки<textarea v-model="form.notes" rows="2" class="edit-input" /></label>
            </div>
          </fieldset>
          </div>

          <footer class="shrink-0 space-y-2 border-t border-gray-200 bg-white px-5 py-3 dark:border-slate-700 dark:bg-slate-800">
            <p v-if="error" role="alert" class="text-sm text-red-700 dark:text-red-300">{{ error }}</p>
            <p v-else-if="changed && validation" role="status" class="text-xs text-amber-800 dark:text-amber-300">{{ validation }}</p>
            <div class="flex justify-end gap-2">
              <button type="button" class="rounded-md border border-gray-200 px-4 py-2 text-sm font-semibold text-gray-700 disabled:opacity-50 dark:border-slate-600 dark:text-slate-200" :disabled="saving" @click="close">Отмена</button>
              <button type="submit" class="inline-flex items-center gap-2 rounded-md bg-teal-600 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700 disabled:opacity-50" :disabled="saving || !changed || Boolean(validation)"><LoaderCircle v-if="saving" class="h-4 w-4 animate-spin" />{{ saving ? 'Сохраняем…' : 'Сохранить' }}</button>
            </div>
          </footer>
        </form>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.edit-label { @apply flex min-w-0 flex-col gap-1.5 text-xs font-medium text-gray-600 dark:text-slate-300; }
.edit-input { @apply min-h-10 w-full min-w-0 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500 dark:border-slate-600 dark:bg-slate-900 dark:text-white; }
</style>
