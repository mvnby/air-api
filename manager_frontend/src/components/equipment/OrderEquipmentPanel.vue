<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import {
  Boxes,
  ChevronDown,
  ChevronUp,
  CircleAlert,
  Link2,
  LoaderCircle,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
  WandSparkles,
} from 'lucide-vue-next';
import {
  ManagerEquipmentLinksService,
  ManagerEquipmentService,
  type ManagerEquipmentItemResponse,
  type ManagerOrderEquipmentLinkItemResponse,
} from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
import type { ServiceAttachmentEquipmentOption } from '../service-attachments/types';
import EquipmentLinkDialog from './EquipmentLinkDialog.vue';
import EquipmentManualDialog from './EquipmentManualDialog.vue';
import { listAllCustomerEquipment } from './loadAllCustomerEquipment';
import { confirmDialog } from '../../services/ui-feedback';

const props = withDefaults(defineProps<{
  orderId: number;
  customerId?: number | null;
  customerBranchId?: number | null;
  initialCount?: number | null;
  hasCatalogProducts?: boolean;
}>(), {
  customerId: null,
  customerBranchId: null,
  initialCount: 0,
  hasCatalogProducts: false,
});

const emit = defineEmits<{
  'options-change': [options: ServiceAttachmentEquipmentOption[]];
  'count-change': [count: number];
  reload: [];
  error: [message: string];
}>();

const expanded = ref(false);
const loaded = ref(false);
const loading = ref(false);
const action = ref('');
const error = ref('');
const message = ref('');
const links = ref<ManagerOrderEquipmentLinkItemResponse[]>([]);
const showLinkDialog = ref(false);
const showManualDialog = ref(false);
const customerEquipment = ref<ManagerEquipmentItemResponse[]>([]);
const customerEquipmentLoading = ref(false);
let linksRequestId = 0;
let customerEquipmentRequestId = 0;

const count = computed(() => loaded.value ? links.value.length : Number(props.initialCount || 0));
const countLabel = computed(() => {
  const value = count.value;
  const mod100 = value % 100;
  const mod10 = value % 10;
  const noun = mod100 >= 11 && mod100 <= 14 ? 'единиц' : mod10 === 1 ? 'единица' : mod10 >= 2 && mod10 <= 4 ? 'единицы' : 'единиц';
  return `Оборудование: ${value} ${noun}`;
});
const linkedIds = computed(() => links.value.map((item) => item.equipment.id));

const equipmentTitle = (item: ManagerOrderEquipmentLinkItemResponse['equipment']) => (
  item.display_name
  || [item.brand, item.model].filter(Boolean).join(' ')
  || item.serial
  || `Оборудование #${item.id}`
);

const componentTitle = (component: NonNullable<ManagerOrderEquipmentLinkItemResponse['equipment']['components']>[number]) => {
  const kind = component.component_type === 'indoor_unit'
    ? 'Внутренний'
    : component.component_type === 'outdoor_unit'
      ? 'Наружный'
      : 'Блок';
  const name = [component.brand, component.model].filter(Boolean).join(' ') || component.title || '';
  return `${kind}${name ? `: ${name}` : ''}${component.serial ? ` · ${component.serial}` : ''}`;
};

const roleLabel = (role: string) => ({
  sale: 'Продажа',
  installation: 'Монтаж',
  maintenance: 'ТО',
  repair: 'Ремонт',
  diagnostic: 'Диагностика',
  warranty_case: 'Гарантия',
  other: 'Связано',
}[role] || role);

const coverageLabel = (type: string) => type === 'mvn_work' ? 'Работы MVN' : 'Оборудование';
const coverageState = (timeStatus: string, maintenanceStatus: string) => {
  if (timeStatus === 'voided') return 'Снята';
  if (timeStatus === 'expired') return 'Истекла';
  if (maintenanceStatus === 'overdue') return 'ТО просрочено';
  if (maintenanceStatus === 'due_soon') return 'ТО скоро';
  if (timeStatus === 'active') return 'Действует';
  return 'Нужно уточнить';
};
const coverageClass = (timeStatus: string, maintenanceStatus: string) => {
  if (timeStatus === 'voided' || timeStatus === 'expired' || maintenanceStatus === 'overdue') {
    return 'bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-200';
  }
  if (maintenanceStatus === 'due_soon' || timeStatus === 'unknown') {
    return 'bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200';
  }
  return 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-200';
};

