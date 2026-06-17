<script setup lang="ts">
import { useDebounceFn } from '@vueuse/core';
import { computed, onMounted, ref, watch } from 'vue';
import { ArrowLeft, Building2, Mail, Phone, Plus, ReceiptText, Save, UserRound, X } from 'lucide-vue-next';
import CreateOrderModal from '../components/CreateOrderModal.vue';
import { api } from '../api';
import {
  ManagerContractsService,
  ManagerDocsService,
  ManagerEquipmentService,
  ManagerSettingsService,
  ManagerService,
  type AddressSuggestionItem,
  type DocumentTemplateItem,
  type EquipmentServiceEventType,
  type ManagerCatalogCustomerItemResponse,
  type ManagerCustomerContractItemResponse,
  type ManagerCustomerDocumentItem,
  type ManagerEquipmentComponentCreatePayload,
  type ManagerEquipmentComponentItemResponse,
  type ManagerEquipmentComponentUpdatePayload,
  type ManagerEquipmentCreatePayload,
  type ManagerEquipmentDetailResponse,
  type ManagerEquipmentItemResponse,
  type ManagerEquipmentServiceHistoryCreatePayload,
  type ManagerEquipmentServiceHistoryItemResponse,
  type ManagerEquipmentUpdatePayload,
} from '../client';
import { useBelarusPhoneMask } from '../composables/useBelarusPhoneMask';
import { useB2BLookup } from '../composables/useB2BLookup';
import { dispatchCustomerUpdated } from '../utils/customer-events';
import { getApiErrorMessage, parseApiFieldErrors } from '../utils/api-errors';
import { normalizeIban, normalizeUnp } from '../utils/legal-requisites';
import { normalizePhoneForApi } from '../utils/phone';
import {
  normalizeEmail,
  validateOptionalBelarusPhone,
  validateOptionalByIban,
  validateOptionalByUnp,
  validateOptionalEmail,
} from '../utils/validation';

type CustomerForm = {
  name: string;
  phone: string;
  email: string;
  type: 'individual' | 'company';
  inn: string;
  kpp: string;
  full_legal_name: string;
  legal_address: string;
  actual_address: string;
  bank_name: string;
  bic: string;
  iban: string;
  signer_position: string;
  signer_name: string;
  acting_basis: string;
};

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

type EquipmentHistoryForm = {
  event_type: EquipmentServiceEventType;
  event_date: string;
  complaint_snapshot: string;
  diagnostic_result: string;
  repair_recommendation: string;
  refrigerant_type: string;
  refrigerant_amount: string;
  not_repairable: boolean;
  not_repairable_reason: string;
  notes: string;
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

const customer = ref<ManagerCatalogCustomerItemResponse | null>(null);
const loading = ref(false);
const saving = ref(false);
const error = ref('');
const saveError = ref('');
const success = ref('');
const toast = ref('');
const editMode = ref(false);
const showCreateOrder = ref(false);
const serverErrors = ref<Record<string, string>>({});

const documents = ref<ManagerCustomerDocumentItem[]>([]);
const docsLoading = ref(false);
const contracts = ref<ManagerCustomerContractItemResponse[]>([]);
const contractsLoading = ref(false);
const contractSaving = ref(false);
const contractUploadSaving = ref(false);
const showContractForm = ref(false);
const showContractUploadForm = ref(false);
type DocumentRoleType = 'seller_buyer' | 'executor_customer' | 'contractor_customer';
const DOCUMENT_ROLE_OPTIONS: Array<{ value: DocumentRoleType; label: string }> = [
  { value: 'seller_buyer', label: 'Продавец / Покупатель' },
  { value: 'executor_customer', label: 'Исполнитель / Заказчик' },
  { value: 'contractor_customer', label: 'Подрядчик / Заказчик' },
];
const contractTemplates = ref<DocumentTemplateItem[]>([]);
const openContractTemplates = computed(() => contractTemplates.value.filter((template) => template.is_open_contract));
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

const normalizeRoleType = (value: unknown): DocumentRoleType => {
  const raw = String(value || '').trim();
  if (raw === 'executor_customer' || raw === 'contractor_customer') return raw;
  return 'seller_buyer';
};

const getRoleLabel = (value?: string | null) => (
  DOCUMENT_ROLE_OPTIONS.find((option) => option.value === normalizeRoleType(value))?.label || 'Продавец / Покупатель'
);

const getTemplateRoleLabel = (templateId?: string | null) => {
  const template = contractTemplates.value.find((item) => item.id === templateId);
  return getRoleLabel(template?.document_role_type);
};

const phoneError = ref('');
const emailError = ref('');
const innError = ref('');
const ibanError = ref('');
const phoneInputRef = ref<HTMLInputElement | null>(null);
type CustomerAddressField = 'legal_address' | 'actual_address';
const customerAddressSuggestions = ref<AddressSuggestionItem[]>([]);
const activeCustomerAddressField = ref<CustomerAddressField | null>(null);
const customerAddressLookupLoading = ref(false);
let customerAddressRequestId = 0;

const form = ref<CustomerForm>({
  name: '',
  phone: '',
  email: '',
  type: 'individual',
  inn: '',
  kpp: '',
  full_legal_name: '',
  legal_address: '',
  actual_address: '',
  bank_name: '',
  bic: '',
  iban: '',
  signer_position: '',
  signer_name: '',
  acting_basis: '',
});

const phoneModel = computed({
  get: () => form.value.phone,
  set: (value: string) => {
    form.value.phone = value;
  },
});

const phoneMask = useBelarusPhoneMask(phoneInputRef, phoneModel);

const { lookupCompany, lookupBank, isEgrLoading, isBankLoading } = useB2BLookup();

const customerId = computed(() => {
  const raw = new URLSearchParams(window.location.search).get('customerId');
  if (!raw) return null;
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? value : null;
});

const returnTo = computed(() => new URLSearchParams(window.location.search).get('returnTo') || '');
const shouldOpenContractForm = computed(() => new URLSearchParams(window.location.search).get('openContract') === '1');
const backLabel = computed(() => (returnTo.value ? 'Назад' : 'К списку клиентов'));

const formatDate = (iso?: string | null) => {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('ru-RU');
};

const formatDateOnly = (iso?: string | null) => {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('ru-RU');
};

const toInputDate = (date: Date) => date.toISOString().slice(0, 10);

const buildDefaultContractForm = () => {
  const start = new Date();
  const end = new Date(start);
  end.setFullYear(end.getFullYear() + 1);
  const defaultTemplate = openContractTemplates.value[0];
  return {
    number: '',
    contract_date: toInputDate(start),
    valid_until: toInputDate(end),
    template_id: defaultTemplate?.id || '',
  };
};

const contractForm = ref(buildDefaultContractForm());
const contractUploadForm = ref({
  number: '',
  contract_date: buildDefaultContractForm().contract_date,
  valid_until: buildDefaultContractForm().valid_until,
  template_id: buildDefaultContractForm().template_id,
  file: null as File | null,
});

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
const showComponentForm = ref(false);
const editingComponentId = ref<number | null>(null);
const componentForm = ref<EquipmentComponentForm>(emptyComponentForm());
const equipmentHistoryLoading = ref(false);
const historySaving = ref(false);
const showHistoryForm = ref(false);
const historyForm = ref<EquipmentHistoryForm>(emptyHistoryForm());

const setToast = (message: string) => {
  toast.value = message;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 3500);
};

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

const warrantyStatusLabel = (value?: string | null) => {
  const labels: Record<string, string> = {
    active: 'Гарантия действует',
    expired: 'Гарантия истекла',
    scheduled: 'Гарантия начнется',
    none: 'Без гарантии',
    unknown: 'Гарантия не указана',
  };
  return labels[value || 'unknown'] || 'Гарантия не указана';
};

