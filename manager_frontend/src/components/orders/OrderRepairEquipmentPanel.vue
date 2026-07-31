<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type {
  EquipmentServiceEventType,
  ManagerEquipmentDetailResponse,
  ManagerEquipmentHistoryFromRepairOrderPayload,
  ManagerEquipmentItemResponse,
} from '../../client';
import { ManagerEquipmentService } from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
import { EQUIPMENT_EVENT_OPTIONS, type RepairMeta } from './repair-meta';

const props = defineProps<{
  orderId: number;
  orderTitle: string;
  customerId: number | null;
  customerBranchId: number | null;
  objectAddress: string;
}>();

const emit = defineEmits<{
  toast: [payload: { message: string; type: 'success' | 'error' }];
}>();

const repairMeta = defineModel<RepairMeta>('repairMeta', { required: true });
const equipment = ref<ManagerEquipmentItemResponse[]>([]);
const loading = ref(false);
const errorMessage = ref('');
const selectedId = ref<number | null>(null);
const selectedDetail = ref<ManagerEquipmentDetailResponse | null>(null);
const historyLoading = ref(false);
const creating = ref(false);
const recordingHistory = ref(false);
const historyEventType = ref<EquipmentServiceEventType | ''>('');
const historyNotes = ref('');

const selectedEquipment = computed(() => (
  equipment.value.find((item) => item.id === selectedId.value) || null
));

const notify = (message: string, type: 'success' | 'error') => {
  emit('toast', { message, type });
};

const trimOrNull = (value: string) => value.trim() || null;

const reset = () => {
  equipment.value = [];
  selectedId.value = null;
  selectedDetail.value = null;
  errorMessage.value = '';
  historyEventType.value = '';
  historyNotes.value = '';
};

const loadDetail = async (equipmentId: number) => {
  historyLoading.value = true;
  errorMessage.value = '';
  try {
    selectedDetail.value = await ManagerEquipmentService.getManagerEquipment(equipmentId, 10);
  } catch (error) {
    selectedDetail.value = null;
    errorMessage.value = `Не удалось загрузить историю оборудования: ${getApiErrorMessage(error)}`;
  } finally {
    historyLoading.value = false;
  }
};

const selectEquipment = async (equipmentId: number) => {
  selectedId.value = equipmentId;
  await loadDetail(equipmentId);
};

const loadEquipment = async () => {
  if (!props.customerId) {
    reset();
    return;
  }
  loading.value = true;
  errorMessage.value = '';
  try {
    const response = await ManagerEquipmentService.listManagerEquipment(
      props.customerId,
      props.customerBranchId || null,
      1,
      50,
      false,
    );
    equipment.value = response.items || [];
    if (selectedId.value && !equipment.value.some((item) => item.id === selectedId.value)) {
      selectedId.value = null;
      selectedDetail.value = null;
    }
    if (!selectedId.value && equipment.value.length) {
      await selectEquipment(equipment.value[0]!.id);
    } else if (selectedId.value) {
      await loadDetail(selectedId.value);
    }
  } catch (error) {
    equipment.value = [];
    selectedDetail.value = null;
    errorMessage.value = `Не удалось загрузить оборудование клиента: ${getApiErrorMessage(error)}`;
  } finally {
    loading.value = false;
  }
};

const createFromMeta = async () => {
  if (!props.customerId || creating.value) return;
  const meta = repairMeta.value;
  const displayName = trimOrNull(meta.equipment_name) || trimOrNull(props.orderTitle);
  const hasPassportData = Boolean(
    displayName
    || trimOrNull(meta.equipment_brand)
    || trimOrNull(meta.equipment_model)
    || trimOrNull(meta.equipment_serial_number)
    || trimOrNull(meta.equipment_inventory_number),
  );
  if (!hasPassportData) {
    errorMessage.value = 'Заполните название, бренд, модель, серийный или инвентарный номер';
    return;
  }
  creating.value = true;
  errorMessage.value = '';
  try {
    const notes = [
      meta.equipment_power ? `Мощность: ${meta.equipment_power}` : '',
      meta.equipment_commissioning_date
        ? `Ввод в эксплуатацию: ${meta.equipment_commissioning_date}`
        : '',
    ].filter(Boolean).join('\n') || null;
    const created = await ManagerEquipmentService.createManagerEquipment({
      customer_id: props.customerId,
      customer_branch_id: props.customerBranchId || null,
      equipment_type: 'hvac',
      display_name: displayName,
      brand: trimOrNull(meta.equipment_brand),
      model: trimOrNull(meta.equipment_model),
      serial: trimOrNull(meta.equipment_serial_number),
      inventory_number: trimOrNull(meta.equipment_inventory_number),
      location_hint: trimOrNull(props.objectAddress),
      refrigerant_type: trimOrNull(meta.refrigerant_type),
      notes,
    });
    selectedId.value = created.id;
    await loadEquipment();
    await loadDetail(created.id);
    notify('Оборудование создано из полей ремонта', 'success');
  } catch (error) {
    errorMessage.value = `Не удалось создать оборудование: ${getApiErrorMessage(error)}`;
  } finally {
    creating.value = false;
  }
};