const emitOptions = () => {
  const options = links.value.map<ServiceAttachmentEquipmentOption>((link) => ({
    id: link.equipment.id,
    label: equipmentTitle(link.equipment),
    components: (link.equipment.components || []).map((component) => ({
      id: component.id,
      label: componentTitle(component),
    })),
  }));
  emit('options-change', options);
  emit('count-change', links.value.length);
};

const reportError = (cause: unknown, fallback: string) => {
  const detail = getApiErrorMessage(cause);
  error.value = detail || fallback;
  message.value = '';
  emit('error', error.value);
};

const loadLinks = async (force = false) => {
  if (!force && (loading.value || loaded.value)) return;
  const requestId = ++linksRequestId;
  const orderId = props.orderId;
  loading.value = true;
  error.value = '';
  try {
    const response = await ManagerEquipmentLinksService.listManagerOrderEquipmentLinks(orderId);
    if (requestId !== linksRequestId || props.orderId !== orderId) return;
    links.value = response.items || [];
    loaded.value = true;
    emitOptions();
  } catch (cause) {
    if (requestId !== linksRequestId || props.orderId !== orderId) return;
    reportError(cause, 'Не удалось загрузить оборудование заказа');
  } finally {
    if (requestId === linksRequestId) loading.value = false;
  }
};

const toggle = () => {
  expanded.value = !expanded.value;
  if (expanded.value) void loadLinks();
};

const expand = () => {
  expanded.value = true;
  return loadLinks();
};

const collapse = () => {
  expanded.value = false;
};

const createFromOrder = async () => {
  if (action.value) return;
  action.value = 'from-order';
  error.value = '';
  try {
    const result = await ManagerEquipmentService.createManagerEquipmentFromOrder(props.orderId, {
      order_role: 'sale',
      include_component_placeholders: true,
    });
    message.value = result.created_count
      ? `Создано паспортов: ${result.created_count}`
      : 'Все товары заказа уже связаны с оборудованием';
    await loadLinks(true);
    emit('reload');
  } catch (cause) {
    reportError(cause, 'Не удалось создать оборудование из заказа');
  } finally {
    action.value = '';
  }
};

const openLinkDialog = async () => {
  const customerId = props.customerId;
  if (!customerId) {
    error.value = 'Сначала выберите клиента заказа';
    return;
  }
  const requestId = ++customerEquipmentRequestId;
  showLinkDialog.value = true;
  customerEquipment.value = [];
  customerEquipmentLoading.value = true;
  error.value = '';
  try {
    const items = await listAllCustomerEquipment({
      customerId,
      customerBranchId: props.customerBranchId,
    });
    if (requestId !== customerEquipmentRequestId || !showLinkDialog.value || props.customerId !== customerId) return;
    customerEquipment.value = items;
  } catch (cause) {
    if (requestId !== customerEquipmentRequestId || !showLinkDialog.value || props.customerId !== customerId) return;
    reportError(cause, 'Не удалось загрузить оборудование клиента');
  } finally {
    if (requestId === customerEquipmentRequestId) customerEquipmentLoading.value = false;
  }
};

const closeLinkDialog = () => {
  customerEquipmentRequestId += 1;
  customerEquipmentLoading.value = false;
  showLinkDialog.value = false;
};

const openManualDialog = () => {
  error.value = '';
  message.value = '';
  showManualDialog.value = true;
};

const linkExisting = async (payload: { equipmentId: number; role: string }) => {
  if (action.value) return;
  action.value = 'link';
  error.value = '';
  try {
    await ManagerEquipmentLinksService.createManagerOrderEquipmentLink(props.orderId, {
      equipment_id: payload.equipmentId,
      role: payload.role,
    });
    showLinkDialog.value = false;
    message.value = 'Оборудование привязано к заказу';
    await loadLinks(true);
    emit('reload');
  } catch (cause) {
    reportError(cause, 'Не удалось привязать оборудование');
  } finally {
    action.value = '';
  }
};

