<script setup lang="ts">
import { computed, onMounted, onScopeDispose, ref } from 'vue';
import { Link2, Plus, X } from 'lucide-vue-next';
import {
  ManagerOrderSitesService,
  type ManagerEquipmentItemResponse,
  type ManagerOrderDetailResponse,
  type OrderSiteEquipmentItem,
  type OrderSiteEquipmentLinkRequest,
  type OrderSiteItem,
} from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
import EquipmentLinkDialog from '../equipment/EquipmentLinkDialog.vue';
import EquipmentManualDialog from '../equipment/EquipmentManualDialog.vue';
import { listAllCustomerEquipment } from '../equipment/loadAllCustomerEquipment';
import { equipmentSubtitle, equipmentTitle } from '../equipment/registry';
import OrderSiteDiagnosticsPanel from './OrderSiteDiagnosticsPanel.vue';
import { loadOrderSitePages } from './order-site-pages';

const props = defineProps<{
  site: OrderSiteItem;
  customerId: number;
  diagnosticOrder?: ManagerOrderDetailResponse;
  disabled: boolean;
  beforeAction: () => Promise<boolean>;
}>();
const emit = defineEmits<{
  busy: [busy: boolean];
  'site-updated': [site: OrderSiteItem];
  stale: [];
  'equipment-changed': [];
}>();

type LinkPayload = OrderSiteEquipmentLinkRequest['payload'];
type EquipmentPayload = NonNullable<LinkPayload['equipment']>;
type EquipmentRole = NonNullable<LinkPayload['role']>;
type ComponentPayload = NonNullable<EquipmentPayload['components']>[number];
type ComponentDraft = {
  key: number;
  component_type: ComponentPayload['component_type'];
  brand: string;
  model: string;
  serial: string;
};
const componentLabels: Record<string, string> = {
  indoor_unit: 'Внутренний блок',
  outdoor_unit: 'Наружный блок',
  drain_pump: 'Дренажный насос',
  other: 'Другой компонент',
};
const componentTypeLabel = (type?: string) => type ? componentLabels[type] || type : 'Компонент';
const roleLabels: Record<string, string> = {
  sale: 'Продажа',
  installation: 'Монтаж',
  maintenance: 'Обслуживание',
  repair: 'Ремонт',
  diagnostic: 'Диагностика',
  warranty_case: 'Гарантийный случай',
  other: 'Другое',
};
const items = ref<OrderSiteEquipmentItem[]>([]);
const loading = ref(false);
const readError = ref('');
const saveError = ref('');
const candidateError = ref('');
const action = ref<'link' | 'manual' | null>(null);
const saving = ref(false);
const diagnosticsBusy = ref(false);
const candidates = ref<ManagerEquipmentItemResponse[]>([]);
const candidateLoading = ref(false);
const writtenIds = computed(() => items.value.map(item => item.equipment_id));
const inventoryNumber = ref('');
const refrigerantType = ref('');
const locationHint = ref('');
const components = ref<ComponentDraft[]>([]);
let active = true;
let candidateRequest = 0;
let componentKey = 0;
let intent: { fingerprint: string; request: OrderSiteEquipmentLinkRequest } | undefined;
onScopeDispose(() => { active = false; });