const recordHistory = async () => {
  if (!selectedId.value || recordingHistory.value) return;
  recordingHistory.value = true;
  errorMessage.value = '';
  try {
    const payload: ManagerEquipmentHistoryFromRepairOrderPayload = {
      order_id: props.orderId,
      event_type: historyEventType.value || null,
      notes: trimOrNull(historyNotes.value),
    };
    await ManagerEquipmentService.createManagerEquipmentHistoryFromRepairOrder(
      selectedId.value,
      payload,
    );
    historyEventType.value = '';
    historyNotes.value = '';
    await loadDetail(selectedId.value);
    notify('Событие записано в историю оборудования', 'success');
  } catch (error) {
    errorMessage.value = `Не удалось записать историю: ${getApiErrorMessage(error)}`;
  } finally {
    recordingHistory.value = false;
  }
};

const equipmentTitle = (item?: Pick<ManagerEquipmentItemResponse, 'display_name' | 'brand' | 'model' | 'serial' | 'inventory_number'> | null) => {
  if (!item) return 'Оборудование';
  const name = item.display_name?.trim();
  if (name) return name;
  const parts = [item.brand, item.model, item.serial || item.inventory_number]
    .map((value) => value?.trim())
    .filter(Boolean);
  return parts.join(' ') || 'Оборудование';
};

const equipmentSubtitle = (item: ManagerEquipmentItemResponse | ManagerEquipmentDetailResponse) => {
  const parts = [
    item.brand,
    item.model,
    item.serial ? `SN ${item.serial}` : '',
    item.inventory_number ? `Инв. ${item.inventory_number}` : '',
    item.location_hint,
    item.refrigerant_type,
  ].map((value) => value?.trim()).filter(Boolean);
  return parts.join(' · ') || 'Паспортные данные не заполнены';
};

const eventLabel = (value?: EquipmentServiceEventType | null) => (
  EQUIPMENT_EVENT_OPTIONS.find((option) => option.value === value)?.label || 'Другое'
);

const historyLine = (item: NonNullable<ManagerEquipmentDetailResponse['recent_history']>[number]) => {
  const parts = [
    item.complaint_snapshot,
    item.diagnostic_result,
    item.repair_recommendation,
    item.refrigerant_type ? `Хладагент ${item.refrigerant_type}` : '',
    item.refrigerant_amount,
    item.not_repairable ? 'Не ремонтируется' : '',
    item.not_repairable_reason,
    item.notes,
  ].map((value) => value?.trim()).filter(Boolean);
  return parts.join(' · ') || 'Без подробностей';
};