const createManual = async (payload: {
  displayName: string;
  brand: string;
  model: string;
  serial: string;
  installedAt: string;
  role: string;
  notes: string;
}) => {
  if (action.value || !props.customerId) return;
  action.value = 'manual';
  error.value = '';
  try {
    await ManagerEquipmentService.createManagerEquipment({
      customer_id: props.customerId,
      customer_branch_id: props.customerBranchId,
      source_order_id: props.orderId,
      order_role: payload.role,
      equipment_source: 'customer_owned',
      display_name: payload.displayName.trim() || null,
      brand: payload.brand.trim() || null,
      model: payload.model.trim() || null,
      serial: payload.serial.trim() || null,
      installed_at: payload.installedAt ? `${payload.installedAt}T00:00:00` : null,
      notes: payload.notes.trim() || null,
    });
    showManualDialog.value = false;
    message.value = 'Оборудование создано и привязано';
    await loadLinks(true);
    emit('reload');
  } catch (cause) {
    reportError(cause, 'Не удалось создать оборудование');
  } finally {
    action.value = '';
  }
};

const unlink = async (link: ManagerOrderEquipmentLinkItemResponse) => {
  if (!link.link_id || action.value) return;
  if (!await confirmDialog({
    title: 'Убрать связь с оборудованием?',
    description: `«${equipmentTitle(link.equipment)}» останется в реестре оборудования.`,
    confirmText: 'Убрать связь',
    variant: 'warning',
  })) return;
  action.value = `unlink-${link.link_id}`;
  error.value = '';
  try {
    await ManagerEquipmentLinksService.deleteManagerOrderEquipmentLink(props.orderId, link.link_id);
    links.value = links.value.filter((item) => item.link_id !== link.link_id);
    message.value = 'Связь с заказом удалена';
    emitOptions();
    emit('reload');
  } catch (cause) {
    reportError(cause, 'Не удалось убрать связь');
  } finally {
    action.value = '';
  }
};

watch(() => props.orderId, () => {
  linksRequestId += 1;
  customerEquipmentRequestId += 1;
  loading.value = false;
  links.value = [];
  loaded.value = false;
  error.value = '';
  message.value = '';
  showLinkDialog.value = false;
  showManualDialog.value = false;
  customerEquipment.value = [];
  customerEquipmentLoading.value = false;
  emit('options-change', []);
  void loadLinks();
});

watch(() => [props.customerId, props.customerBranchId], () => {
  customerEquipmentRequestId += 1;
  customerEquipment.value = [];
  customerEquipmentLoading.value = false;
  if (showLinkDialog.value) {
    if (props.customerId) void openLinkDialog();
    else closeLinkDialog();
  }
});

onMounted(() => void loadLinks());

defineExpose({ expand, collapse });
</script>