const loadEquipment = async () => {
  if (loading.value) return;
  loading.value = true;
  readError.value = '';
  try {
    const result = await loadOrderSitePages((limit, offset) =>
      ManagerOrderSitesService.managerListOrderSiteEquipment(props.site.order_id, props.site.id, limit, offset),
    );
    if (active) items.value = result;
  } catch (error) {
    if (active) readError.value = 'Не удалось загрузить оборудование. ' + getApiErrorMessage(error);
  } finally {
    if (active) loading.value = false;
  }
};
const openLink = async () => {
  action.value = 'link';
  saveError.value = '';
  candidateError.value = '';
  candidates.value = [];
  candidateLoading.value = true;
  const request = ++candidateRequest;
  try {
    const result = await listAllCustomerEquipment({ customerId: props.customerId });
    if (!active || request !== candidateRequest) return;
    candidates.value = result.filter(item => !item.customer_branch_id
      || item.customer_branch_id === props.site.customer_branch_id);
  } catch (error) {
    if (active && request === candidateRequest) candidateError.value = 'Не удалось загрузить реестр. ' + getApiErrorMessage(error);
  } finally {
    if (active && request === candidateRequest) candidateLoading.value = false;
  }
};
const closeAction = () => {
  action.value = null;
  candidateRequest += 1;
  candidateLoading.value = false;
  saveError.value = '';
  candidateError.value = '';
};
const openManual = () => {
  action.value = 'manual';
  saveError.value = '';
  inventoryNumber.value = '';
  refrigerantType.value = '';
  locationHint.value = '';
  components.value = [];
};
const addComponent = () => {
  components.value.push({
    key: ++componentKey, component_type: 'indoor_unit', brand: '', model: '', serial: '',
  });
};
const removeComponent = (key: number) => {
  components.value = components.value.filter(component => component.key !== key);
};
const save = async (payload: Omit<LinkPayload, 'expected_version'>) => {
  if (saving.value || diagnosticsBusy.value || props.disabled) return;
  const command = { ...payload, expected_version: props.site.version };
  const fingerprint = JSON.stringify(command);
  if (intent?.fingerprint !== fingerprint) {
    intent = { fingerprint, request: { payload: command, idempotency_key: crypto.randomUUID() } };
  }
  const request = intent.request;
  saving.value = true;
  saveError.value = '';
  emit('busy', true);
  try {
    if (!await props.beforeAction() || !active) return;
    const { result } = await ManagerOrderSitesService.managerLinkOrderSiteEquipment(props.site.order_id, props.site.id, request);
    if (!active) return;
    intent = undefined;
    emit('site-updated', result.site);
    items.value = [...items.value.filter(item => item.equipment_id !== result.equipment.equipment_id), result.equipment];
    closeAction();
    emit('equipment-changed');
  } catch (error) {
    if (!active) return;
    const detail = (error as { body?: { detail?: { code?: string; message?: string } } })?.body?.detail;
    if (detail?.code === 'version_conflict') {
      saveError.value = 'Объект изменился. Проверьте обновлённые данные и повторите сохранение.';
      emit('stale');
      await loadEquipment();
    } else {
      saveError.value = 'Не удалось привязать оборудование. ' + getApiErrorMessage(error);
    }
  } finally {
    if (active) {
      saving.value = false;
      emit('busy', false);
    }
  }
};
const linkExisting = (payload: { equipmentId: number; role: string }) =>
  save({ equipment_id: payload.equipmentId, role: payload.role as EquipmentRole });
const createManual = (payload: {
  displayName: string;
  brand: string;
  model: string;
  serial: string;
  installedAt: string;
  role: string;
  notes: string;
}) => save({
  role: payload.role as EquipmentRole,
  equipment: {
    display_name: payload.displayName.trim() || null,
    brand: payload.brand.trim() || null,
    model: payload.model.trim() || null,
    serial: payload.serial.trim() || null,
    installed_at: payload.installedAt ? `${payload.installedAt}T00:00:00` : null,
    inventory_number: inventoryNumber.value.trim() || null,
    refrigerant_type: refrigerantType.value.trim() || null,
    location_hint: locationHint.value.trim() || null,
    notes: payload.notes.trim() || null,
    components: components.value.map(component => ({
      component_type: component.component_type,
      brand: component.brand.trim() || null,
      model: component.model.trim() || null,
      serial: component.serial.trim() || null,
    })),
  },
});

const refreshDiagnosticsScope = () => {
  emit('stale');
  void loadEquipment();
};

onMounted(loadEquipment);
</script>