const warrantyStatusClass = (value?: string | null) => {
  const classes: Record<string, string> = {
    active: 'bg-emerald-500/15 text-emerald-400',
    expired: 'bg-red-500/15 text-red-400',
    scheduled: 'bg-sky-500/15 text-sky-400',
    none: 'bg-slate-500/20 text-slate-400',
    unknown: 'bg-amber-500/15 text-amber-400',
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

const componentPayload = (): ManagerEquipmentComponentCreatePayload | ManagerEquipmentComponentUpdatePayload => ({
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
});

const historyPayload = (): ManagerEquipmentServiceHistoryCreatePayload => ({
  event_type: historyForm.value.event_type,
  event_date: historyForm.value.event_date ? `${historyForm.value.event_date}T00:00:00` : null,
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
    item.supplier_id ? `Поставщик #${item.supplier_id}` : '',
    item.supplier_invoice_number ? `Накладная ${item.supplier_invoice_number}` : '',
    item.supplier_invoice_date ? formatDateOnly(item.supplier_invoice_date) : '',
  ].map((value) => value?.trim()).filter(Boolean);
  return parts.join(' · ') || 'Паспортные данные не заполнены';
};

const toForm = (item: ManagerCatalogCustomerItemResponse): CustomerForm => ({
  name: item.name || '',
  phone: item.phone || '',
  email: item.email || '',
  type: item.type === 'company' ? 'company' : 'individual',
  inn: item.inn || '',
  kpp: item.kpp || '',
  full_legal_name: item.full_legal_name || '',
  legal_address: item.legal_address || '',
  actual_address: item.actual_address || '',
  bank_name: item.bank_name || '',
  bic: item.bic || '',
  iban: item.iban || '',
  signer_position: item.signer_position || '',
  signer_name: item.signer_name || '',
  acting_basis: item.acting_basis || '',
});

const currentForm = computed(() => form.value);

const formDiff = computed<Record<keyof CustomerForm, boolean>>(() => {
  const source = customer.value;
  if (!source) return {} as Record<keyof CustomerForm, boolean>;
  const original = toForm(source);
  const entries = Object.keys(original) as (keyof CustomerForm)[];
  const diff: Partial<Record<keyof CustomerForm, boolean>> = {};
  for (const key of entries) {
    diff[key] = (original[key] || '').toString().trim() !== (currentForm.value[key] || '').toString().trim();
  }
  return diff as Record<keyof CustomerForm, boolean>;
});

const hasChanges = computed(() => Object.values(formDiff.value).some(Boolean));
const isCompany = computed(() => currentForm.value.type === 'company');

const fieldClass = (key: keyof CustomerForm) => ({
  'field-input': true,
  changed: formDiff.value[key],
  'border-red-500 focus:outline-red-400':
    Boolean(serverErrors.value[key]) ||
    (key === 'phone' && Boolean(phoneError.value)) ||
    (key === 'email' && Boolean(emailError.value)) ||
    (key === 'inn' && Boolean(innError.value)) ||
    (key === 'iban' && Boolean(ibanError.value)),
});

const fetchCustomerAddressSuggestions = async (field: CustomerAddressField, query: string) => {
  const requestId = ++customerAddressRequestId;
  if (!query || query.length < 3) {
    customerAddressSuggestions.value = [];
    return;
  }
  customerAddressLookupLoading.value = true;
  try {
    const res = await ManagerSettingsService.suggestAddress(query);
    if (requestId === customerAddressRequestId && activeCustomerAddressField.value === field) {
      customerAddressSuggestions.value = res.items || [];
    }
  } catch (err) {
    console.warn('Failed to fetch address suggestions', err);
  } finally {
    if (requestId === customerAddressRequestId) {
      customerAddressLookupLoading.value = false;
    }
  }
};

const debouncedFetchCustomerAddressSuggestions = useDebounceFn(fetchCustomerAddressSuggestions, 400);

const onCustomerAddressInput = (field: CustomerAddressField) => {
  activeCustomerAddressField.value = field;
  debouncedFetchCustomerAddressSuggestions(field, form.value[field]);
};

const selectCustomerAddressSuggestion = (field: CustomerAddressField, item: AddressSuggestionItem) => {
  form.value[field] = item.value || item.title || '';
  activeCustomerAddressField.value = null;
  customerAddressSuggestions.value = [];
};

const hideCustomerAddressSuggestions = () => {
  window.setTimeout(() => {
    activeCustomerAddressField.value = null;
  }, 200);
};

const clearFieldErrors = () => {
  serverErrors.value = {};
  phoneError.value = '';
  emailError.value = '';
  innError.value = '';
  ibanError.value = '';
};

const resetFormFromCustomer = () => {
  if (!customer.value) return;
  form.value = toForm(customer.value);
  clearFieldErrors();
};

const loadCustomer = async () => {
  if (!customerId.value) {
    error.value = 'Не передан customerId';
    customer.value = null;
    return;
  }
  loading.value = true;
  error.value = '';
  saveError.value = '';
  success.value = '';
  try {
    customer.value = await api.getManagerCustomerDetail(customerId.value);
    resetFormFromCustomer();
    if (shouldOpenContractForm.value && customer.value?.type === 'company') {
      openContractForm();
    }
  } catch (e) {
    console.error(e);
    error.value = `Не удалось загрузить карточку клиента: ${getApiErrorMessage(e)}`;
    customer.value = null;
  } finally {
    loading.value = false;
  }
};

const loadCustomerDocs = async () => {
  if (!customerId.value) return;
  docsLoading.value = true;
  try {
    const res = await ManagerService.getManagerCustomerDocs(customerId.value);
    documents.value = res.items;
  } catch (e) {
    console.error('Failed to load customer docs', e);
  } finally {
    docsLoading.value = false;
  }
};

const loadCustomerContracts = async () => {
  if (!customerId.value) return;
  contractsLoading.value = true;
  try {
    const res = await ManagerContractsService.getManagerCustomerContracts(customerId.value);
    contracts.value = res.items;
  } catch (e) {
    console.error('Failed to load customer contracts', e);
  } finally {
    contractsLoading.value = false;
  }
};

const loadEquipmentDetail = async (equipmentId: number) => {
  equipmentHistoryLoading.value = true;
  equipmentError.value = '';
  try {
    selectedEquipmentDetail.value = await ManagerEquipmentService.getManagerEquipment(equipmentId, 10);
  } catch (e) {
    console.error('Failed to load equipment detail', e);
    equipmentError.value = `Не удалось загрузить историю: ${getApiErrorMessage(e)}`;
    selectedEquipmentDetail.value = null;
  } finally {
    equipmentHistoryLoading.value = false;
  }
};

const selectEquipment = async (equipmentId: number) => {
  selectedEquipmentId.value = equipmentId;
  showHistoryForm.value = false;
  showComponentForm.value = false;
  editingComponentId.value = null;
  historyForm.value = emptyHistoryForm();
  componentForm.value = emptyComponentForm();
  await loadEquipmentDetail(equipmentId);
};

const loadCustomerEquipment = async () => {
  if (!customerId.value) return;
  equipmentLoading.value = true;
  equipmentError.value = '';
  try {
    const res = await ManagerEquipmentService.listManagerEquipment(
      customerId.value,
      null,
      1,
      100,
      includeArchivedEquipment.value,
    );
    equipment.value = res.items || [];
    if (selectedEquipmentId.value && !equipment.value.some((item) => item.id === selectedEquipmentId.value)) {
      selectedEquipmentId.value = null;
      selectedEquipmentDetail.value = null;
    }
    if (!selectedEquipmentId.value && equipment.value.length) {
      await selectEquipment(equipment.value[0]!.id);
    } else if (selectedEquipmentId.value) {
      await loadEquipmentDetail(selectedEquipmentId.value);
    }
  } catch (e) {
    console.error('Failed to load customer equipment', e);
    equipmentError.value = `Не удалось загрузить оборудование: ${getApiErrorMessage(e)}`;
  } finally {
    equipmentLoading.value = false;
  }
};

const openEquipmentCreateForm = () => {
  equipmentForm.value = emptyEquipmentForm();
  editingEquipmentId.value = null;
  showEquipmentForm.value = true;
};

const openEquipmentEditForm = (item: ManagerEquipmentItemResponse) => {
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
  const payload = componentPayload();
  if (!payload.title && !payload.brand && !payload.model && !payload.serial && !payload.inventory_number) {
    equipmentError.value = 'Укажите название, бренд, модель, серийный или инвентарный номер компонента';
    return;
  }
  componentSaving.value = true;
  equipmentError.value = '';
  try {
    if (editingComponentId.value) {
      await ManagerEquipmentService.patchManagerEquipmentComponent(
        selectedEquipmentId.value,
        editingComponentId.value,
        payload as ManagerEquipmentComponentUpdatePayload,
      );
      setToast('Компонент обновлен');
    } else {
      await ManagerEquipmentService.createManagerEquipmentComponent(
        selectedEquipmentId.value,
        payload as ManagerEquipmentComponentCreatePayload,
      );
      setToast('Компонент добавлен');
    }
    showComponentForm.value = false;
    editingComponentId.value = null;
    componentForm.value = emptyComponentForm();
    await loadEquipmentDetail(selectedEquipmentId.value);
  } catch (e) {
    equipmentError.value = `Не удалось сохранить компонент: ${getApiErrorMessage(e)}`;
  } finally {
    componentSaving.value = false;
  }
};

const toggleEquipmentComponentArchive = async (item: ManagerEquipmentComponentItemResponse) => {
  if (!selectedEquipmentId.value || componentActionId.value) return;
  componentActionId.value = item.id;
  equipmentError.value = '';
  try {
    await ManagerEquipmentService.patchManagerEquipmentComponent(
      selectedEquipmentId.value,
      item.id,
      { is_archived: !item.is_archived },
    );
    setToast(item.is_archived ? 'Компонент возвращен из архива' : 'Компонент архивирован');
    await loadEquipmentDetail(selectedEquipmentId.value);
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
  historySaving.value = true;
  equipmentError.value = '';
  try {
    await ManagerEquipmentService.createManagerEquipmentHistory(selectedEquipmentId.value, historyPayload());
    setToast('Событие истории добавлено');
    showHistoryForm.value = false;
    historyForm.value = emptyHistoryForm();
    await loadEquipmentDetail(selectedEquipmentId.value);
  } catch (e) {
    equipmentError.value = `Не удалось добавить событие: ${getApiErrorMessage(e)}`;
  } finally {
    historySaving.value = false;
  }
};

const loadContractTemplates = async () => {
  try {
    const res = await ManagerDocsService.getDocTemplates('contract');
    contractTemplates.value = res.items;
  } catch (e) {
    console.warn('Failed to load contract templates', e);
  }
};

const openContractForm = () => {
  if (!openContractTemplates.value.length) {
    setToast('В настройках нет шаблонов, отмеченных как открытый договор');
    return;
  }
  contractForm.value = buildDefaultContractForm();
  showContractUploadForm.value = false;
  showContractForm.value = true;
};

const openContractUploadForm = () => {
  if (!openContractTemplates.value.length) {
    setToast('В настройках нет шаблонов, отмеченных как открытый договор');
    return;
  }
  const defaults = buildDefaultContractForm();
  contractUploadForm.value = {
    number: '',
    contract_date: defaults.contract_date,
    valid_until: defaults.valid_until,
    template_id: defaults.template_id,
    file: null,
  };
  showContractForm.value = false;
  showContractUploadForm.value = true;
};

const syncContractValidUntil = () => {
  if (!contractForm.value.contract_date) return;
  const start = new Date(`${contractForm.value.contract_date}T00:00:00`);
  if (Number.isNaN(start.getTime())) return;
  const end = new Date(start);
  end.setFullYear(end.getFullYear() + 1);
  contractForm.value.valid_until = toInputDate(end);
};

const syncUploadContractValidUntil = () => {
  if (!contractUploadForm.value.contract_date) return;
  const start = new Date(`${contractUploadForm.value.contract_date}T00:00:00`);
  if (Number.isNaN(start.getTime())) return;
  const end = new Date(start);
  end.setFullYear(end.getFullYear() + 1);
  contractUploadForm.value.valid_until = toInputDate(end);
};

const onContractUploadFileChange = (event: Event) => {
  const input = event.target as HTMLInputElement;
  contractUploadForm.value.file = input.files?.[0] || null;
};

const createContract = async () => {
  if (!customerId.value) return;
  if (!contractForm.value.template_id.trim()) {
    setToast('Выберите шаблон открытого договора');
    return;
  }
  contractSaving.value = true;
  try {
    const payload = {
      number: contractForm.value.number.trim() || null,
      template_id: contractForm.value.template_id.trim(),
      contract_date: contractForm.value.contract_date ? `${contractForm.value.contract_date}T00:00:00` : null,
      valid_until: contractForm.value.valid_until ? `${contractForm.value.valid_until}T00:00:00` : null,
    };
    await ManagerContractsService.createManagerCustomerContract(customerId.value, payload);
    showContractForm.value = false;
    await loadCustomerContracts();
    setToast('Договор создан');
  } catch (e) {
    setToast(`Не удалось создать договор: ${getApiErrorMessage(e)}`);
  } finally {
    contractSaving.value = false;
  }
};

const uploadContract = async () => {
  if (!customerId.value) return;
  if (!contractUploadForm.value.number.trim()) {
    setToast('Укажите номер договора');
    return;
  }
  if (!contractUploadForm.value.file) {
    setToast('Выберите файл договора');
    return;
  }
  if (!contractUploadForm.value.template_id.trim()) {
    setToast('Выберите шаблон открытого договора');
    return;
  }
  contractUploadSaving.value = true;
  try {
    await ManagerContractsService.uploadManagerCustomerContract(customerId.value, {
      number: contractUploadForm.value.number.trim(),
      contract_date: `${contractUploadForm.value.contract_date}T00:00:00`,
      valid_until: `${contractUploadForm.value.valid_until}T00:00:00`,
      template_id: contractUploadForm.value.template_id.trim(),
      file: contractUploadForm.value.file,
    });
    showContractUploadForm.value = false;
    await loadCustomerContracts();
    setToast('Договор загружен');
  } catch (e) {
    setToast(`Не удалось загрузить договор: ${getApiErrorMessage(e)}`);
  } finally {
    contractUploadSaving.value = false;
  }
};

const archiveContract = async (contract: ManagerCustomerContractItemResponse) => {
  if (!customerId.value) return;
  if (!confirm(`Архивировать договор ${contract.number}?`)) return;
  try {
    await ManagerContractsService.archiveManagerCustomerContract(customerId.value, contract.id);
    await loadCustomerContracts();
    setToast('Договор архивирован');
  } catch (e) {
    setToast(`Не удалось архивировать договор: ${getApiErrorMessage(e)}`);
  }
};

const deleteContract = async (contract: ManagerCustomerContractItemResponse) => {
  if (!customerId.value) return;
  if (!confirm(`Удалить договор ${contract.number} из базы и Google Drive?`)) return;
  try {
    await ManagerContractsService.deleteManagerCustomerContract(customerId.value, contract.id);
    await loadCustomerContracts();
    setToast('Договор удален');
  } catch (e) {
    setToast(`Не удалось удалить договор: ${getApiErrorMessage(e)}`);
  }
};

const navigateToCustomers = () => {
  const target = returnTo.value || '/manager/customers';
  window.history.pushState({}, '', target);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

const openOrders = () => {
  if (!customer.value) return;
  const search = customer.value.inn || customer.value.phone || customer.value.email || customer.value.name || '';
  const path = search
    ? `/manager/orders/kanban?search=${encodeURIComponent(search)}`
    : '/manager/orders/kanban';
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

const onOrderCreated = (orderId: number) => {
  showCreateOrder.value = false;
  window.history.pushState({}, '', `/manager/orders/kanban?orderId=${orderId}`);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

const startEdit = () => {
  if (!customer.value) return;
  editMode.value = true;
  success.value = '';
  saveError.value = '';
  resetFormFromCustomer();
};

const cancelEdit = () => {
  editMode.value = false;
  resetFormFromCustomer();
};

const normalizeForm = () => {
    form.value.email = normalizeEmail(form.value.email || '');
    form.value.inn = normalizeUnp(form.value.inn || '');
    form.value.iban = normalizeIban(form.value.iban || '');
};

const onInnBlur = async () => {
    if (!form.value.inn || form.value.inn.length !== 9) return;
    const data = await lookupCompany(form.value.inn);
    if (data) {
        if (!form.value.full_legal_name) form.value.full_legal_name = data.fullLegalName || '';
        if (!form.value.legal_address) form.value.legal_address = data.legalAddress || '';
        if (!form.value.name) form.value.name = data.fullLegalName || '';
    }
};

const onIbanBlur = async () => {
    if (!form.value.iban || form.value.iban.length < 15) return;
    const data = await lookupBank(form.value.iban);
    if (data) {
        if (!form.value.bank_name) form.value.bank_name = data.bankName || '';
        if (!form.value.bic) form.value.bic = data.bic || '';
    }
};

const validateForm = (): boolean => {
  normalizeForm();
  clearFieldErrors();

  phoneError.value = validateOptionalBelarusPhone(form.value.phone || '', phoneMask.isComplete.value);
  emailError.value = validateOptionalEmail(form.value.email || '');
  innError.value = validateOptionalByUnp(form.value.inn || '');
  ibanError.value = validateOptionalByIban(form.value.iban || '');

  if (!form.value.name.trim()) {
    serverErrors.value.name = 'Имя клиента не может быть пустым';
  }
  if (!form.value.phone.trim()) {
    phoneError.value = 'Телефон обязателен';
  }
  if (isCompany.value && !form.value.full_legal_name.trim()) {
    serverErrors.value.full_legal_name = 'Для юрлица укажите полное наименование';
  }

  return !phoneError.value && !emailError.value && !innError.value && !ibanError.value && !Object.keys(serverErrors.value).length;
};

const saveCustomer = async () => {
  if (!customer.value || !hasChanges.value || !validateForm()) return;

  const payload: Record<string, string> = {};
  (Object.keys(formDiff.value) as (keyof CustomerForm)[]).forEach((key) => {
    if (!formDiff.value[key]) return;
    payload[key] = currentForm.value[key]?.trim?.() ?? currentForm.value[key];
  });

  payload.phone = normalizePhoneForApi(form.value.phone || '');
  payload.email = normalizeEmail(form.value.email || '');
  payload.inn = normalizeUnp(form.value.inn || '');
  payload.iban = normalizeIban(form.value.iban || '');

  const optionalKeys: (keyof CustomerForm)[] = [
    'email',
    'inn',
    'kpp',
    'full_legal_name',
    'legal_address',
    'actual_address',
    'bank_name',
    'bic',
    'iban',
    'signer_position',
    'signer_name',
    'acting_basis',
  ];
  optionalKeys.forEach((key) => {
    if (!(key in payload)) return;
    if (!payload[key]) payload[key] = '';
  });

  saving.value = true;
  success.value = '';
  saveError.value = '';
  try {
    const updated = await api.patchManagerCustomer(customer.value.id, payload);
    customer.value = updated;
    editMode.value = false;
    resetFormFromCustomer();
    success.value = 'Карточка клиента обновлена';
    dispatchCustomerUpdated(updated);
  } catch (e) {
    console.error(e);
    const parsed = parseApiFieldErrors(e, [
      'name',
      'phone',
      'email',
      'type',
      'inn',
      'kpp',
      'full_legal_name',
      'legal_address',
      'actual_address',
      'bank_name',
      'bic',
      'iban',
      'signer_position',
      'signer_name',
      'acting_basis',
    ]);
    serverErrors.value = parsed.fieldErrors;
    if (!phoneError.value && parsed.fieldErrors.phone) phoneError.value = parsed.fieldErrors.phone;
    if (!emailError.value && parsed.fieldErrors.email) emailError.value = parsed.fieldErrors.email;
    if (!innError.value && parsed.fieldErrors.inn) innError.value = parsed.fieldErrors.inn;
    if (!ibanError.value && parsed.fieldErrors.iban) ibanError.value = parsed.fieldErrors.iban;
    saveError.value = `Не удалось сохранить карточку клиента: ${parsed.message}`;
  } finally {
    saving.value = false;
  }
};

const isDeleting = ref(false);
const deleteCustomer = async () => {
  if (!customer.value?.id) return;
  const proceed = window.confirm("Вы уверены? Это действие безвозвратно удалит карточку клиента.");
  if (!proceed) return;

  isDeleting.value = true;
  error.value = '';
  try {
    await api.deleteManagerCustomer(customer.value.id);
    success.value = 'Клиент успешно удален';
    setTimeout(() => {
      navigateToCustomers();
    }, 1500);
  } catch (err: any) {
    const message = getApiErrorMessage(err) || 'Ошибка при удалении клиента';
    error.value = message;
    setToast(message);
  } finally {
    isDeleting.value = false;
  }
};

watch(customerId, () => {
  void loadCustomer();
  void loadCustomerDocs();
  void loadCustomerContracts();
  void loadCustomerEquipment();
  void loadContractTemplates();
});

watch(includeArchivedEquipment, () => {
  void loadCustomerEquipment();
});

onMounted(() => {
  void loadCustomer();
  void loadCustomerDocs();
  void loadCustomerContracts();
  void loadCustomerEquipment();
  void loadContractTemplates();
});
</script>

<template>
  <div class="min-h-screen bg-[var(--mv-bg)] text-[var(--mv-text)]">
    <Transition name="fade">
      <div v-if="toast" class="fixed top-6 right-6 z-[100] rounded-xl bg-red-600 px-6 py-3 font-medium text-white shadow-2xl">
        {{ toast }}
      </div>
    </Transition>
    <div class="mx-auto max-w-[1200px] px-4 py-6 md:px-8">
      <div class="mb-4 flex items-center gap-2">
        <button class="btn-mini-outline" type="button" @click="navigateToCustomers">
          <ArrowLeft class="h-4 w-4" />
          {{ backLabel }}
        </button>
        <button v-if="customer" class="btn-mini" type="button" @click="openOrders">
          Сделки клиента
        </button>
        <button v-if="customer && !editMode" class="btn-mini" type="button" @click="showCreateOrder = true">
          <Plus class="h-4 w-4" />
          Новый заказ
        </button>
        <button v-if="customer && !editMode" class="btn-mini" type="button" @click="startEdit">
          Редактировать
        </button>
        <button v-if="customer && !editMode" class="btn-mini hover:bg-red-50 hover:text-red-600 hover:border-red-200 text-gray-400 bg-white border border-gray-200 transition-colors" type="button" :disabled="isDeleting" @click="deleteCustomer" title="Безвозвратное удаление">
          {{ isDeleting ? 'Удаление...' : 'Удалить' }}
        </button>
        <button v-if="customer && editMode" class="btn-mini-outline" type="button" :disabled="saving" @click="cancelEdit">
          <X class="h-4 w-4" />
          Отмена
        </button>
        <button v-if="customer && editMode" class="btn-mini" type="button" :disabled="saving || !hasChanges" @click="saveCustomer">
          <Save class="h-4 w-4" />
          {{ saving ? 'Сохраняем…' : 'Сохранить' }}
        </button>
      </div>

      <div v-if="loading" class="rounded-[2rem] border border-[var(--mv-border)] bg-[var(--mv-surface)] p-8 text-sm text-[var(--mv-text-muted)]">
        Загрузка карточки клиента...
      </div>
      <div v-else-if="error" class="rounded-[2rem] border border-red-500/40 bg-red-900/20 p-6 text-sm text-red-200">
        {{ error }}
      </div>
      <div v-else-if="customer" class="space-y-4">
        <div v-if="success" class="rounded-xl border border-emerald-500/40 bg-emerald-900/20 px-4 py-3 text-sm text-emerald-200">
          {{ success }}
        </div>
        <div v-if="saveError" class="rounded-xl border border-red-500/40 bg-red-900/20 px-4 py-3 text-sm text-red-200">
          {{ saveError }}
        </div>

        <header class="rounded-[2rem] border border-[var(--mv-border)] bg-[var(--mv-surface)] p-6 shadow-sm">
          <p class="text-xs uppercase tracking-[0.2em] text-[var(--mv-text-muted)]">Customer profile</p>
          <h1 class="mt-2 text-2xl font-bold">{{ customer.full_legal_name || customer.name || `Клиент #${customer.id}` }}</h1>
          <p class="mt-1 text-sm text-[var(--mv-text-muted)]">ID: #{{ customer.id }} · {{ customer.type === 'company' ? 'Юр. лицо' : 'Физ. лицо' }}</p>
        </header>

        <section class="grid gap-4 md:grid-cols-2">
          <article class="rounded-[1.5rem] border border-[var(--mv-border)] bg-[var(--mv-surface)] p-5 shadow-sm">
            <h2 class="mb-3 text-sm font-semibold uppercase tracking-[0.16em] text-[var(--mv-text-muted)]">Контакты</h2>

            <template v-if="!editMode">
              <div class="space-y-2 text-sm">
                <p class="detail"><UserRound class="h-4 w-4" /> <span>{{ customer.name || '—' }}</span></p>
                <p class="detail"><Phone class="h-4 w-4" /> <span>{{ customer.phone || '—' }}</span></p>
                <p class="detail"><Mail class="h-4 w-4" /> <span>{{ customer.email || '—' }}</span></p>
                <p v-if="customer.type !== 'company'" class="detail"><Building2 class="h-4 w-4" /> <span>Адрес: {{ customer.actual_address || customer.last_delivery_address || '—' }}</span></p>
                <p class="detail"><Building2 class="h-4 w-4" /> <span>УНП: {{ customer.inn || '—' }}</span></p>
                <p class="detail"><Building2 class="h-4 w-4" /> <span>КПП: {{ customer.kpp || '—' }}</span></p>
                <p class="detail"><ReceiptText class="h-4 w-4" /> <span>Заказов: {{ customer.order_count }}</span></p>
                <p class="detail"><ReceiptText class="h-4 w-4" /> <span>Создан: {{ formatDate(customer.created_at) }}</span></p>
              </div>
            </template>

            <template v-else>
              <div class="space-y-3 text-sm">
                <select v-model="form.type" :class="fieldClass('type')">
                  <option value="individual">Физ. лицо</option>
                  <option value="company">Юр. лицо</option>
                </select>
                <input v-model="form.name" type="text" :placeholder="isCompany ? 'Компания' : 'Имя клиента'" :class="fieldClass('name')" />
                <div v-if="!isCompany" class="relative">
                  <input
                    v-model="form.actual_address"
                    type="text"
                    placeholder="Адрес объекта / доставки"
                    autocomplete="off"
                    :class="fieldClass('actual_address')"
                    @input="onCustomerAddressInput('actual_address')"
                    @focus="activeCustomerAddressField = 'actual_address'"
                    @blur="hideCustomerAddressSuggestions"
                  />
                  <div v-if="customerAddressLookupLoading && activeCustomerAddressField === 'actual_address'" class="absolute right-3 top-2">
                    <span class="material-icons-round animate-spin text-teal-500 text-sm">refresh</span>
                  </div>
                  <div v-if="activeCustomerAddressField === 'actual_address' && customerAddressSuggestions.length > 0" class="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-xl border border-slate-200 bg-white p-1 shadow-xl">
                    <button
                      v-for="(item, index) in customerAddressSuggestions"
                      :key="index"
                      type="button"
                      class="w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-50"
                      @mousedown.prevent="selectCustomerAddressSuggestion('actual_address', item)"
                    >
                      <span class="block font-medium text-slate-900">{{ item.title || item.value }}</span>
                      <span v-if="item.subtitle" class="block truncate text-xs text-slate-500">{{ item.subtitle }}</span>
                    </button>
                  </div>
                </div>
                <input ref="phoneInputRef" v-model="form.phone" type="tel" placeholder="+375 (XX) XXX-XX-XX или +7 XXX XXX-XX-XX" :class="fieldClass('phone')" />
                <span v-if="phoneError" class="field-error">{{ phoneError }}</span>
                <input v-model="form.email" type="email" placeholder="Email" :class="fieldClass('email')" />
                <span v-if="emailError" class="field-error">{{ emailError }}</span>
                <div class="relative">
                    <input v-model="form.inn" type="text" placeholder="УНП" :class="fieldClass('inn')" @blur="onInnBlur" />
                    <div v-if="isEgrLoading" class="absolute right-3 top-2">
                        <span class="material-icons-round animate-spin text-teal-500 text-sm">refresh</span>
                    </div>
                </div>
                <span v-if="innError" class="field-error">{{ innError }}</span>
                <input v-model="form.kpp" type="text" placeholder="КПП" :class="fieldClass('kpp')" />
              </div>
            </template>
          </article>

          <article class="rounded-[1.5rem] border border-[var(--mv-border)] bg-[var(--mv-surface)] p-5 shadow-sm">
            <h2 class="mb-3 text-sm font-semibold uppercase tracking-[0.16em] text-[var(--mv-text-muted)]">Юр. реквизиты</h2>

            <template v-if="!editMode">
              <div class="space-y-2 text-sm">
                <p class="detail-value"><span>Полное наименование</span><strong>{{ customer.full_legal_name || '—' }}</strong></p>
                <p class="detail-value"><span>Юр. адрес</span><strong>{{ customer.legal_address || '—' }}</strong></p>
                <p class="detail-value"><span>Факт. адрес</span><strong>{{ customer.actual_address || '—' }}</strong></p>
                <p class="detail-value"><span>Банк</span><strong>{{ customer.bank_name || '—' }}</strong></p>
                <p class="detail-value"><span>BIC</span><strong>{{ customer.bic || '—' }}</strong></p>
                <p class="detail-value"><span>IBAN</span><strong>{{ customer.iban || '—' }}</strong></p>
                <p class="detail-value"><span>Подписант</span><strong>{{ customer.signer_name || '—' }}</strong></p>
                <p class="detail-value"><span>Должность</span><strong>{{ customer.signer_position || '—' }}</strong></p>
                <p class="detail-value"><span>Основание</span><strong>{{ customer.acting_basis || '—' }}</strong></p>
                <p class="detail-value"><span>Последний адрес доставки</span><strong>{{ customer.last_delivery_address || '—' }}</strong></p>
              </div>
            </template>

            <template v-else>
              <div class="space-y-3 text-sm">
                <div v-if="isCompany" class="space-y-3">
                  <input v-model="form.full_legal_name" type="text" placeholder="Полное наименование" :class="fieldClass('full_legal_name')" />
                  <div class="relative">
                    <input
                      v-model="form.legal_address"
                      type="text"
                      placeholder="Юр. адрес"
                      autocomplete="off"
                      :class="fieldClass('legal_address')"
                      @input="onCustomerAddressInput('legal_address')"
                      @focus="activeCustomerAddressField = 'legal_address'"
                      @blur="hideCustomerAddressSuggestions"
                    />
                    <div v-if="customerAddressLookupLoading && activeCustomerAddressField === 'legal_address'" class="absolute right-3 top-2">
                      <span class="material-icons-round animate-spin text-teal-500 text-sm">refresh</span>
                    </div>
                    <div v-if="activeCustomerAddressField === 'legal_address' && customerAddressSuggestions.length > 0" class="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-xl border border-slate-200 bg-white p-1 shadow-xl">
                      <button
                        v-for="(item, index) in customerAddressSuggestions"
                        :key="index"
                        type="button"
                        class="w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-50"
                        @mousedown.prevent="selectCustomerAddressSuggestion('legal_address', item)"
                      >
                        <span class="block font-medium text-slate-900">{{ item.title || item.value }}</span>
                        <span v-if="item.subtitle" class="block truncate text-xs text-slate-500">{{ item.subtitle }}</span>
                      </button>
                    </div>
                  </div>
                  <div class="relative">
                    <input
                      v-model="form.actual_address"
                      type="text"
                      placeholder="Факт. адрес"
                      autocomplete="off"
                      :class="fieldClass('actual_address')"
                      @input="onCustomerAddressInput('actual_address')"
                      @focus="activeCustomerAddressField = 'actual_address'"
                      @blur="hideCustomerAddressSuggestions"
                    />
                    <div v-if="customerAddressLookupLoading && activeCustomerAddressField === 'actual_address'" class="absolute right-3 top-2">
                      <span class="material-icons-round animate-spin text-teal-500 text-sm">refresh</span>
                    </div>
                    <div v-if="activeCustomerAddressField === 'actual_address' && customerAddressSuggestions.length > 0" class="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-xl border border-slate-200 bg-white p-1 shadow-xl">
                      <button
                        v-for="(item, index) in customerAddressSuggestions"
                        :key="index"
                        type="button"
                        class="w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-50"
                        @mousedown.prevent="selectCustomerAddressSuggestion('actual_address', item)"
                      >
                        <span class="block font-medium text-slate-900">{{ item.title || item.value }}</span>
                        <span v-if="item.subtitle" class="block truncate text-xs text-slate-500">{{ item.subtitle }}</span>
                      </button>
                    </div>
                  </div>
                  <input v-model="form.bank_name" type="text" placeholder="Название банка" :class="fieldClass('bank_name')" />
                  <input v-model="form.bic" type="text" placeholder="BIC" :class="fieldClass('bic')" />
                  <div class="relative">
                    <input v-model="form.iban" type="text" placeholder="IBAN" :class="fieldClass('iban')" @blur="onIbanBlur" />
                    <div v-if="isBankLoading" class="absolute right-3 top-2">
                        <span class="material-icons-round animate-spin text-teal-500 text-sm">refresh</span>
                    </div>
                  </div>
                  <span v-if="ibanError" class="field-error">{{ ibanError }}</span>
                  <input v-model="form.signer_name" type="text" placeholder="Подписант" :class="fieldClass('signer_name')" />
                  <input v-model="form.signer_position" type="text" placeholder="Должность подписанта" :class="fieldClass('signer_position')" />
                  <input v-model="form.acting_basis" type="text" placeholder="Основание действий" :class="fieldClass('acting_basis')" />
                </div>
                <p v-else class="text-xs text-[var(--mv-text-muted)]">Для физлица реквизиты юрлица не обязательны.</p>
              </div>
            </template>
          </article>
        </section>

        <section v-if="!editMode && isCompany" class="mt-8 mb-6">
          <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 class="flex items-center gap-2 text-lg font-bold">
              <span class="material-icons-round text-teal-500">contract</span>
              Открытые договоры
              <span v-if="contracts.length" class="flex h-6 min-w-6 items-center justify-center rounded-full bg-teal-500/20 px-2 text-xs text-teal-400">{{ contracts.length }}</span>
            </h2>
            <div class="flex flex-wrap gap-2">
              <button class="btn-mini-outline" type="button" @click="openContractUploadForm">
                Загрузить договор
              </button>
              <button class="btn-mini" type="button" @click="openContractForm">
                Создать договор
              </button>
            </div>
          </div>

          <form v-if="showContractForm" class="mb-4 rounded-2xl border border-[var(--mv-border)] bg-[var(--mv-panel)] p-4" @submit.prevent="createContract">
            <div class="grid gap-3 md:grid-cols-4">
              <input v-model="contractForm.number" class="field-input" type="text" placeholder="Номер, если уже известен" />
              <input v-model="contractForm.contract_date" class="field-input" type="date" @change="syncContractValidUntil" />
              <input v-model="contractForm.valid_until" class="field-input" type="date" />
              <select v-model="contractForm.template_id" class="field-input">
                <option v-for="template in openContractTemplates" :key="template.id" :value="template.id">
                  {{ template.name }}
                </option>
              </select>
              <p class="md:col-span-4 text-xs text-[var(--mv-text-muted)]">
                Роли берутся из выбранного шаблона: {{ getTemplateRoleLabel(contractForm.template_id) }}
              </p>
            </div>
            <div class="mt-3 flex justify-end gap-2">
              <button class="btn-mini-outline" type="button" @click="showContractForm = false">Отмена</button>
              <button class="btn-mini" type="submit" :disabled="contractSaving">
                {{ contractSaving ? 'Создаем...' : 'Создать' }}
              </button>
            </div>
          </form>

          <form v-if="showContractUploadForm" class="mb-4 rounded-2xl border border-[var(--mv-border)] bg-[var(--mv-panel)] p-4" @submit.prevent="uploadContract">
            <div class="grid gap-3 md:grid-cols-4">
              <input v-model="contractUploadForm.number" class="field-input" type="text" placeholder="Номер договора" required />
              <input v-model="contractUploadForm.contract_date" class="field-input" type="date" required @change="syncUploadContractValidUntil" />
              <input v-model="contractUploadForm.valid_until" class="field-input" type="date" required />
              <select v-model="contractUploadForm.template_id" class="field-input">
                <option v-for="template in openContractTemplates" :key="template.id" :value="template.id">
                  {{ template.name }}
                </option>
              </select>
              <input class="field-input" type="file" accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document" required @change="onContractUploadFileChange" />
              <p class="md:col-span-4 text-xs text-[var(--mv-text-muted)]">
                Роли загруженного договора будут взяты из выбранного шаблона: {{ getTemplateRoleLabel(contractUploadForm.template_id) }}
              </p>
            </div>
            <div class="mt-3 flex justify-end gap-2">
              <button class="btn-mini-outline" type="button" @click="showContractUploadForm = false">Отмена</button>
              <button class="btn-mini" type="submit" :disabled="contractUploadSaving">
                {{ contractUploadSaving ? 'Загружаем...' : 'Загрузить' }}
              </button>
            </div>
          </form>

          <div v-if="contractsLoading" class="text-sm text-[var(--mv-text-muted)] p-5 border border-dashed border-[var(--mv-border)] rounded-2xl">
            Загрузка договоров...
          </div>
          <div v-else-if="contracts.length" class="space-y-3">
            <div v-for="contract in contracts" :key="contract.id" class="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4 text-slate-700 shadow-sm dark:border-slate-700/50 dark:bg-[#1e293b] dark:text-slate-300">
              <div class="flex items-center gap-4">
                <div class="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-teal-600 dark:bg-slate-800 dark:text-teal-400">
                  <span class="material-icons-round text-2xl">article</span>
                </div>
                <div>
                  <div class="flex flex-wrap items-center gap-2">
                    <p class="text-[15px] font-semibold leading-none text-slate-900 dark:text-white">{{ contract.number }}</p>
                    <span class="rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider" :class="contract.status === 'active' ? 'bg-teal-500/10 text-teal-700 dark:text-teal-300' : 'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400'">
                      {{ contract.status === 'active' ? 'активен' : 'архив' }}
                    </span>
                  </div>
                  <p class="mt-2 text-[13px] leading-none text-slate-500 dark:text-slate-400">
                    {{ formatDateOnly(contract.valid_from) }} - {{ formatDateOnly(contract.valid_until) }}
                  </p>
                  <p class="mt-2 text-[12px] leading-none text-slate-500 dark:text-slate-400">
                    Роли: {{ getRoleLabel(contract.document_role_type) }}
                  </p>
                </div>
              </div>
              <div class="flex items-center gap-2">
                <a v-if="contract.edit_url" :href="contract.edit_url" target="_blank" class="flex h-10 w-10 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-white" title="Открыть договор">
                  <span class="material-icons-round text-[20px]">open_in_new</span>
                </a>
                <button v-if="contract.status === 'active'" class="flex h-10 w-10 items-center justify-center rounded-lg text-amber-400 hover:bg-amber-500/10 hover:text-amber-300 transition-colors" type="button" title="Архивировать" @click="archiveContract(contract)">
                  <span class="material-icons-round text-[20px]">archive</span>
                </button>
                <button class="flex h-10 w-10 items-center justify-center rounded-lg text-red-400 transition-colors hover:bg-red-500/10 hover:text-red-300" type="button" title="Удалить" @click="deleteContract(contract)">
                  <span class="material-icons-round text-[20px]">delete</span>
                </button>
              </div>
            </div>
          </div>
          <div v-else class="text-sm text-[var(--mv-text-muted)] italic py-5 text-center rounded-2xl border border-dashed border-[var(--mv-border)]">
            Открытые договоры пока не созданы
          </div>
        </section>

        <section v-if="!editMode" class="mt-8 mb-6">
          <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 class="flex items-center gap-2 text-lg font-bold">
              <span class="material-icons-round text-teal-500">precision_manufacturing</span>
              Оборудование клиента
              <span v-if="equipment.length" class="flex h-6 min-w-6 items-center justify-center rounded-full bg-teal-500/20 px-2 text-xs text-teal-400">{{ equipment.length }}</span>
            </h2>
            <div class="flex flex-wrap items-center gap-2">
              <label class="inline-flex items-center gap-2 rounded-xl border border-[var(--mv-border)] px-3 py-2 text-xs text-[var(--mv-text-muted)]">
                <input v-model="includeArchivedEquipment" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500" />
                Архив
              </label>
              <button class="btn-mini-outline" type="button" :disabled="equipmentLoading" @click="loadCustomerEquipment">
                Обновить
              </button>
              <button class="btn-mini" type="button" @click="openEquipmentCreateForm">
                Создать оборудование
              </button>
            </div>
          </div>

          <p v-if="equipmentError" class="mb-3 rounded-xl border border-red-500/40 bg-red-900/20 px-4 py-3 text-sm text-red-200">
            {{ equipmentError }}
          </p>

          <form v-if="showEquipmentForm" class="mb-4 rounded-2xl border border-[var(--mv-border)] bg-[var(--mv-panel)] p-4" @submit.prevent="saveEquipment">
            <div class="grid gap-3 md:grid-cols-3">
              <label class="field-label">
                Филиал
                <select v-model="equipmentForm.customer_branch_id" class="field-input">
                  <option :value="null">Без филиала</option>
                  <option v-for="branch in customer.branches || []" :key="branch.id" :value="branch.id">
                    {{ branch.name || branch.delivery_address || `Филиал #${branch.id}` }}
                  </option>
                </select>
              </label>
              <label class="field-label">
                Источник
                <select v-model="equipmentForm.equipment_source" class="field-input">
                  <option v-for="option in EQUIPMENT_SOURCE_OPTIONS" :key="option.value" :value="option.value">
                    {{ option.label }}
                  </option>
                </select>
              </label>
              <label class="field-label">
                Тип
                <input v-model="equipmentForm.equipment_type" class="field-input" placeholder="hvac, chiller..." />
              </label>
              <label class="field-label">
                ID товара каталога
                <input v-model="equipmentForm.catalog_product_id" class="field-input" inputmode="numeric" placeholder="Можно оставить пустым" />
              </label>
              <label class="field-label">
                ID исходного заказа
                <input v-model="equipmentForm.source_order_id" class="field-input" inputmode="numeric" placeholder="Заказ продажи/монтажа" />
              </label>
              <label class="field-label">
                Название
                <input v-model="equipmentForm.display_name" class="field-input" placeholder="Кондиционер серверной" />
              </label>
              <label class="field-label">
                Бренд
                <input v-model="equipmentForm.brand" class="field-input" placeholder="Gree, LG..." />
              </label>
              <label class="field-label">
                Модель
                <input v-model="equipmentForm.model" class="field-input" placeholder="Модель блока" />
              </label>
              <label class="field-label">
                Серийный номер
                <input v-model="equipmentForm.serial" class="field-input" placeholder="SN..." />
              </label>
              <label class="field-label">
                Инвентарный номер
                <input v-model="equipmentForm.inventory_number" class="field-input" placeholder="Инв. номер клиента" />
              </label>
              <label class="field-label">
                Локация
                <input v-model="equipmentForm.location_hint" class="field-input" placeholder="Серверная, 2 этаж" />
              </label>
              <label class="field-label">
                Хладагент
                <input v-model="equipmentForm.refrigerant_type" class="field-input" placeholder="R32, R410A" />
              </label>
              <label class="field-label">
                Дата установки
                <input v-model="equipmentForm.installed_at" class="field-input" type="date" />
              </label>
              <label class="field-label">
                Ввод в эксплуатацию
                <input v-model="equipmentForm.commissioned_at" class="field-input" type="date" />
              </label>
              <label class="field-label">
                Гарантия с
                <input v-model="equipmentForm.warranty_started_at" class="field-input" type="date" />
              </label>
              <label class="field-label">
                Гарантия до
                <input v-model="equipmentForm.warranty_expires_at" class="field-input" type="date" />
              </label>
              <label class="field-label md:col-span-3">
                Условия гарантии
                <textarea v-model="equipmentForm.warranty_terms" class="field-input min-h-[72px]" placeholder="Например: 24 месяца на оборудование, 12 месяцев на монтаж. Гарантия сохраняется при ежегодном ТО." />
              </label>
              <label class="field-label md:col-span-3">
                Заметки
                <textarea v-model="equipmentForm.notes" class="field-input min-h-[72px]" placeholder="Особенности доступа, состояние, монтаж..." />
              </label>
            </div>
            <div class="mt-3 flex flex-wrap justify-end gap-2">
              <button class="btn-mini-outline" type="button" :disabled="equipmentSaving" @click="showEquipmentForm = false">Отмена</button>
              <button class="btn-mini" type="submit" :disabled="equipmentSaving">
                {{ equipmentSaving ? 'Сохраняем...' : (editingEquipmentId ? 'Сохранить' : 'Создать') }}
              </button>
            </div>
          </form>

          <div v-if="equipmentLoading" class="rounded-2xl border border-dashed border-[var(--mv-border)] p-5 text-sm text-[var(--mv-text-muted)]">
            Загрузка оборудования...
          </div>
          <div v-else-if="equipment.length" class="grid gap-4 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
            <div class="space-y-3">
              <button
                v-for="item in equipment"
                :key="item.id"
                type="button"
                class="w-full rounded-xl border p-4 text-left shadow-sm transition"
                :class="selectedEquipmentId === item.id ? 'border-teal-400 bg-teal-500/10' : 'border-[var(--mv-border)] bg-[var(--mv-surface)] hover:border-teal-400/60'"
                @click="selectEquipment(item.id)"
              >
                <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div class="min-w-0">
                    <div class="flex flex-wrap items-center gap-2">
                      <p class="break-words text-sm font-semibold text-[var(--mv-text)]">{{ equipmentTitle(item) }}</p>
                      <span class="rounded-full px-2 py-0.5 text-[11px] font-semibold" :class="warrantyStatusClass(item.warranty_status)">
                        {{ warrantyStatusLabel(item.warranty_status) }}
                      </span>
                      <span v-if="item.is_archived" class="rounded-full bg-slate-500/20 px-2 py-0.5 text-[11px] font-semibold text-slate-400">Архив</span>
                    </div>
                    <p class="mt-1 break-words text-xs text-[var(--mv-text-muted)]">{{ equipmentSubtitle(item) }}</p>
                    <p class="mt-1 text-xs text-[var(--mv-text-muted)]">{{ equipmentBranchLabel(item.customer_branch_id) }} · {{ equipmentSourceLabel(item.equipment_source) }}</p>
                    <p v-if="item.warranty_expires_at" class="mt-1 text-xs text-[var(--mv-text-muted)]">Гарантия до {{ formatDateOnly(item.warranty_expires_at) }}</p>
                  </div>
                  <div class="flex shrink-0 flex-wrap gap-2">
                    <button class="btn-mini-outline text-xs" type="button" @click.stop="openEquipmentEditForm(item)">Править</button>
                    <button class="btn-mini-outline text-xs" type="button" :disabled="equipmentActionId === item.id" @click.stop="toggleEquipmentArchive(item)">
                      {{ equipmentActionId === item.id ? '...' : (item.is_archived ? 'Вернуть' : 'Архив') }}
                    </button>
                  </div>
                </div>
              </button>
            </div>

            <div class="rounded-2xl border border-[var(--mv-border)] bg-[var(--mv-surface)] p-4">
              <div v-if="equipmentHistoryLoading" class="text-sm text-[var(--mv-text-muted)]">Загрузка истории...</div>
              <template v-else-if="selectedEquipmentDetail">
                <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div class="min-w-0">
                    <p class="break-words text-base font-semibold">{{ equipmentTitle(selectedEquipmentDetail) }}</p>
                    <p class="mt-1 break-words text-xs text-[var(--mv-text-muted)]">{{ equipmentSubtitle(selectedEquipmentDetail) }}</p>
                    <div class="mt-2 flex flex-wrap gap-2 text-xs">
                      <span class="rounded-full px-2 py-0.5 font-semibold" :class="warrantyStatusClass(selectedEquipmentDetail.warranty_status)">
                        {{ warrantyStatusLabel(selectedEquipmentDetail.warranty_status) }}
                      </span>
                      <span class="rounded-full bg-slate-500/20 px-2 py-0.5 text-slate-400">{{ equipmentSourceLabel(selectedEquipmentDetail.equipment_source) }}</span>
                    </div>
                    <div class="mt-3 grid gap-2 text-xs text-[var(--mv-text-muted)] sm:grid-cols-2">
                      <p v-if="selectedEquipmentDetail.catalog_product_id">Товар каталога: #{{ selectedEquipmentDetail.catalog_product_id }}</p>
                      <p v-if="selectedEquipmentDetail.source_order_id">Исходный заказ: #{{ selectedEquipmentDetail.source_order_id }}</p>
                      <p v-if="selectedEquipmentDetail.installed_at">Установка: {{ formatDateOnly(selectedEquipmentDetail.installed_at) }}</p>
                      <p v-if="selectedEquipmentDetail.commissioned_at">Ввод: {{ formatDateOnly(selectedEquipmentDetail.commissioned_at) }}</p>
                      <p v-if="selectedEquipmentDetail.warranty_started_at">Гарантия с: {{ formatDateOnly(selectedEquipmentDetail.warranty_started_at) }}</p>
                      <p v-if="selectedEquipmentDetail.warranty_expires_at">Гарантия до: {{ formatDateOnly(selectedEquipmentDetail.warranty_expires_at) }}</p>
                      <p v-if="selectedEquipmentDetail.warranty_terms" class="break-words sm:col-span-2">Условия: {{ selectedEquipmentDetail.warranty_terms }}</p>
                    </div>
                  </div>
                  <button class="btn-mini whitespace-nowrap text-xs" type="button" @click="openHistoryCreateForm">Добавить событие</button>
                </div>

                <div class="mt-4 rounded-xl border border-[var(--mv-border)] bg-[var(--mv-panel)] p-3">
                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p class="text-sm font-semibold text-[var(--mv-text)]">Состав оборудования</p>
                      <p class="text-xs text-[var(--mv-text-muted)]">Внутренний блок, наружный блок и серийные номера</p>
                    </div>
                    <button class="btn-mini-outline text-xs" type="button" @click="openComponentCreateForm">
                      Добавить блок
                    </button>
                  </div>

                  <form v-if="showComponentForm" class="mt-3 rounded-xl border border-[var(--mv-border)] bg-[var(--mv-surface)] p-3" @submit.prevent="saveEquipmentComponent">
                    <div class="grid gap-3 md:grid-cols-2">
                      <label class="field-label">
                        Тип блока
                        <select v-model="componentForm.component_type" class="field-input">
                          <option v-for="option in EQUIPMENT_COMPONENT_OPTIONS" :key="option.value" :value="option.value">
                            {{ option.label }}
                          </option>
                        </select>
                      </label>
                      <label class="field-label">
                        Название
                        <input v-model="componentForm.title" class="field-input" placeholder="Например: внутренний блок спальня" />
                      </label>
                      <label class="field-label">
                        Бренд
                        <input v-model="componentForm.brand" class="field-input" placeholder="TCL, Gree..." />
                      </label>
                      <label class="field-label">
                        Модель
                        <input v-model="componentForm.model" class="field-input" placeholder="Модель блока" />
                      </label>
                      <label class="field-label">
                        Серийный номер
                        <input v-model="componentForm.serial" class="field-input" placeholder="SN..." />
                      </label>
                      <label class="field-label">
                        Инвентарный номер
                        <input v-model="componentForm.inventory_number" class="field-input" placeholder="Если ведется у клиента" />
                      </label>
                      <label class="field-label">
                        ID товара каталога
                        <input v-model="componentForm.catalog_product_id" class="field-input" inputmode="numeric" placeholder="Опционально" />
                      </label>
                      <label class="field-label">
                        ID поставщика
                        <input v-model="componentForm.supplier_id" class="field-input" inputmode="numeric" placeholder="Опционально" />
                      </label>
                      <label class="field-label">
                        Накладная поставщика
                        <input v-model="componentForm.supplier_invoice_number" class="field-input" placeholder="Номер документа" />
                      </label>
                      <label class="field-label">
                        Дата накладной
                        <input v-model="componentForm.supplier_invoice_date" class="field-input" type="date" />
                      </label>
                      <label class="field-label md:col-span-2">
                        Заметки
                        <textarea v-model="componentForm.notes" class="field-input min-h-[58px]" />
                      </label>
                    </div>
                    <div class="mt-3 flex flex-wrap justify-end gap-2">
                      <button class="btn-mini-outline" type="button" :disabled="componentSaving" @click="showComponentForm = false">Отмена</button>
                      <button class="btn-mini" type="submit" :disabled="componentSaving">
                        {{ componentSaving ? 'Сохраняем...' : (editingComponentId ? 'Сохранить блок' : 'Добавить блок') }}
                      </button>
                    </div>
                  </form>

                  <div class="mt-3 space-y-2">
                    <div
                      v-for="component in selectedEquipmentDetail.components || []"
                      :key="component.id"
                      class="rounded-xl border border-[var(--mv-border)] bg-[var(--mv-surface)] p-3 text-sm"
                      :class="component.is_archived ? 'opacity-60' : ''"
                    >
                      <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                        <div class="min-w-0">
                          <div class="flex flex-wrap items-center gap-2">
                            <span class="rounded-full bg-teal-500/10 px-2 py-0.5 text-xs font-semibold text-teal-400">{{ componentTypeLabel(component.component_type) }}</span>
                            <span v-if="component.is_archived" class="rounded-full bg-slate-500/20 px-2 py-0.5 text-xs font-semibold text-slate-400">Архив</span>
                          </div>
                          <p class="mt-2 break-words font-semibold text-[var(--mv-text)]">{{ componentTitle(component) }}</p>
                          <p class="mt-1 break-words text-xs text-[var(--mv-text-muted)]">{{ componentLine(component) }}</p>
                          <p v-if="component.notes" class="mt-1 break-words text-xs text-[var(--mv-text-muted)]">{{ component.notes }}</p>
                        </div>
                        <div class="flex shrink-0 flex-wrap gap-2">
                          <button class="btn-mini-outline text-xs" type="button" @click="openComponentEditForm(component)">Править</button>
                          <button class="btn-mini-outline text-xs" type="button" :disabled="componentActionId === component.id" @click="toggleEquipmentComponentArchive(component)">
                            {{ componentActionId === component.id ? '...' : (component.is_archived ? 'Вернуть' : 'Архив') }}
                          </button>
                        </div>
                      </div>
                    </div>
                    <div v-if="!(selectedEquipmentDetail.components || []).length" class="rounded-xl border border-dashed border-[var(--mv-border)] px-3 py-4 text-center text-sm text-[var(--mv-text-muted)]">
                      Блоки и серийные номера пока не добавлены
                    </div>
                  </div>
                </div>

                <form v-if="showHistoryForm" class="mt-4 rounded-xl border border-[var(--mv-border)] bg-[var(--mv-panel)] p-3" @submit.prevent="createEquipmentHistory">
                  <div class="grid gap-3 md:grid-cols-2">
                    <label class="field-label">
                      Тип события
                      <select v-model="historyForm.event_type" class="field-input">
                        <option v-for="option in EQUIPMENT_EVENT_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
                      </select>
                    </label>
                    <label class="field-label">
                      Дата
                      <input v-model="historyForm.event_date" class="field-input" type="date" />
                    </label>
                    <label class="field-label md:col-span-2">
                      Жалоба / причина
                      <textarea v-model="historyForm.complaint_snapshot" class="field-input min-h-[58px]" />
                    </label>
                    <label class="field-label">
                      Диагностика
                      <textarea v-model="historyForm.diagnostic_result" class="field-input min-h-[70px]" />
                    </label>
                    <label class="field-label">
                      Рекомендация
                      <textarea v-model="historyForm.repair_recommendation" class="field-input min-h-[70px]" />
                    </label>
                    <label class="field-label">
                      Хладагент
                      <input v-model="historyForm.refrigerant_type" class="field-input" />
                    </label>
                    <label class="field-label">
                      Количество
                      <input v-model="historyForm.refrigerant_amount" class="field-input" />
                    </label>
                    <label class="inline-flex items-center gap-2 text-xs text-[var(--mv-text-muted)] md:col-span-2">
                      <input v-model="historyForm.not_repairable" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500" />
                      Оборудование не ремонтируется
                    </label>
                    <label class="field-label md:col-span-2">
                      Причина / заметки
                      <textarea v-model="historyForm.not_repairable_reason" class="field-input min-h-[58px]" placeholder="Причина неремонтопригодности" />
                    </label>
                    <label class="field-label md:col-span-2">
                      Внутренние заметки
                      <textarea v-model="historyForm.notes" class="field-input min-h-[58px]" />
                    </label>
                  </div>
                  <div class="mt-3 flex flex-wrap justify-end gap-2">
                    <button class="btn-mini-outline" type="button" :disabled="historySaving" @click="showHistoryForm = false">Отмена</button>
                    <button class="btn-mini" type="submit" :disabled="historySaving">
                      {{ historySaving ? 'Добавляем...' : 'Добавить' }}
                    </button>
                  </div>
                </form>

                <div class="mt-4 space-y-2">
                  <div
                    v-for="entry in selectedEquipmentDetail.recent_history || []"
                    :key="entry.id"
                    class="rounded-xl border border-[var(--mv-border)] bg-[var(--mv-panel)] p-3 text-sm"
                  >
                    <div class="flex flex-wrap items-center gap-2">
                      <span class="rounded-full bg-teal-500/10 px-2 py-0.5 text-xs font-semibold text-teal-400">{{ equipmentEventLabel(entry.event_type) }}</span>
                      <span class="text-xs text-[var(--mv-text-muted)]">{{ formatDate(entry.event_date) }}</span>
                      <span v-if="entry.order_id" class="text-xs text-[var(--mv-text-muted)]">Заказ #{{ entry.order_id }}</span>
                    </div>
                    <p class="mt-2 break-words text-[var(--mv-text-muted)]">{{ historyLine(entry) }}</p>
                  </div>
                  <div v-if="!(selectedEquipmentDetail.recent_history || []).length" class="rounded-xl border border-dashed border-[var(--mv-border)] px-3 py-4 text-center text-sm text-[var(--mv-text-muted)]">
                    История обслуживания пока пустая
                  </div>
                </div>
              </template>
              <div v-else class="text-sm text-[var(--mv-text-muted)]">Выберите оборудование слева.</div>
            </div>
          </div>
          <div v-else class="rounded-2xl border border-dashed border-[var(--mv-border)] py-5 text-center text-sm italic text-[var(--mv-text-muted)]">
            Оборудование пока не заведено
          </div>
        </section>

        <section v-if="!editMode" class="mt-8 mb-6">
          <h2 class="mb-4 flex items-center gap-2 text-lg font-bold">
            <span class="material-icons-round text-teal-500">folder</span>
            Связанные документы 
            <span v-if="documents.length" class="flex h-6 w-6 items-center justify-center rounded-full bg-teal-500/20 text-xs text-teal-400">{{ documents.length }}</span>
          </h2>

          <div v-if="docsLoading" class="text-sm text-[var(--mv-text-muted)] p-5 border border-dashed border-[var(--mv-border)] rounded-2xl">
            Загрузка документов...
          </div>
          <div v-else-if="documents.length" class="space-y-3">
             <div v-for="doc in documents" :key="doc.id" class="flex items-center justify-between rounded-xl border border-slate-700/50 bg-[#1e293b] p-4 text-slate-300 shadow-sm">
                <div class="flex items-center gap-4">
                    <div class="flex h-12 w-12 items-center justify-center rounded-full bg-slate-800 text-teal-400">
                      <span class="material-icons-round text-2xl">description</span>
                    </div>
                    <div>
                        <div class="flex items-center gap-2 mb-1">
                          <p class="text-[15px] font-semibold text-white leading-none">{{ doc.number || doc.doc_type }}</p>
                          <a :href="`/manager/orders/kanban?orderId=${doc.order_id}`" target="_blank" class="rounded bg-teal-500/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-teal-400 border border-teal-500/20 hover:bg-teal-500/20 hover:text-white transition-colors">Заказ #{{ doc.order_id }}</a>
                        </div>
                        <p class="text-[13px] text-slate-400 leading-none mt-1">{{ new Date(doc.date).toLocaleDateString('ru-RU', { year: 'numeric', month: 'long', day: 'numeric' }) }} · <span class="uppercase font-medium text-slate-300">{{ doc.doc_type }}</span></p>
                    </div>
                </div>
                <div class="flex items-center gap-4">
                    <a v-if="doc.edit_url" :href="doc.edit_url" target="_blank" class="flex h-10 w-10 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-700 hover:text-white transition-colors" title="Открыть документ">
                        <span class="material-icons-round text-[20px]">open_in_new</span>
                    </a>
                </div>
            </div>
          </div>
          <div v-else class="text-sm text-[var(--mv-text-muted)] italic py-5 text-center rounded-2xl border border-dashed border-[var(--mv-border)]">
              Документы пока не найдены
          </div>
        </section>

      </div>

      <CreateOrderModal
        v-if="showCreateOrder && customer"
        :customer-id="customer.id"
        :customer-name="customer.full_legal_name || customer.name || `Клиент #${customer.id}`"
        @close="showCreateOrder = false"
        @created="onOrderCreated"
      />
    </div>
  </div>
</template>

<style scoped>
.detail {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--mv-text-muted);
}

.detail-value {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.detail-value span {
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--mv-text-muted);
}

.detail-value strong {
  color: var(--mv-text);
  font-weight: 600;
  word-break: break-word;
}

.field-input {
  width: 100%;
  border-radius: 0.8rem;
  border: 1px solid var(--mv-border);
  background: var(--mv-surface);
  color: var(--mv-text);
  padding: 0.55rem 0.75rem;
}

.field-input.changed {
  border-color: rgb(20 184 166);
  box-shadow: inset 0 0 0 1px rgb(20 184 166 / 0.3);
}

.field-error {
  margin-top: -0.35rem;
  display: block;
  font-size: 0.72rem;
  color: rgb(252 165 165);
}
</style>