<template>
  <section class="rounded-lg border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900/70">
    <div class="flex items-center gap-1 pr-2">
      <button type="button" class="flex min-w-0 flex-1 items-center gap-3 rounded-lg px-3 py-3 text-left transition hover:bg-slate-50 dark:hover:bg-slate-800/60 sm:px-4" :aria-expanded="expanded" @click="toggle">
        <Boxes class="h-5 w-5 shrink-0 text-teal-700 dark:text-teal-300" />
        <span class="min-w-0 flex-1">
          <span class="block text-sm font-semibold text-slate-900 dark:text-slate-100">Оборудование на объекте</span>
          <span class="block truncate text-xs text-slate-500 dark:text-slate-400">
            {{ count ? countLabel : 'Оборудование не привязано' }}
          </span>
        </span>
        <span v-if="count" class="inline-flex min-w-7 items-center justify-center rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">{{ count }}</span>
        <ChevronUp v-if="expanded" class="h-5 w-5 text-slate-500" />
        <ChevronDown v-else class="h-5 w-5 text-slate-500" />
      </button>
      <button v-if="!count" type="button" class="btn-mini-outline h-8 shrink-0 px-2 text-xs" :disabled="Boolean(action)" @click="openLinkDialog">Привязать</button>
    </div>

    <div v-if="expanded" class="border-t border-slate-200 px-3 pb-4 pt-3 dark:border-slate-700 sm:px-4">
      <div class="flex flex-wrap items-center gap-2">
        <button v-if="hasCatalogProducts" type="button" class="btn-mini" :disabled="Boolean(action)" @click="createFromOrder">
          <WandSparkles class="h-4 w-4" />
          {{ action === 'from-order' ? 'Создаём...' : 'Создать из товаров' }}
        </button>
        <button type="button" class="btn-mini-outline" :disabled="Boolean(action)" @click="openLinkDialog">
          <Link2 class="h-4 w-4" />
          Привязать
        </button>
        <button type="button" class="btn-mini-outline" :disabled="Boolean(action) || !customerId" @click="openManualDialog">
          <Plus class="h-4 w-4" />
          Создать вручную
        </button>
        <button v-if="loaded" type="button" class="ml-auto inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:text-teal-700 dark:border-slate-700 dark:hover:text-teal-300" :disabled="loading" title="Обновить" aria-label="Обновить" @click="loadLinks(true)">
          <RefreshCw class="h-4 w-4" :class="loading ? 'animate-spin' : ''" />
        </button>
      </div>

      <p v-if="message" class="mt-3 rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-200">{{ message }}</p>
      <p v-if="error" class="mt-3 flex items-start gap-2 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-200">
        <CircleAlert class="mt-0.5 h-4 w-4 shrink-0" />
        {{ error }}
      </p>

      <div v-if="loading && !loaded" class="flex items-center gap-2 py-6 text-sm text-slate-500">
        <LoaderCircle class="h-4 w-4 animate-spin" />
        Загружаем оборудование
      </div>
      <p v-else-if="loaded && !links.length" class="mt-3 rounded-md border border-dashed border-slate-300 px-3 py-5 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
        К заказу пока ничего не привязано.
      </p>

      <div v-else class="mt-3 space-y-2">
        <article v-for="link in links" :key="`${link.link_id || 'legacy'}-${link.equipment.id}`" class="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
          <header class="flex items-start gap-3">
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <h3 class="break-words text-sm font-semibold text-slate-900 dark:text-slate-100">{{ equipmentTitle(link.equipment) }}</h3>
                <span class="rounded-full bg-teal-50 px-2 py-0.5 text-[11px] font-semibold text-teal-700 dark:bg-teal-950/40 dark:text-teal-200">{{ roleLabel(link.role) }}</span>
              </div>
              <p v-if="link.equipment.serial" class="mt-1 text-xs text-slate-500 dark:text-slate-400">Серийный: {{ link.equipment.serial }}</p>
              <p v-if="link.equipment.branch_address || link.equipment.location_hint" class="mt-1 text-xs text-slate-500 dark:text-slate-400">{{ link.equipment.branch_address || link.equipment.location_hint }}</p>
            </div>
            <button v-if="link.link_id" type="button" class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/30" title="Убрать связь с заказом" aria-label="Убрать связь с заказом" :disabled="Boolean(action)" @click="unlink(link)">
              <Trash2 class="h-4 w-4" />
            </button>
          </header>

          <div v-if="link.equipment.components?.length" class="mt-2 space-y-1 border-t border-slate-100 pt-2 dark:border-slate-800">
            <p v-for="component in link.equipment.components" :key="component.id" class="text-xs text-slate-600 dark:text-slate-300">{{ componentTitle(component) }}</p>
          </div>

          <div class="mt-2 flex flex-wrap gap-1.5">
            <span
              v-for="coverage in link.equipment.coverages || []"
              :key="coverage.id"
              class="inline-flex items-center gap-1 rounded-full px-2 py-1 text-[11px] font-semibold"
              :class="coverageClass(coverage.time_status || 'unknown', coverage.maintenance_status || 'unknown')"
            >
              <ShieldCheck class="h-3.5 w-3.5" />
              {{ coverageLabel(coverage.coverage_type) }}: {{ coverageState(coverage.time_status || 'unknown', coverage.maintenance_status || 'unknown') }}
            </span>
            <span v-if="!(link.equipment.coverages || []).length" class="rounded-full bg-amber-50 px-2 py-1 text-[11px] font-semibold text-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
              Гарантию нужно уточнить
            </span>
          </div>
        </article>
      </div>
    </div>
  </section>

  <EquipmentLinkDialog
    :open="showLinkDialog"
    :items="customerEquipment"
    :linked-ids="linkedIds"
    :loading="customerEquipmentLoading"
    :saving="action === 'link'"
    :error="showLinkDialog ? error : ''"
    @close="closeLinkDialog"
    @confirm="linkExisting"
  />
  <EquipmentManualDialog
    :open="showManualDialog"
    :saving="action === 'manual'"
    :error="showManualDialog ? error : ''"
    @close="showManualDialog = false"
    @confirm="createManual"
  />
</template>
