import { computed, ref, watch, onMounted, onUnmounted, type Ref } from 'vue';
import { notify } from '../../services/ui-feedback';
import { equipmentWarrantySummary } from "../../components/equipment/equipmentWarrantySummary";
import { listAllCustomerEquipment } from "../../components/equipment/loadAllCustomerEquipment";
import { sanitizeEquipmentComponentPayload } from "../../components/equipment/equipment-component-permissions";
import { managerSession } from "../../services/manager-session";
import { MANAGER_CAPABILITY, hasManagerCapability } from "../../manager-capabilities";
import { ManagerEquipmentService, type EquipmentServiceEventType, type ManagerEquipmentComponentCreatePayload, type ManagerEquipmentComponentItemResponse, type ManagerEquipmentComponentUpdatePayload, type ManagerEquipmentCreatePayload, type ManagerEquipmentDetailResponse, type ManagerEquipmentItemResponse, type ManagerEquipmentServiceHistoryCreatePayload, type ManagerEquipmentServiceHistoryItemResponse, type ManagerEquipmentUpdatePayload, type ManagerEquipmentWarrantyCoverageResponse } from "../../client";
import { getApiErrorMessage } from "../../utils/api-errors";
import type { ManagerCatalogCustomerItemResponse } from '../../client';

export function useCustomerEquipmentPanel(customer: Ref<ManagerCatalogCustomerItemResponse>) {
const customerId = computed(() => customer.value.id);
type EquipmentForm = {
  customer_branch_id: number | null;
  catalog_product_id: string;
  source_order_id: string;
  equipment_type: string;
  equipment_source: string;
  display_name: string;
  brand: string;
  model: string;
  serial: string;
  inventory_number: string;
  location_hint: string;
  refrigerant_type: string;
  installed_at: string;
  commissioned_at: string;
  warranty_started_at: string;
  warranty_expires_at: string;
  warranty_terms: string;
  notes: string;
};

type MaintenanceProvider = 'mvn' | 'authorized' | 'external';

type EquipmentHistoryForm = {
  event_type: EquipmentServiceEventType;
  event_date: string;
  maintenance_provider: MaintenanceProvider;
  complaint_snapshot: string;
  diagnostic_result: string;
  repair_recommendation: string;
  refrigerant_type: string;
  refrigerant_amount: string;
  not_repairable: boolean;
  not_repairable_reason: string;
  notes: string;
};

type EquipmentHistoryPayload = ManagerEquipmentServiceHistoryCreatePayload & {
  maintenance_provider?: MaintenanceProvider | null;
};

type EquipmentComponentForm = {
  catalog_product_id: string;
  supplier_id: string;
  component_type: string;
  title: string;
  brand: string;
  model: string;
  serial: string;
  inventory_number: string;
  supplier_invoice_number: string;
  supplier_invoice_date: string;
  notes: string;
};

const error = ref('');

const canManagePlatform = computed(() => hasManagerCapability(
  managerSession.auth.value,
  MANAGER_CAPABILITY.platformManage,
));

const EQUIPMENT_EVENT_OPTIONS: Array<{ value: EquipmentServiceEventType; label: string }> = [
  { value: 'diagnostic', label: 'Диагностика' },
  { value: 'repair', label: 'Ремонт' },
  { value: 'maintenance', label: 'Обслуживание' },
  { value: 'refrigerant_charge', label: 'Заправка хладагентом' },
  { value: 'leak', label: 'Утечка' },
  { value: 'recommendation', label: 'Рекомендация' },
  { value: 'not_repairable', label: 'Не ремонтируется' },
  { value: 'other', label: 'Другое' },
];

const EQUIPMENT_SOURCE_OPTIONS = [
  { value: 'unknown', label: 'Не указано' },
  { value: 'sold_by_us', label: 'Продано нами' },
  { value: 'installed_by_us', label: 'Установлено нами' },
  { value: 'customer_owned', label: 'Оборудование клиента' },
];

const EQUIPMENT_COMPONENT_OPTIONS = [
  { value: 'indoor_unit', label: 'Внутренний блок' },
  { value: 'outdoor_unit', label: 'Наружный блок' },
  { value: 'system', label: 'Система целиком' },
  { value: 'remote', label: 'Пульт' },
  { value: 'wifi_module', label: 'Wi-Fi модуль' },
  { value: 'other', label: 'Другое' },
];

const formatDate = (iso?: string | null) => {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('ru-RU');
};

const formatDateOnly = (iso?: string | null) => {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('ru-RU');
};

const toInputDate = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const emptyEquipmentForm = (): EquipmentForm => ({
  customer_branch_id: null,
  catalog_product_id: '',
  source_order_id: '',
  equipment_type: 'hvac',
  equipment_source: 'unknown',
  display_name: '',
  brand: '',
  model: '',
  serial: '',
  inventory_number: '',
  location_hint: '',
  refrigerant_type: '',
  installed_at: '',
  commissioned_at: '',
  warranty_started_at: '',
  warranty_expires_at: '',
  warranty_terms: '',
  notes: '',
});

const emptyHistoryForm = (): EquipmentHistoryForm => ({
  event_type: 'diagnostic',
  event_date: toInputDate(new Date()),
  maintenance_provider: 'mvn',
  complaint_snapshot: '',
  diagnostic_result: '',
  repair_recommendation: '',
  refrigerant_type: '',
  refrigerant_amount: '',
  not_repairable: false,
  not_repairable_reason: '',
  notes: '',
});

const emptyComponentForm = (): EquipmentComponentForm => ({
  catalog_product_id: '',
  supplier_id: '',
  component_type: 'indoor_unit',
  title: '',
  brand: '',
  model: '',
  serial: '',
  inventory_number: '',
  supplier_invoice_number: '',
  supplier_invoice_date: '',
  notes: '',
});

const equipment = ref<ManagerEquipmentItemResponse[]>([]);

const equipmentLoading = ref(false);

const equipmentSaving = ref(false);

const equipmentActionId = ref<number | null>(null);

const componentSaving = ref(false);

const componentActionId = ref<number | null>(null);

const equipmentError = ref('');

const includeArchivedEquipment = ref(true);

const showEquipmentForm = ref(false);

const editingEquipmentId = ref<number | null>(null);

const equipmentForm = ref<EquipmentForm>(emptyEquipmentForm());

const selectedEquipmentId = ref<number | null>(null);

const selectedEquipmentDetail = ref<ManagerEquipmentDetailResponse | null>(null);

const equipmentCoverageCache = ref<Record<number, ManagerEquipmentWarrantyCoverageResponse[]>>({});

const showComponentForm = ref(false);

const editingComponentId = ref<number | null>(null);

const componentForm = ref<EquipmentComponentForm>(emptyComponentForm());

const equipmentHistoryLoading = ref(false);

const historySaving = ref(false);

const showHistoryForm = ref(false);

const historyForm = ref<EquipmentHistoryForm>(emptyHistoryForm());

let equipmentDetailRequestId = 0;

let equipmentListRequestId = 0;

const setToast = notify;

const trimOrNull = (value: string) => {
  const normalized = value.trim();
  return normalized || null;
};

const equipmentBranchLabel = (branchId?: number | null) => {
  if (!branchId) return 'Без филиала';
  const branch = customer.value?.branches?.find((item) => item.id === branchId);
  return branch?.name || branch?.delivery_address || `Филиал #${branchId}`;
};

const equipmentEventLabel = (value?: EquipmentServiceEventType | null) => (
  EQUIPMENT_EVENT_OPTIONS.find((option) => option.value === value)?.label || 'Другое'
);

const equipmentSourceLabel = (value?: string | null) => (
  EQUIPMENT_SOURCE_OPTIONS.find((option) => option.value === value)?.label || 'Не указано'
);

const componentTypeLabel = (value?: string | null) => (
  EQUIPMENT_COMPONENT_OPTIONS.find((option) => option.value === value)?.label || 'Другое'
);

const warrantyStatusClass = (value?: string | null) => {
  const classes: Record<string, string> = {
    active: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
    attention: 'bg-red-50 text-red-700 dark:bg-red-500/15 dark:text-red-300',
    expired: 'bg-red-50 text-red-700 dark:bg-red-500/15 dark:text-red-300',
    scheduled: 'bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300',
    none: 'bg-amber-50 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300',
    unknown: 'bg-amber-50 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300',
  };
  return classes[value || 'unknown'] || classes.unknown;
};

const toDateInputValue = (iso?: string | null) => {
  if (!iso) return '';
  return iso.slice(0, 10);
};

const parseOptionalNumber = (value: string) => {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
};

const toDateTimePayload = (value: string) => (value ? `${value}T00:00:00` : null);

const equipmentTitle = (item?: Pick<ManagerEquipmentItemResponse, 'display_name' | 'brand' | 'model' | 'serial' | 'inventory_number'> | null) => {
  if (!item) return 'Оборудование';
  const name = item.display_name?.trim();
  if (name) return name;
  const parts = [item.brand, item.model, item.serial || item.inventory_number].map((value) => value?.trim()).filter(Boolean);
  return parts.join(' ') || 'Оборудование';
};

const equipmentFormTitle = computed(() => {
  if (!editingEquipmentId.value) return 'Новое оборудование';
  return `Редактирование: ${equipmentTitle(equipment.value.find((item) => item.id === editingEquipmentId.value))}`;
});

const equipmentWarrantyView = (item: Pick<ManagerEquipmentItemResponse, 'id' | 'warranty_status' | 'warranty_expires_at' | 'warranty_mode'>) => (
  equipmentWarrantySummary(item, equipmentCoverageCache.value[item.id])
);

const equipmentSubtitle = (item: ManagerEquipmentItemResponse | ManagerEquipmentDetailResponse) => {
  const parts = [
    item.equipment_type || 'hvac',
    item.brand,
    item.model,
    item.serial ? `SN ${item.serial}` : '',
    item.inventory_number ? `Инв. ${item.inventory_number}` : '',
    item.location_hint,
    item.refrigerant_type,
  ].map((value) => value?.trim()).filter(Boolean);
  return parts.join(' · ') || 'Паспортные данные не заполнены';
};

const equipmentFormPayload = (): ManagerEquipmentCreatePayload | ManagerEquipmentUpdatePayload => ({
  customer_branch_id: equipmentForm.value.customer_branch_id,
  catalog_product_id: parseOptionalNumber(equipmentForm.value.catalog_product_id),
  source_order_id: parseOptionalNumber(equipmentForm.value.source_order_id),
  equipment_type: trimOrNull(equipmentForm.value.equipment_type) || 'hvac',
  equipment_source: trimOrNull(equipmentForm.value.equipment_source) || 'unknown',
  display_name: trimOrNull(equipmentForm.value.display_name),
  brand: trimOrNull(equipmentForm.value.brand),
  model: trimOrNull(equipmentForm.value.model),
  serial: trimOrNull(equipmentForm.value.serial),
  inventory_number: trimOrNull(equipmentForm.value.inventory_number),
  location_hint: trimOrNull(equipmentForm.value.location_hint),
  refrigerant_type: trimOrNull(equipmentForm.value.refrigerant_type),
  installed_at: toDateTimePayload(equipmentForm.value.installed_at),
  commissioned_at: toDateTimePayload(equipmentForm.value.commissioned_at),
  warranty_started_at: toDateTimePayload(equipmentForm.value.warranty_started_at),
  warranty_expires_at: toDateTimePayload(equipmentForm.value.warranty_expires_at),
  warranty_terms: trimOrNull(equipmentForm.value.warranty_terms),
  notes: trimOrNull(equipmentForm.value.notes),
});

const componentPayload = (): ManagerEquipmentComponentCreatePayload | ManagerEquipmentComponentUpdatePayload => {
  const payload: ManagerEquipmentComponentCreatePayload | ManagerEquipmentComponentUpdatePayload = {
    catalog_product_id: parseOptionalNumber(componentForm.value.catalog_product_id),
    supplier_id: parseOptionalNumber(componentForm.value.supplier_id),
    component_type: trimOrNull(componentForm.value.component_type) || 'other',
    title: trimOrNull(componentForm.value.title),
    brand: trimOrNull(componentForm.value.brand),
    model: trimOrNull(componentForm.value.model),
    serial: trimOrNull(componentForm.value.serial),
    inventory_number: trimOrNull(componentForm.value.inventory_number),
    supplier_invoice_number: trimOrNull(componentForm.value.supplier_invoice_number),
    supplier_invoice_date: toDateTimePayload(componentForm.value.supplier_invoice_date),
    notes: trimOrNull(componentForm.value.notes),
  };
  return sanitizeEquipmentComponentPayload(payload, canManagePlatform.value);
};

const historyPayload = (): EquipmentHistoryPayload => ({
  event_type: historyForm.value.event_type,
  event_date: historyForm.value.event_date ? `${historyForm.value.event_date}T00:00:00` : null,
  maintenance_provider: historyForm.value.event_type === 'maintenance' ? historyForm.value.maintenance_provider : null,
  complaint_snapshot: trimOrNull(historyForm.value.complaint_snapshot),
  diagnostic_result: trimOrNull(historyForm.value.diagnostic_result),
  repair_recommendation: trimOrNull(historyForm.value.repair_recommendation),
  refrigerant_type: trimOrNull(historyForm.value.refrigerant_type),
  refrigerant_amount: trimOrNull(historyForm.value.refrigerant_amount),
  not_repairable: historyForm.value.not_repairable,
  not_repairable_reason: trimOrNull(historyForm.value.not_repairable_reason),
  notes: trimOrNull(historyForm.value.notes),
});

const historyLine = (item: ManagerEquipmentServiceHistoryItemResponse) => {
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

const componentTitle = (item: ManagerEquipmentComponentItemResponse) => {
  const title = item.title?.trim();
  if (title) return title;
  const parts = [item.brand, item.model, item.serial ? `SN ${item.serial}` : ''].map((value) => value?.trim()).filter(Boolean);
  return parts.join(' ') || componentTypeLabel(item.component_type);
};

const componentLine = (item: ManagerEquipmentComponentItemResponse) => {
  const parts = [
    componentTypeLabel(item.component_type),
    item.brand,
    item.model,
    item.serial ? `SN ${item.serial}` : '',
    item.inventory_number ? `Инв. ${item.inventory_number}` : '',
    item.catalog_product_id ? `Товар #${item.catalog_product_id}` : '',
    canManagePlatform.value && item.supplier_id ? `Поставщик #${item.supplier_id}` : '',
    canManagePlatform.value && item.supplier_invoice_number ? `Накладная ${item.supplier_invoice_number}` : '',
    canManagePlatform.value && item.supplier_invoice_date ? formatDateOnly(item.supplier_invoice_date) : '',
  ].map((value) => value?.trim()).filter(Boolean);
  return parts.join(' · ') || 'Паспортные данные не заполнены';
};

const loadEquipmentDetail = async (equipmentId: number) => {
  const requestId = ++equipmentDetailRequestId;
  equipmentHistoryLoading.value = true;
  equipmentError.value = '';
  try {
    const detail = await ManagerEquipmentService.getManagerEquipment(equipmentId, 10);
    if (requestId !== equipmentDetailRequestId || selectedEquipmentId.value !== equipmentId) return;
    selectedEquipmentDetail.value = detail;
    equipmentCoverageCache.value = {
      ...equipmentCoverageCache.value,
      [equipmentId]: detail.coverages || [],
    };
  } catch (e) {
    if (requestId !== equipmentDetailRequestId || selectedEquipmentId.value !== equipmentId) return;
    console.error('Failed to load equipment detail', e);
    equipmentError.value = `Не удалось загрузить данные оборудования: ${getApiErrorMessage(e)}`;
    selectedEquipmentDetail.value = null;
  } finally {
    if (requestId === equipmentDetailRequestId) equipmentHistoryLoading.value = false;
  }
};

const updateSelectedCoverage = (updated: ManagerEquipmentWarrantyCoverageResponse) => {
  if (!selectedEquipmentDetail.value) return;
  const coverages = selectedEquipmentDetail.value.coverages || [];
  selectedEquipmentDetail.value = {
    ...selectedEquipmentDetail.value,
    coverages: coverages.map((coverage) => coverage.id === updated.id ? updated : coverage),
  };
  equipmentCoverageCache.value = {
    ...equipmentCoverageCache.value,
    [selectedEquipmentDetail.value.id]: selectedEquipmentDetail.value.coverages || [],
  };
};

const selectEquipment = async (equipmentId: number) => {
  selectedEquipmentId.value = equipmentId;
  selectedEquipmentDetail.value = null;
  showHistoryForm.value = false;
  showComponentForm.value = false;
  editingComponentId.value = null;
  historyForm.value = emptyHistoryForm();
  componentForm.value = emptyComponentForm();
  await loadEquipmentDetail(equipmentId);
};

const loadCustomerEquipment = async () => {
  if (!customerId.value) return;
  const requestId = ++equipmentListRequestId;
  const targetCustomerId = customerId.value;
  equipmentLoading.value = true;
  equipmentError.value = '';
  try {
    const items = await listAllCustomerEquipment({
      customerId: targetCustomerId,
      includeArchived: includeArchivedEquipment.value,
    });
    if (requestId !== equipmentListRequestId || customerId.value !== targetCustomerId) return;
    equipment.value = items;
    if (selectedEquipmentId.value && !equipment.value.some((item) => item.id === selectedEquipmentId.value)) {
      equipmentDetailRequestId += 1;
      selectedEquipmentId.value = null;
      selectedEquipmentDetail.value = null;
    }
    if (!selectedEquipmentId.value && equipment.value.length) {
      await selectEquipment(equipment.value[0]!.id);
    } else if (selectedEquipmentId.value) {
      await loadEquipmentDetail(selectedEquipmentId.value);
    }
  } catch (e) {
    if (requestId !== equipmentListRequestId || customerId.value !== targetCustomerId) return;
    console.error('Failed to load customer equipment', e);
    equipmentError.value = `Не удалось загрузить оборудование: ${getApiErrorMessage(e)}`;
  } finally {
    if (requestId === equipmentListRequestId) equipmentLoading.value = false;
  }
};

const openEquipmentCreateForm = () => {
  equipmentForm.value = emptyEquipmentForm();
  editingEquipmentId.value = null;
  showEquipmentForm.value = true;
};

const openEquipmentEditForm = (item: ManagerEquipmentItemResponse) => {
  if (selectedEquipmentId.value !== item.id) void selectEquipment(item.id);
  equipmentForm.value = {
    customer_branch_id: item.customer_branch_id ?? null,
    catalog_product_id: item.catalog_product_id ? String(item.catalog_product_id) : '',
    source_order_id: item.source_order_id ? String(item.source_order_id) : '',
    equipment_type: item.equipment_type || 'hvac',
    equipment_source: item.equipment_source || 'unknown',
    display_name: item.display_name || '',
    brand: item.brand || '',
    model: item.model || '',
    serial: item.serial || '',
    inventory_number: item.inventory_number || '',
    location_hint: item.location_hint || '',
    refrigerant_type: item.refrigerant_type || '',
    installed_at: toDateInputValue(item.installed_at),
    commissioned_at: toDateInputValue(item.commissioned_at),
    warranty_started_at: toDateInputValue(item.warranty_started_at),
    warranty_expires_at: toDateInputValue(item.warranty_expires_at),
    warranty_terms: item.warranty_terms || '',
    notes: item.notes || '',
  };
  editingEquipmentId.value = item.id;
  showEquipmentForm.value = true;
};

const saveEquipment = async () => {
  if (!customerId.value || equipmentSaving.value) return;
  const payload = equipmentFormPayload();
  if (!payload.display_name && !payload.brand && !payload.model && !payload.serial && !payload.inventory_number) {
    equipmentError.value = 'Укажите название, бренд, модель, серийный или инвентарный номер';
    return;
  }
  equipmentSaving.value = true;
  equipmentError.value = '';
  try {
    if (editingEquipmentId.value) {
      const updated = await ManagerEquipmentService.patchManagerEquipment(editingEquipmentId.value, payload);
      selectedEquipmentId.value = updated.id;
      setToast('Оборудование обновлено');
    } else {
      const created = await ManagerEquipmentService.createManagerEquipment({
        ...(payload as ManagerEquipmentCreatePayload),
        customer_id: customerId.value,
      });
      selectedEquipmentId.value = created.id;
      setToast('Оборудование создано');
    }
    showEquipmentForm.value = false;
    editingEquipmentId.value = null;
    await loadCustomerEquipment();
  } catch (e) {
    equipmentError.value = `Не удалось сохранить оборудование: ${getApiErrorMessage(e)}`;
  } finally {
    equipmentSaving.value = false;
  }
};

const toggleEquipmentArchive = async (item: ManagerEquipmentItemResponse) => {
  if (equipmentActionId.value) return;
  equipmentActionId.value = item.id;
  equipmentError.value = '';
  try {
    await ManagerEquipmentService.patchManagerEquipment(item.id, { is_archived: !item.is_archived });
    setToast(item.is_archived ? 'Оборудование возвращено из архива' : 'Оборудование архивировано');
    await loadCustomerEquipment();
  } catch (e) {
    equipmentError.value = `Не удалось изменить архив: ${getApiErrorMessage(e)}`;
  } finally {
    equipmentActionId.value = null;
  }
};

const openComponentCreateForm = () => {
  componentForm.value = {
    ...emptyComponentForm(),
    brand: selectedEquipmentDetail.value?.brand || '',
  };
  editingComponentId.value = null;
  showComponentForm.value = true;
};

const openComponentEditForm = (item: ManagerEquipmentComponentItemResponse) => {
  componentForm.value = {
    catalog_product_id: item.catalog_product_id ? String(item.catalog_product_id) : '',
    supplier_id: item.supplier_id ? String(item.supplier_id) : '',
    component_type: item.component_type || 'other',
    title: item.title || '',
    brand: item.brand || '',
    model: item.model || '',
    serial: item.serial || '',
    inventory_number: item.inventory_number || '',
    supplier_invoice_number: item.supplier_invoice_number || '',
    supplier_invoice_date: toDateInputValue(item.supplier_invoice_date),
    notes: item.notes || '',
  };
  editingComponentId.value = item.id;
  showComponentForm.value = true;
};

const saveEquipmentComponent = async () => {
  if (!selectedEquipmentId.value || componentSaving.value) return;
  const equipmentId = selectedEquipmentId.value;
  const componentId = editingComponentId.value;
  const payload = componentPayload();
  if (!payload.title && !payload.brand && !payload.model && !payload.serial && !payload.inventory_number) {
    equipmentError.value = 'Укажите название, бренд, модель, серийный или инвентарный номер компонента';
    return;
  }
  componentSaving.value = true;
  equipmentError.value = '';
  try {
    if (componentId) {
      await ManagerEquipmentService.patchManagerEquipmentComponent(
        equipmentId,
        componentId,
        payload as ManagerEquipmentComponentUpdatePayload,
      );
      setToast('Компонент обновлен');
    } else {
      await ManagerEquipmentService.createManagerEquipmentComponent(
        equipmentId,
        payload as ManagerEquipmentComponentCreatePayload,
      );
      setToast('Компонент добавлен');
    }
    showComponentForm.value = false;
    editingComponentId.value = null;
    componentForm.value = emptyComponentForm();
    if (selectedEquipmentId.value === equipmentId) await loadEquipmentDetail(equipmentId);
  } catch (e) {
    equipmentError.value = `Не удалось сохранить компонент: ${getApiErrorMessage(e)}`;
  } finally {
    componentSaving.value = false;
  }
};

const toggleEquipmentComponentArchive = async (item: ManagerEquipmentComponentItemResponse) => {
  if (!selectedEquipmentId.value || componentActionId.value) return;
  const equipmentId = selectedEquipmentId.value;
  componentActionId.value = item.id;
  equipmentError.value = '';
  try {
    await ManagerEquipmentService.patchManagerEquipmentComponent(
      equipmentId,
      item.id,
      { is_archived: !item.is_archived },
    );
    setToast(item.is_archived ? 'Компонент возвращен из архива' : 'Компонент архивирован');
    if (selectedEquipmentId.value === equipmentId) await loadEquipmentDetail(equipmentId);
  } catch (e) {
    equipmentError.value = `Не удалось изменить компонент: ${getApiErrorMessage(e)}`;
  } finally {
    componentActionId.value = null;
  }
};

const openHistoryCreateForm = () => {
  historyForm.value = {
    ...emptyHistoryForm(),
    refrigerant_type: selectedEquipmentDetail.value?.refrigerant_type || '',
  };
  showHistoryForm.value = true;
};

const createEquipmentHistory = async () => {
  if (!selectedEquipmentId.value || historySaving.value) return;
  const equipmentId = selectedEquipmentId.value;
  historySaving.value = true;
  equipmentError.value = '';
  try {
    await ManagerEquipmentService.createManagerEquipmentHistory(equipmentId, historyPayload());
    setToast('Событие истории добавлено');
    showHistoryForm.value = false;
    historyForm.value = emptyHistoryForm();
    if (selectedEquipmentId.value === equipmentId) await loadEquipmentDetail(equipmentId);
  } catch (e) {
    equipmentError.value = `Не удалось добавить событие: ${getApiErrorMessage(e)}`;
  } finally {
    historySaving.value = false;
  }
};
watch(includeArchivedEquipment, () => { void loadCustomerEquipment(); });
onMounted(() => { void loadCustomerEquipment(); });
onUnmounted(() => { equipmentListRequestId += 1; equipmentDetailRequestId += 1; });
return { equipment, includeArchivedEquipment, equipmentLoading, loadCustomerEquipment, openEquipmentCreateForm, equipmentError, showEquipmentForm, saveEquipment, equipmentFormTitle, equipmentForm, EQUIPMENT_SOURCE_OPTIONS, equipmentSaving, editingEquipmentId, selectedEquipmentId, selectEquipment, equipmentTitle, warrantyStatusClass, equipmentWarrantyView, equipmentSubtitle, equipmentBranchLabel, equipmentSourceLabel, formatDateOnly, openEquipmentEditForm, equipmentActionId, toggleEquipmentArchive, equipmentHistoryLoading, selectedEquipmentDetail, openHistoryCreateForm, updateSelectedCoverage, openComponentCreateForm, showComponentForm, saveEquipmentComponent, componentForm, EQUIPMENT_COMPONENT_OPTIONS, canManagePlatform, componentSaving, editingComponentId, componentTypeLabel, componentTitle, componentLine, openComponentEditForm, componentActionId, toggleEquipmentComponentArchive, showHistoryForm, createEquipmentHistory, historyForm, EQUIPMENT_EVENT_OPTIONS, historySaving, equipmentEventLabel, formatDate, historyLine, loadEquipmentDetail, error, emptyEquipmentForm, equipmentFormPayload, setToast, emptyHistoryForm, emptyComponentForm, equipmentCoverageCache, toDateInputValue, componentPayload, historyPayload, parseOptionalNumber, trimOrNull, toDateTimePayload, toInputDate };
}