const formatDateTime = (value?: string | null) => {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

watch(
  () => [props.customerId, props.customerBranchId, props.orderId],
  () => void loadEquipment(),
  { immediate: true },
);
</script>

<template>
  <details class="md:col-span-2 rounded-xl border border-slate-200 bg-slate-50 p-3">
    <summary class="cursor-pointer select-none text-sm font-semibold text-slate-900">
      Оборудование и паспортные данные
      <span class="ml-2 text-xs font-normal text-slate-500">{{ repairMeta.equipment_model || repairMeta.equipment_name || 'не заполнено' }}</span>
    </summary>
    <div class="mt-3 grid gap-3 md:grid-cols-2">
      <label class="field-label">
        Оборудование
        <input v-model="repairMeta.equipment_name" class="field-input" placeholder="Кондиционер настенный" />
      </label>
      <label class="field-label">
        Бренд
        <input v-model="repairMeta.equipment_brand" class="field-input" placeholder="LG, Gree, Mitsubishi..." />
      </label>
      <label class="field-label">
        Модель
        <input v-model="repairMeta.equipment_model" class="field-input" placeholder="Модель внутреннего/наружного блока" />
      </label>
      <label class="field-label">
        Мощность
        <input v-model="repairMeta.equipment_power" class="field-input" placeholder="2,5 кВт" />
      </label>
      <label class="field-label">
        Серийный номер
        <input v-model="repairMeta.equipment_serial_number" class="field-input" placeholder="SN..." />
      </label>
      <label class="field-label">
        Инвентарный номер
        <input v-model="repairMeta.equipment_inventory_number" class="field-input" placeholder="Инв. номер заказчика" />
      </label>
      <label class="field-label md:col-span-2">
        Дата ввода в эксплуатацию
        <input v-model="repairMeta.equipment_commissioning_date" class="field-input" placeholder="Например: 2021 г. или 12.05.2021" />
      </label>

      <div class="md:col-span-2 rounded-xl border border-slate-200 bg-slate-50 p-3">
        <div class="mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div class="min-w-0">
            <p class="text-sm font-semibold text-slate-900">Карточка оборудования и история</p>
            <p class="mt-1 text-xs text-slate-600">
              История оборудования записывается отдельным действием и не меняет CRM/Kanban статус заказа.
            </p>
          </div>
          <div class="flex flex-wrap gap-2">
            <button type="button" data-testid="reload-repair-equipment" class="btn-mini-outline justify-center whitespace-nowrap text-xs" :disabled="loading" @click="loadEquipment">
              Обновить
            </button>
            <button type="button" data-testid="create-repair-equipment" class="btn-mini justify-center whitespace-nowrap text-xs" :disabled="creating || !customerId" @click="createFromMeta">
              {{ creating ? 'Создаем...' : 'Создать из полей' }}
            </button>
          </div>
        </div>

        <p v-if="errorMessage" role="alert" class="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {{ errorMessage }}
        </p>

        <div v-if="!customerId" class="rounded-lg border border-dashed border-slate-200 bg-white px-3 py-4 text-center text-xs text-slate-500">
          Выберите клиента, чтобы вести оборудование.
        </div>
        <div v-else-if="loading" class="rounded-lg border border-dashed border-slate-200 bg-white px-3 py-4 text-xs text-slate-500">
          Загружаем оборудование клиента...
        </div>
        <div v-else class="grid gap-3 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <div class="space-y-2">
            <button
              v-for="item in equipment"
              :key="item.id"
              type="button"
              :data-testid="`repair-equipment-${item.id}`"
              class="w-full rounded-lg border px-3 py-2 text-left text-xs transition"
              :class="selectedId === item.id
                ? 'border-teal-400 bg-white text-teal-900 shadow-sm'
                : 'border-slate-200 bg-white text-slate-700 hover:border-teal-200'"
              @click="selectEquipment(item.id)"
            >
              <span class="block break-words font-semibold">{{ equipmentTitle(item) }}</span>
              <span class="mt-1 block break-words text-slate-500">{{ equipmentSubtitle(item) }}</span>
            </button>
            <div v-if="!equipment.length" class="rounded-lg border border-dashed border-slate-200 bg-white px-3 py-4 text-center text-xs text-slate-500">
              {{ customerBranchId ? 'Для выбранного филиала оборудование не найдено.' : 'Оборудование клиента пока не заведено.' }}
            </div>
          </div>

          <div class="rounded-lg border border-slate-200 bg-white p-3">
            <div v-if="historyLoading" class="text-xs text-slate-500">Загружаем историю...</div>
            <template v-else-if="selectedEquipment">
              <div class="mb-3">
                <p class="break-words text-sm font-semibold text-slate-900">{{ equipmentTitle(selectedEquipment) }}</p>
                <p class="mt-1 break-words text-xs text-slate-500">{{ equipmentSubtitle(selectedEquipment) }}</p>
              </div>
              <div class="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                <label class="field-label !mb-0">
                  Тип записи из заказа
                  <select v-model="historyEventType" class="field-input bg-white">
                    <option value="">Определить автоматически</option>
                    <option v-for="option in EQUIPMENT_EVENT_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
                  </select>
                </label>
                <label class="field-label !mb-0">
                  Заметка
                  <input v-model="historyNotes" class="field-input bg-white" placeholder="Например: закрыто после согласования" />
                </label>
              </div>
              <button type="button" data-testid="record-repair-history" class="btn-mini mt-2 w-full justify-center text-xs" :disabled="recordingHistory || !selectedId" @click="recordHistory">
                {{ recordingHistory ? 'Записываем...' : 'Записать историю из этого ремонта' }}
              </button>
              <p class="mt-2 text-[11px] text-slate-500">
                Действие создаст запись истории оборудования из repair meta текущего заказа. Статус заказа и этап ремонта останутся отдельными.
              </p>

              <div class="mt-3 max-h-56 space-y-2 overflow-y-auto pr-1">
                <div v-for="entry in selectedDetail?.recent_history || []" :key="entry.id" class="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-xs">
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="rounded-full bg-teal-50 px-2 py-0.5 font-semibold text-teal-700">{{ eventLabel(entry.event_type) }}</span>
                    <span class="text-slate-500">{{ formatDateTime(entry.event_date) || 'Без даты' }}</span>
                    <span v-if="entry.order_id" class="text-slate-500">Заказ #{{ entry.order_id }}</span>
                  </div>
                  <p class="mt-1 break-words text-slate-600">{{ historyLine(entry) }}</p>
                </div>
                <div v-if="!(selectedDetail?.recent_history || []).length" class="rounded-lg border border-dashed border-slate-200 px-3 py-3 text-center text-xs text-slate-500">
                  История пока пустая
                </div>
              </div>
            </template>
            <div v-else class="text-xs text-slate-500">Выберите оборудование слева или создайте карточку из полей ремонта.</div>
          </div>
        </div>
      </div>
    </div>
  </details>
</template>