<template>
  <section class="space-y-3 rounded-lg border border-slate-200 p-3 dark:border-slate-700 sm:p-4" data-testid="order-site-equipment">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0 break-words">
        <h3 class="text-sm font-semibold">{{ site.title || site.address }}</h3>
        <p v-if="site.title && site.address" class="text-xs text-slate-500 dark:text-slate-400">{{ site.address }}</p>
      </div>
      <div v-if="!disabled" class="flex flex-wrap gap-2">
        <button type="button" class="btn-mini-outline" :disabled="loading || saving || diagnosticsBusy" @click="openLink"><Link2 class="h-4 w-4" /> Привязать оборудование</button>
        <button type="button" class="btn-mini-outline" :disabled="loading || saving || diagnosticsBusy" @click="openManual"><Plus class="h-4 w-4" /> Создать оборудование</button>
      </div>
    </div>
    <p v-if="loading" role="status" class="text-sm text-slate-500">Загружаем оборудование…</p>
    <p v-if="readError" role="alert" class="text-sm text-red-700 dark:text-red-300">
      {{ readError }}
      <button type="button" class="underline" :disabled="loading || saving" @click="loadEquipment">Повторить</button>
    </p>
    <p v-else-if="!loading && !items.length" class="text-sm text-slate-500">На объекте пока нет оборудования.</p>
    <ul v-if="items.length" class="space-y-2">
      <li v-for="{ equipment_id: id, equipment, role } in items" :key="id" class="min-w-0 break-words rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-800/60">
        <p class="font-semibold">{{ equipmentTitle(equipment) }} <span class="ml-1 text-xs font-normal text-slate-500">{{ roleLabels[role] || role }}</span></p>
        <p v-if="equipmentSubtitle(equipment)" class="text-xs text-slate-500 dark:text-slate-400">{{ equipmentSubtitle(equipment) }}</p>
        <p v-if="equipment.serial" class="text-xs text-slate-500 dark:text-slate-400">Серийный номер {{ equipment.serial }}</p>
        <p v-if="equipment.inventory_number" class="text-xs text-slate-500 dark:text-slate-400">Инвентарный номер {{ equipment.inventory_number }}</p>
        <p v-if="equipment.refrigerant_type" class="text-xs text-slate-500 dark:text-slate-400">Хладагент {{ equipment.refrigerant_type }}</p>
        <p v-if="equipment.location_hint" class="text-xs text-slate-500 dark:text-slate-400">{{ equipment.location_hint }}</p>
        <ul v-if="equipment.components?.length" class="mt-2 space-y-1 border-t border-slate-200 pt-2 text-xs dark:border-slate-600">
          <li v-for="component in equipment.components" :key="component.id">
            {{ [componentTypeLabel(component.component_type), component.title, component.brand, component.model, component.serial ? `S/N ${component.serial}` : ''].filter(Boolean).join(' · ') }}
          </li>
        </ul>
      </li>
    </ul>

    <OrderSiteDiagnosticsPanel
      v-if="diagnosticOrder && items.length"
      :order="diagnosticOrder"
      :site="site"
      :equipment="items"
      :disabled="disabled || saving"
      :before-action="beforeAction"
      @busy="diagnosticsBusy = $event; emit('busy', $event)"
      @stale="refreshDiagnosticsScope"
    />

    <EquipmentLinkDialog
      :open="action === 'link'"
      :items="candidates"
      :linked-ids="writtenIds"
      :loading="candidateLoading"
      :saving="saving"
      :error="saveError || candidateError"
      default-role="diagnostic"
      help-text="Можно выбрать оборудование этого филиала или оборудование клиента без указанного филиала."
      @close="closeAction"
      @confirm="linkExisting"
    />
    <EquipmentManualDialog
      :open="action === 'manual'"
      :saving="saving"
      :error="saveError"
      :passport="{ identifiesEquipment: Boolean(inventoryNumber.trim() || components.length) }"
      default-role="diagnostic"
      @close="closeAction"
      @confirm="createManual"
    >
      <template #passport>
        <details class="space-y-3 rounded-lg border border-slate-200 p-3 dark:border-slate-700">
          <summary class="cursor-pointer text-sm font-semibold">Паспортные данные и компоненты</summary>
          <div class="grid gap-3 sm:grid-cols-2">
            <label class="field-label">Инвентарный номер<input v-model="inventoryNumber" class="field-input" maxlength="300" /></label>
            <label class="field-label">Хладагент<input v-model="refrigerantType" class="field-input" maxlength="64" /></label>
            <label class="field-label sm:col-span-2">Расположение на объекте<input v-model="locationHint" class="field-input" maxlength="500" /></label>
          </div>
          <div v-for="part in components" :key="part.key" class="space-y-2 rounded-lg border border-slate-200 p-3 dark:border-slate-700">
            <div class="flex items-end gap-2">
              <label class="field-label min-w-0 flex-1">
                Тип компонента
                <select v-model="part.component_type" class="field-input">
                  <option v-for="(label, kind) in componentLabels" :key="kind" :value="kind">{{ label }}</option>
                </select>
              </label>
              <button type="button" class="btn-mini-outline" aria-label="Удалить компонент" @click="removeComponent(part.key)"><X class="h-4 w-4" /></button>
            </div>
            <div class="grid gap-3 sm:grid-cols-2">
              <label class="field-label">Бренд<input v-model="part.brand" class="field-input" maxlength="200" /></label>
              <label class="field-label">Модель<input v-model="part.model" class="field-input" maxlength="300" /></label>
              <label class="field-label sm:col-span-2">Серийный номер<input v-model="part.serial" class="field-input" maxlength="300" /></label>
            </div>
          </div>
          <button type="button" class="btn-mini-outline" :disabled="components.length >= 30" @click="addComponent"><Plus class="h-4 w-4" /> Добавить компонент</button>
        </details>
      </template>
    </EquipmentManualDialog>
  </section>
</template>
