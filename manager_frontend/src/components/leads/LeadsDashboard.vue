<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { api } from '../../api';
import DateTimeField from '../ui/DateTimeField.vue';
import type {
  LeadCreatePayload,
  LeadLossPayload,
  LeadQualifyPayload,
  ManagerCatalogCustomerItemResponse,
  LeadResponse,
  LeadUpdatePayload,
} from '../../client';
import { useBelarusPhoneMask } from '../../composables/useBelarusPhoneMask';
import { fromLocalDateTimeInput } from '../../utils/datetime';
import { mapCustomerToLeadCreatePrefill, mapCustomerToLeadQualifyPrefill } from '../../utils/customer-mappers';
import { getBankFromLookup, getCompanyFromEgr, normalizeIban, normalizeUnp } from '../../utils/legal-requisites';
import { normalizePhoneDigits, normalizePhoneForApi } from '../../utils/phone';
import { getApiErrorMessage, parseApiFieldErrors } from '../../utils/api-errors';
import {
  normalizeEmail,
  validateOptionalBelarusPhone,
  validateOptionalByIban,
  validateOptionalByUnp,
  validateOptionalEmail,
} from '../../utils/validation';
import { CUSTOMER_UPDATED_EVENT, type CustomerUpdatedEventPayload } from '../../utils/customer-events';

type LeadTab = '' | 'new' | 'contacted' | 'qualified' | 'lost' | 'spam';
type RequisiteFieldKey = 'inn' | 'full_legal_name' | 'legal_address' | 'iban' | 'bic' | 'bank_name';

const leads = ref<LeadResponse[]>([]);
const loading = ref(false);
const saving = ref(false);
const toast = ref('');
const search = ref('');
const source = ref('');
const overdueOnly = ref(false);
const includeArchived = ref(false);
const sort = ref('created_at_desc');
const statusTab = ref<LeadTab>('');

const showCreateModal = ref(false);
const showQualifyModal = ref(false);
const selectedLead = ref<LeadResponse | null>(null);
const selectedExistingCustomer = ref<ManagerCatalogCustomerItemResponse | null>(null);
const createSuggestedCustomer = ref<ManagerCatalogCustomerItemResponse | null>(null);
const selectedQualifyCustomer = ref<ManagerCatalogCustomerItemResponse | null>(null);
const selectedQualifyCustomerDetail = ref<ManagerCatalogCustomerItemResponse | null>(null);
const qualifyOverwriteFields = ref<Record<RequisiteFieldKey, boolean>>({
  inn: false,
  full_legal_name: false,
  legal_address: false,
  iban: false,
  bic: false,
  bank_name: false,
});
const createSuggestionDismissedForId = ref<number | null>(null);
const lastQualifyResult = ref<{
  leadId: number;
  customerId: number;
  orderId: number;
  leadStatus: string;
  segmentHint: string;
  orderStatus: string;
} | null>(null);
const createPhoneError = ref('');
const createEmailError = ref('');
const createInnError = ref('');
const createRequestError = ref('');
const qualifyPhoneError = ref('');
const qualifyEmailError = ref('');
const qualifyInnError = ref('');
const qualifyIbanError = ref('');
const createServerErrors = ref<Record<string, string>>({});
const qualifyServerErrors = ref<Record<string, string>>({});
const qualifyCriticalOverwriteRows = ref<Array<{ key: RequisiteFieldKey; label: string; existing: string; incoming: string }>>([]);
const qualifyCriticalOverwriteConfirmed = ref(false);
const createCompanyLookupLoading = ref(false);
const qualifyCompanyLookupLoading = ref(false);
const qualifyBankLookupLoading = ref(false);
const createPhoneInputRef = ref<HTMLInputElement | null>(null);
const qualifyPhoneInputRef = ref<HTMLInputElement | null>(null);
const customerLookupQuery = ref('');
const customerLookupLoading = ref(false);
const customerLookupResults = ref<ManagerCatalogCustomerItemResponse[]>([]);
const qualifyCustomerLookupQuery = ref('');
const qualifyCustomerLookupLoading = ref(false);
const qualifyCustomerLookupResults = ref<ManagerCatalogCustomerItemResponse[]>([]);
const pendingOpenLeadId = ref<number | null>(null);
const openedByUrlLeadId = ref<number | null>(null);

const createForm = ref<LeadCreatePayload>({
  source: 'manager',
  request_text: '',
  name: '',
  phone: '',
  email: '',
  inn: '',
  company_name: '',
  next_followup_date: undefined,
});

const qualifyForm = ref<LeadQualifyPayload>({
  name: '',
  phone: '',
  email: '',
  inn: '',
  full_legal_name: '',
  legal_address: '',
  iban: '',
  bic: '',
  bank_name: '',
  delivery_address: '',
  order_comment: '',
});

const createPhoneModel = computed({
  get: () => createForm.value.phone ?? '',
  set: (value: string) => {
    createForm.value.phone = value;
  },
});

const qualifyPhoneModel = computed({
  get: () => qualifyForm.value.phone ?? '',
  set: (value: string) => {
    qualifyForm.value.phone = value;
  },
});

const createPhoneMask = useBelarusPhoneMask(createPhoneInputRef, createPhoneModel);
const qualifyPhoneMask = useBelarusPhoneMask(qualifyPhoneInputRef, qualifyPhoneModel);

const statusLabels: Record<string, string> = {
  new: 'Новый',
  contacted: 'Связались',
  qualified: 'Квалифицирован',
  lost: 'Отказ',
  spam: 'Спам',
};

const sourceLabels: Record<string, string> = {
  phone: 'Телефон',
  site: 'Сайт',
  bot: 'Бот',
  email: 'Email',
  manager: 'Менеджер',
  other: 'Другое',
};

const segmentLabels: Record<string, string> = {
  unknown: 'Не определен',
  b2c: 'B2C',
  b2b: 'B2B',
};

const customerTypeLabels: Record<string, string> = {
  company: 'Юрлицо',
  individual: 'Физлицо',
};

const orderStatusLabels: Record<string, string> = {
  new_lead: 'Новый лид',
};

const tabItems = computed(() => [
  { key: '', label: 'Активные' },
  { key: 'new', label: 'Новые' },
  { key: 'contacted', label: 'Связались' },
  { key: 'qualified', label: 'Квалифицированы' },
  { key: 'lost', label: 'Отказы' },
  { key: 'spam', label: 'Спам' },
]);

const qualifyPreview = computed(() => {
  const selectedCustomerId = selectedQualifyCustomer.value?.id;
  const normalizedInn = normalizeUnp(qualifyForm.value.inn || '');
  const normalizedPhone = normalizePhoneDigits(qualifyForm.value.phone || '');
  const normalizedEmail = (qualifyForm.value.email || '').trim().toLowerCase();
  const hasCompanyAttrs = Boolean(normalizedInn || (qualifyForm.value.full_legal_name || '').trim());
  const predictedCustomerType = hasCompanyAttrs ? 'company' : 'individual';
  const predictedSegment = hasCompanyAttrs ? 'b2b' : 'b2c';
  const matchedBy = normalizedInn ? 'inn' : normalizedPhone ? 'phone' : normalizedEmail ? 'email' : null;
  const requisitesToWrite: Array<{ key: string; label: string; value: string }> = [];
  const legalAddress = (qualifyForm.value.legal_address || '').trim();
  const iban = normalizeIban(qualifyForm.value.iban || '');
  const bic = (qualifyForm.value.bic || '').trim();
  const bankName = (qualifyForm.value.bank_name || '').trim();
  const deliveryAddress = (qualifyForm.value.delivery_address || '').trim();
  if (legalAddress) requisitesToWrite.push({ key: 'legal_address', label: 'Юридический адрес', value: legalAddress });
  if (iban) requisitesToWrite.push({ key: 'iban', label: 'IBAN', value: iban });
  if (bic) requisitesToWrite.push({ key: 'bic', label: 'BIC', value: bic });
  if (bankName) requisitesToWrite.push({ key: 'bank_name', label: 'Банк', value: bankName });
  if (deliveryAddress) requisitesToWrite.push({ key: 'delivery_address', label: 'Адрес доставки', value: deliveryAddress });

  return {
    customerId: selectedCustomerId,
    customerMode: selectedCustomerId ? 'reuse' : 'create_or_match',
    customerLabel: selectedCustomerId ? `используется #${selectedCustomerId}` : 'будет найден/создан автоматически',
    predictedCustomerType,
    predictedSegment,
    matchedBy,
    requisitesToWrite,
    inn: normalizedInn || null,
    phoneDigits: normalizedPhone || null,
    email: normalizedEmail || null,
  };
});

const setToast = (message: string) => {
  toast.value = message;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 3000);
};

const formatDate = (value?: string | null) => {
  if (!value) return '—';
  return new Date(value).toLocaleString('ru-RU');
};

const isOverdue = (lead: LeadResponse) => {
  if (!lead.next_followup_date) return false;
  return new Date(lead.next_followup_date).getTime() < Date.now();
};

const FIELD_LABELS: Record<string, string> = {
  source: 'Источник',
  name: 'Имя / Компания',
  phone: 'Телефон',
  email: 'Email',
  inn: 'УНП',
  company_name: 'Полное название компании',
  next_followup_date: 'Следующее касание',
  request_text: 'Запрос',
  full_legal_name: 'Полное наименование',
  legal_address: 'Юридический адрес',
  iban: 'IBAN',
  bic: 'BIC',
  bank_name: 'Название банка',
  delivery_address: 'Адрес доставки/монтажа',
  order_comment: 'Комментарий сделки',
};

const getFieldLabel = (field: string): string => FIELD_LABELS[field] || field;
const REQUISITE_FIELDS: Array<{ key: RequisiteFieldKey; label: string }> = [
  { key: 'inn', label: 'УНП' },
  { key: 'full_legal_name', label: 'Полное наименование' },
  { key: 'legal_address', label: 'Юридический адрес' },
  { key: 'iban', label: 'IBAN' },
  { key: 'bic', label: 'BIC' },
  { key: 'bank_name', label: 'Банк' },
];

const normalizeRequisiteValue = (key: RequisiteFieldKey, value: string): string => {
  if (key === 'inn') return normalizeUnp(value);
  if (key === 'iban') return normalizeIban(value);
  return value.trim();
};

const getExistingRequisiteValue = (key: RequisiteFieldKey): string => {
  const value = selectedQualifyCustomerDetail.value?.[key];
  return typeof value === 'string' ? value : '';
};

const getIncomingRequisiteValue = (key: RequisiteFieldKey): string => {
  const value = qualifyForm.value[key];
  return typeof value === 'string' ? value : '';
};

const isRequisiteChanged = (key: RequisiteFieldKey): boolean => {
  const existing = normalizeRequisiteValue(key, getExistingRequisiteValue(key));
  const incoming = normalizeRequisiteValue(key, getIncomingRequisiteValue(key));
  return Boolean(existing && incoming && existing !== incoming);
};

const canWriteRequisiteByDefault = (key: RequisiteFieldKey): boolean => {
  const existing = normalizeRequisiteValue(key, getExistingRequisiteValue(key));
  const incoming = normalizeRequisiteValue(key, getIncomingRequisiteValue(key));
  if (!incoming) return false;
  if (!existing) return true;
  if (existing === incoming) return true;
  return qualifyOverwriteFields.value[key];
};

const qualifyChangedRequisites = computed(() =>
  REQUISITE_FIELDS
    .filter(({ key }) => isRequisiteChanged(key))
    .map(({ key, label }) => ({
      key,
      label,
      existing: getExistingRequisiteValue(key).trim() || '—',
      incoming: getIncomingRequisiteValue(key).trim() || '—',
      overwrite: qualifyOverwriteFields.value[key],
    })),
);

const qualifyWriteSummary = computed(() =>
  REQUISITE_FIELDS
    .filter(({ key }) => canWriteRequisiteByDefault(key))
    .map(({ key, label }) => ({
      key,
      label,
      value: getIncomingRequisiteValue(key).trim(),
      mode: isRequisiteChanged(key) ? 'overwrite' : 'fill_or_keep',
    })),
);

const loadLeads = async () => {
  loading.value = true;
  try {
    const response = await api.getManagerLeads({
      page: 1,
      limit: 100,
      status: statusTab.value || undefined,
      source: source.value || undefined,
      search: search.value || undefined,
      overdueOnly: overdueOnly.value,
      includeArchived: includeArchived.value,
      sort: sort.value,
    });
    leads.value = response.items;
    if (pendingOpenLeadId.value && openedByUrlLeadId.value !== pendingOpenLeadId.value) {
      const leadToOpen = leads.value.find((item) => item.id === pendingOpenLeadId.value);
      if (leadToOpen) {
        openQualifyModal(leadToOpen, false);
        openedByUrlLeadId.value = pendingOpenLeadId.value;
      }
    }
  } catch (error) {
    console.error(error);
    setToast(`Не удалось загрузить лиды: ${getApiErrorMessage(error)}`);
  } finally {
    loading.value = false;
  }
};

const resetCreateForm = () => {
  createForm.value = {
    source: 'manager',
    request_text: '',
    name: '',
    phone: '',
    email: '',
    inn: '',
    company_name: '',
    next_followup_date: undefined,
  };
  selectedExistingCustomer.value = null;
  createSuggestedCustomer.value = null;
  createSuggestionDismissedForId.value = null;
  customerLookupQuery.value = '';
  customerLookupResults.value = [];
  createPhoneError.value = '';
  createEmailError.value = '';
  createInnError.value = '';
  createRequestError.value = '';
  createServerErrors.value = {};
};

const submitCreateLead = async () => {
  if (saving.value) return;
  createServerErrors.value = {};
  createPhoneError.value = validateOptionalBelarusPhone(createForm.value.phone || '', createPhoneMask.isComplete.value);
  createEmailError.value = validateOptionalEmail(createForm.value.email || '');
  createInnError.value = validateOptionalByUnp(createForm.value.inn || '');
  if (createPhoneError.value) {
    setToast(createPhoneError.value);
    return;
  }
  if (createEmailError.value) {
    setToast(createEmailError.value);
    return;
  }
  if (createInnError.value) {
    setToast(createInnError.value);
    return;
  }
  const requestText = (createForm.value.request_text || '').trim();
  createRequestError.value = requestText ? '' : 'Заполните поле "Запрос"';
  if (createRequestError.value) {
    setToast(createRequestError.value);
    return;
  }
  saving.value = true;
  try {
    const normalizedPhone = createForm.value.phone ? normalizePhoneForApi(createForm.value.phone) : undefined;
    const payload: LeadCreatePayload = {
      ...createForm.value,
      request_text: requestText,
      name: createForm.value.name || undefined,
      phone: normalizedPhone || undefined,
      email: normalizeEmail(createForm.value.email || '') || undefined,
      inn: normalizeUnp(createForm.value.inn || '') || undefined,
      company_name: createForm.value.company_name || undefined,
      next_followup_date: fromLocalDateTimeInput(createForm.value.next_followup_date || undefined) || undefined,
    };
    await api.createManagerLead(payload);
    showCreateModal.value = false;
    resetCreateForm();
    setToast('Лид создан');
    await loadLeads();
  } catch (error) {
    console.error(error);
    const parsed = parseApiFieldErrors(error, [
      'source',
      'name',
      'phone',
      'email',
      'inn',
      'company_name',
      'next_followup_date',
      'request_text',
    ]);
    createServerErrors.value = parsed.fieldErrors;
    if (!createPhoneError.value && parsed.fieldErrors.phone) createPhoneError.value = parsed.fieldErrors.phone;
    if (!createEmailError.value && parsed.fieldErrors.email) createEmailError.value = parsed.fieldErrors.email;
    if (!createInnError.value && parsed.fieldErrors.inn) createInnError.value = parsed.fieldErrors.inn;
    if (!createRequestError.value && parsed.fieldErrors.request_text) createRequestError.value = parsed.fieldErrors.request_text;
    setToast(`Не удалось создать лид: ${parsed.message}`);
  } finally {
    saving.value = false;
  }
};

const updateLead = async (leadId: number, payload: LeadUpdatePayload, successToast?: string) => {
  if (saving.value) return;
  saving.value = true;
  try {
    await api.patchManagerLead(leadId, payload);
    if (successToast) setToast(successToast);
    await loadLeads();
  } catch (error) {
    console.error(error);
    setToast(`Не удалось обновить лид: ${getApiErrorMessage(error)}`);
  } finally {
    saving.value = false;
  }
};

const markLost = async (lead: LeadResponse, status: 'lost' | 'spam') => {
  if (saving.value) return;
  saving.value = true;
  try {
    const payload: LeadLossPayload = {
      status,
      loss_reason: status === 'spam' ? 'spam' : 'other',
    };
    await api.markManagerLeadLost(lead.id, payload);
    setToast(status === 'spam' ? 'Лид отмечен как спам' : 'Лид переведен в отказы');
    await loadLeads();
  } catch (error) {
    console.error(error);
    setToast(`Не удалось обновить статус: ${getApiErrorMessage(error)}`);
  } finally {
    saving.value = false;
  }
};

const openQualifyModal = (lead: LeadResponse, updateUrl = true) => {
  selectedLead.value = lead;
  selectedQualifyCustomer.value = null;
  selectedQualifyCustomerDetail.value = null;
  qualifyOverwriteFields.value = {
    inn: false,
    full_legal_name: false,
    legal_address: false,
    iban: false,
    bic: false,
    bank_name: false,
  };
  qualifyCustomerLookupQuery.value = '';
  qualifyCustomerLookupResults.value = [];
  qualifyForm.value = {
    name: lead.name || '',
    phone: lead.phone ? normalizePhoneForApi(lead.phone) : '',
    email: lead.email || '',
    inn: lead.inn || '',
    full_legal_name: lead.company_name || '',
    legal_address: '',
    iban: '',
    bic: '',
    bank_name: '',
    delivery_address: '',
    order_comment: lead.request_text,
  };
  qualifyPhoneError.value = '';
  qualifyEmailError.value = '';
  qualifyInnError.value = '';
  qualifyIbanError.value = '';
  qualifyServerErrors.value = {};
  qualifyCriticalOverwriteRows.value = [];
  qualifyCriticalOverwriteConfirmed.value = false;
  if (updateUrl) {
    const url = new URL(window.location.href);
    url.searchParams.set('leadId', String(lead.id));
    window.history.replaceState({}, '', `${url.pathname}${url.search}`);
    pendingOpenLeadId.value = lead.id;
    openedByUrlLeadId.value = lead.id;
  }
  showQualifyModal.value = true;
  void autoHydrateQualifyFormByLeadIdentity();
};

const clearQualifyCriticalOverwriteConfirm = () => {
  qualifyCriticalOverwriteRows.value = [];
  qualifyCriticalOverwriteConfirmed.value = false;
};

const qualifyLead = async () => {
  if (!selectedLead.value || saving.value) return;
  qualifyServerErrors.value = {};
  qualifyPhoneError.value = validateOptionalBelarusPhone(qualifyForm.value.phone || '', qualifyPhoneMask.isComplete.value);
  qualifyEmailError.value = validateOptionalEmail(qualifyForm.value.email || '');
  qualifyInnError.value = validateOptionalByUnp(qualifyForm.value.inn || '');
  qualifyIbanError.value = validateOptionalByIban(qualifyForm.value.iban || '');
  if (qualifyPhoneError.value) {
    setToast(qualifyPhoneError.value);
    return;
  }
  if (qualifyEmailError.value) {
    setToast(qualifyEmailError.value);
    return;
  }
  if (qualifyInnError.value) {
    setToast(qualifyInnError.value);
    return;
  }
  if (qualifyIbanError.value) {
    setToast(qualifyIbanError.value);
    return;
  }
  saving.value = true;
  try {
    const normalizedPhone = qualifyForm.value.phone ? normalizePhoneForApi(qualifyForm.value.phone) : undefined;
    const criticalOverwriteRows = qualifyChangedRequisites.value.filter(
      (row) =>
        ['inn', 'iban', 'bic', 'bank_name'].includes(row.key) &&
        qualifyOverwriteFields.value[row.key],
    );
    if (criticalOverwriteRows.length && !qualifyCriticalOverwriteConfirmed.value) {
      qualifyCriticalOverwriteRows.value = criticalOverwriteRows;
      setToast('Подтвердите перезапись критичных реквизитов в блоке ниже');
      saving.value = false;
      return;
    }
    clearQualifyCriticalOverwriteConfirm();
    const resolveRequisite = (key: RequisiteFieldKey): string | undefined => {
      const incoming = normalizeRequisiteValue(key, getIncomingRequisiteValue(key));
      if (!incoming) return undefined;
      if (!selectedQualifyCustomerDetail.value) return incoming;
      if (canWriteRequisiteByDefault(key)) return incoming;
      return undefined;
    };
    const response = await api.qualifyManagerLead(selectedLead.value.id, {
      ...qualifyForm.value,
      customer_id: selectedQualifyCustomer.value?.id || undefined,
      name: qualifyForm.value.name || undefined,
      phone: normalizedPhone || undefined,
      email: normalizeEmail(qualifyForm.value.email || '') || undefined,
      inn: resolveRequisite('inn'),
      full_legal_name: resolveRequisite('full_legal_name'),
      legal_address: resolveRequisite('legal_address'),
      iban: resolveRequisite('iban'),
      bic: resolveRequisite('bic'),
      bank_name: resolveRequisite('bank_name'),
      delivery_address: qualifyForm.value.delivery_address || undefined,
      order_comment: qualifyForm.value.order_comment || undefined,
    });
    lastQualifyResult.value = {
      leadId: selectedLead.value.id,
      customerId: response.customer_id,
      orderId: response.order_id,
      leadStatus: response.lead.status,
      segmentHint: response.lead.segment_hint,
      orderStatus: 'new_lead',
    };
    showQualifyModal.value = false;
    setToast(`Лид квалифицирован. Сделка #${response.order_id}, клиент #${response.customer_id}`);
    await loadLeads();
  } catch (error) {
    console.error(error);
    const parsed = parseApiFieldErrors(error, [
      'name',
      'phone',
      'email',
      'inn',
      'full_legal_name',
      'legal_address',
      'iban',
      'bic',
      'bank_name',
      'delivery_address',
      'order_comment',
    ]);
    qualifyServerErrors.value = parsed.fieldErrors;
    if (!qualifyPhoneError.value && parsed.fieldErrors.phone) qualifyPhoneError.value = parsed.fieldErrors.phone;
    if (!qualifyEmailError.value && parsed.fieldErrors.email) qualifyEmailError.value = parsed.fieldErrors.email;
    if (!qualifyInnError.value && parsed.fieldErrors.inn) qualifyInnError.value = parsed.fieldErrors.inn;
    if (!qualifyIbanError.value && parsed.fieldErrors.iban) qualifyIbanError.value = parsed.fieldErrors.iban;
    setToast(`Не удалось квалифицировать лид: ${parsed.message}`);
  } finally {
    saving.value = false;
    qualifyCriticalOverwriteConfirmed.value = false;
  }
};

const navigateToOrders = (orderId?: number | null) => {
  const path = orderId
    ? `/manager/orders/kanban?orderId=${encodeURIComponent(String(orderId))}`
    : '/manager/orders/kanban';
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
  if (orderId) setToast(`Открыта сделка #${orderId}.`);
};

const navigateToCustomerProfile = (customer?: { id?: number | null } | null) => {
  const customerId = customer?.id ? String(customer.id) : '';
  const path = customerId
    ? `/manager/customers/profile?customerId=${encodeURIComponent(customerId)}`
    : '/manager/customers';
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
  if (customer?.id) {
    setToast(`Открыта карточка клиента #${customer.id}.`);
  }
};

const clearLeadIdFromUrl = () => {
  const url = new URL(window.location.href);
  if (!url.searchParams.has('leadId')) return;
  url.searchParams.delete('leadId');
  window.history.replaceState({}, '', `${url.pathname}${url.search}`);
};

let searchTimer: number | undefined;
let customerLookupTimer: number | undefined;
let qualifyCustomerLookupTimer: number | undefined;
watch([statusTab, source, overdueOnly, includeArchived, sort], async () => {
  await loadLeads();
});
watch(search, () => {
  if (searchTimer) window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(async () => {
    await loadLeads();
  }, 300);
});
watch(customerLookupQuery, () => {
  if (customerLookupTimer) window.clearTimeout(customerLookupTimer);
  customerLookupTimer = window.setTimeout(async () => {
    await findExistingCustomers();
  }, 250);
});
watch(qualifyCustomerLookupQuery, () => {
  if (qualifyCustomerLookupTimer) window.clearTimeout(qualifyCustomerLookupTimer);
  qualifyCustomerLookupTimer = window.setTimeout(async () => {
    await findCustomersForQualify();
  }, 250);
});

onMounted(async () => {
  const leadIdParam = new URLSearchParams(window.location.search).get('leadId');
  if (leadIdParam) {
    const parsed = Number(leadIdParam);
    if (Number.isFinite(parsed) && parsed > 0) {
      pendingOpenLeadId.value = parsed;
    }
  }
  await loadLeads();
  window.addEventListener(CUSTOMER_UPDATED_EVENT, handleCustomerUpdated);
});

onUnmounted(() => {
  window.removeEventListener(CUSTOMER_UPDATED_EVENT, handleCustomerUpdated);
});

watch(showQualifyModal, (isOpen) => {
  if (isOpen) {
    qualifyServerErrors.value = {};
    qualifyEmailError.value = '';
    qualifyInnError.value = '';
    qualifyIbanError.value = '';
    clearQualifyCriticalOverwriteConfirm();
    return;
  }
  if (!isOpen) {
    selectedQualifyCustomerDetail.value = null;
    clearQualifyCriticalOverwriteConfirm();
    clearLeadIdFromUrl();
    openedByUrlLeadId.value = null;
  }
});

watch(showCreateModal, (isOpen) => {
  if (isOpen) {
    createServerErrors.value = {};
    createPhoneError.value = '';
    createEmailError.value = '';
    createInnError.value = '';
    createRequestError.value = '';
  }
});

const validateCreatePhoneOnBlur = () => {
  createPhoneError.value = validateOptionalBelarusPhone(createForm.value.phone || '', createPhoneMask.isComplete.value);
};

const validateQualifyPhoneOnBlur = () => {
  qualifyPhoneError.value = validateOptionalBelarusPhone(qualifyForm.value.phone || '', qualifyPhoneMask.isComplete.value);
};

const applyCustomerRequisitesToQualifyForm = (customer: ManagerCatalogCustomerItemResponse) => {
  const mapped = mapCustomerToLeadQualifyPrefill(customer);
  qualifyForm.value.full_legal_name = mapped.full_legal_name || qualifyForm.value.full_legal_name;
  qualifyForm.value.legal_address = mapped.legal_address || qualifyForm.value.legal_address;
  qualifyForm.value.iban = mapped.iban || qualifyForm.value.iban;
  qualifyForm.value.bic = mapped.bic || qualifyForm.value.bic;
  qualifyForm.value.bank_name = mapped.bank_name || qualifyForm.value.bank_name;
  qualifyForm.value.delivery_address = mapped.delivery_address || qualifyForm.value.delivery_address;
};

const hydrateQualifyRequisitesFromCustomer = async (customerId: number) => {
  try {
    const customer = await api.getManagerCustomerDetail(customerId);
    selectedQualifyCustomerDetail.value = customer;
    applyCustomerRequisitesToQualifyForm(customer);
  } catch (error) {
    console.error(error);
  }
};

const applyCustomerToCreateForm = (customer: ManagerCatalogCustomerItemResponse) => {
  selectedExistingCustomer.value = customer;
  createSuggestedCustomer.value = null;
  createSuggestionDismissedForId.value = null;
  customerLookupQuery.value = customer.full_legal_name || customer.name || `Клиент #${customer.id}`;
  const mapped = mapCustomerToLeadCreatePrefill(customer);
  createForm.value.name = mapped.name || createForm.value.name;
  createForm.value.phone = mapped.phone || createForm.value.phone;
  createForm.value.email = mapped.email || createForm.value.email;
  createForm.value.inn = mapped.inn || createForm.value.inn;
  createForm.value.company_name = mapped.company_name || createForm.value.company_name;
  customerLookupResults.value = [];
};

const syncQualifyFormWithUpdatedCustomer = (
  previous: ManagerCatalogCustomerItemResponse | null,
  updated: ManagerCatalogCustomerItemResponse,
) => {
  const prevMapped = previous ? mapCustomerToLeadQualifyPrefill(previous) : {};
  const nextMapped = mapCustomerToLeadQualifyPrefill(updated);
  const keys: (keyof LeadQualifyPayload)[] = [
    'name',
    'phone',
    'email',
    'inn',
    'full_legal_name',
    'legal_address',
    'iban',
    'bic',
    'bank_name',
    'delivery_address',
  ];

  for (const key of keys) {
    const current = (qualifyForm.value[key] || '').toString().trim();
    const before = ((prevMapped[key] as string | undefined) || '').toString().trim();
    const after = ((nextMapped[key] as string | undefined) || '').toString().trim();
    if (!current || current === before) {
      // Keep user edits intact, but refresh unchanged values from latest profile.
      (qualifyForm.value as Record<string, string | undefined>)[key] = after || undefined;
    }
  }
};

const handleCustomerUpdated = (event: Event) => {
  const detail = (event as CustomEvent<CustomerUpdatedEventPayload>).detail;
  const updated = detail?.customer;
  if (!updated) return;

  if (selectedExistingCustomer.value?.id === updated.id) {
    selectedExistingCustomer.value = updated;
    applyCustomerToCreateForm(updated);
  }

  if (createSuggestedCustomer.value?.id === updated.id) {
    createSuggestedCustomer.value = updated;
  }

  if (selectedQualifyCustomer.value?.id === updated.id || selectedQualifyCustomerDetail.value?.id === updated.id) {
    const previous = selectedQualifyCustomerDetail.value;
    selectedQualifyCustomer.value = updated;
    selectedQualifyCustomerDetail.value = updated;
    syncQualifyFormWithUpdatedCustomer(previous, updated);
  }
};

const suggestCustomerForCreate = (customer: ManagerCatalogCustomerItemResponse) => {
  if (selectedExistingCustomer.value?.id === customer.id) return;
  if (createSuggestionDismissedForId.value === customer.id) return;
  createSuggestedCustomer.value = customer;
};

const dismissCreateCustomerSuggestion = () => {
  createSuggestionDismissedForId.value = createSuggestedCustomer.value?.id || null;
  createSuggestedCustomer.value = null;
};

const isCustomerMatchByIdentity = (
  customer: ManagerCatalogCustomerItemResponse,
  identity: { inn?: string; email?: string; phoneDigits?: string },
): boolean => {
  const customerInn = normalizeUnp(customer.inn || '');
  const customerEmail = (customer.email || '').trim().toLowerCase();
  const customerPhoneDigits = normalizePhoneDigits(customer.phone || '');

  if (identity.inn && customerInn && identity.inn === customerInn) return true;
  if (identity.email && customerEmail && identity.email === customerEmail) return true;
  if (identity.phoneDigits && customerPhoneDigits && identity.phoneDigits === customerPhoneDigits) return true;
  return false;
};

const getCustomerIdentityMatchPriority = (
  customer: ManagerCatalogCustomerItemResponse,
  identity: { inn?: string; email?: string; phoneDigits?: string },
): number => {
  const customerInn = normalizeUnp(customer.inn || '');
  const customerPhoneDigits = normalizePhoneDigits(customer.phone || '');
  const customerEmail = (customer.email || '').trim().toLowerCase();

  if (identity.inn && customerInn && identity.inn === customerInn) return 3;
  if (identity.phoneDigits && customerPhoneDigits && identity.phoneDigits === customerPhoneDigits) return 2;
  if (identity.email && customerEmail && identity.email === customerEmail) return 1;
  return 0;
};

const customerDataCompletenessScore = (customer: ManagerCatalogCustomerItemResponse): number => {
  let score = 0;
  if (customer.full_legal_name) score += 2;
  if (customer.legal_address) score += 3;
  if (customer.bank_name) score += 3;
  if (customer.bic) score += 3;
  if (customer.iban) score += 4;
  if (customer.order_count > 0) score += 1;
  return score;
};

const findCustomerByIdentity = async (identity: { inn?: string; email?: string; phoneDigits?: string }) => {
  const query = identity.inn || identity.phoneDigits || identity.email;
  if (!query) return null;

  const response = await api.getManagerCustomers(1, 100, query, undefined, false);
  const items = response.items || [];
  const exactMatches = items.filter((item) => isCustomerMatchByIdentity(item, identity));
  if (!exactMatches.length) return null;

  exactMatches.sort((a, b) => {
    const priorityDiff = getCustomerIdentityMatchPriority(b, identity) - getCustomerIdentityMatchPriority(a, identity);
    if (priorityDiff !== 0) return priorityDiff;
    return customerDataCompletenessScore(b) - customerDataCompletenessScore(a);
  });
  return exactMatches[0];
};

const findExistingCustomers = async () => {
  const query = customerLookupQuery.value.trim();
  if (query.length < 2) {
    customerLookupResults.value = [];
    return;
  }

  customerLookupLoading.value = true;
  try {
    const data = await api.getManagerCustomers(1, 8, query, undefined, false);
    customerLookupResults.value = data.items || [];
  } catch (error) {
    console.error(error);
    setToast(`Не удалось найти клиентов: ${getApiErrorMessage(error)}`);
  } finally {
    customerLookupLoading.value = false;
  }
};

const applyCustomerToQualifyForm = (customer: ManagerCatalogCustomerItemResponse) => {
  selectedQualifyCustomer.value = customer;
  selectedQualifyCustomerDetail.value = customer;
  qualifyOverwriteFields.value = {
    inn: false,
    full_legal_name: false,
    legal_address: false,
    iban: false,
    bic: false,
    bank_name: false,
  };
  qualifyCustomerLookupQuery.value = customer.full_legal_name || customer.name || `Клиент #${customer.id}`;
  const mapped = mapCustomerToLeadQualifyPrefill(customer);
  qualifyForm.value.name = mapped.name || qualifyForm.value.name;
  qualifyForm.value.phone = mapped.phone || qualifyForm.value.phone;
  qualifyForm.value.email = mapped.email || qualifyForm.value.email;
  qualifyForm.value.inn = mapped.inn || qualifyForm.value.inn;
  qualifyForm.value.full_legal_name = mapped.full_legal_name || qualifyForm.value.full_legal_name;
  qualifyForm.value.delivery_address = mapped.delivery_address || qualifyForm.value.delivery_address;
  applyCustomerRequisitesToQualifyForm(customer);
  qualifyCustomerLookupResults.value = [];
  void hydrateQualifyRequisitesFromCustomer(customer.id);
};

const findCustomersForQualify = async () => {
  const query = qualifyCustomerLookupQuery.value.trim();
  if (query.length < 2) {
    qualifyCustomerLookupResults.value = [];
    return;
  }

  qualifyCustomerLookupLoading.value = true;
  try {
    const data = await api.getManagerCustomers(1, 8, query, undefined, false);
    qualifyCustomerLookupResults.value = data.items || [];
  } catch (error) {
    console.error(error);
    setToast(`Не удалось найти клиентов: ${getApiErrorMessage(error)}`);
  } finally {
    qualifyCustomerLookupLoading.value = false;
  }
};

const onCreateInnBlur = async () => {
  const normalizedUnp = normalizeUnp(createForm.value.inn || '');
  createForm.value.inn = normalizedUnp;
  createInnError.value = validateOptionalByUnp(normalizedUnp);
  if (createInnError.value) return;
  if (normalizedUnp.length !== 9) return;

  try {
    const existing = await findCustomerByIdentity({ inn: normalizedUnp });
    if (existing) {
      suggestCustomerForCreate(existing);
      setToast(`Найден существующий клиент #${existing.id}. Выберите действие в подсказке.`);
      return;
    }
  } catch (error) {
    console.error(error);
  }

  createCompanyLookupLoading.value = true;
  try {
    const response = await api.getCompanyByUnp(normalizedUnp);
    const company = getCompanyFromEgr(response);
    if (company.fullLegalName && !(createForm.value.company_name || '').trim()) {
      createForm.value.company_name = company.fullLegalName;
    }
  } catch (error) {
    console.error(error);
    setToast(`Не удалось получить данные ЕГР: ${getApiErrorMessage(error)}`);
  } finally {
    createCompanyLookupLoading.value = false;
  }
};

const onQualifyInnBlur = async () => {
  const normalizedUnp = normalizeUnp(qualifyForm.value.inn || '');
  qualifyForm.value.inn = normalizedUnp;
  qualifyInnError.value = validateOptionalByUnp(normalizedUnp);
  if (qualifyInnError.value) return;
  if (normalizedUnp.length !== 9) return;

  try {
    const existing = await findCustomerByIdentity({ inn: normalizedUnp });
    if (existing) {
      applyCustomerToQualifyForm(existing);
      setToast(`Найден клиент #${existing.id}, реквизиты подставлены.`);
      return;
    }
  } catch (error) {
    console.error(error);
  }

  qualifyCompanyLookupLoading.value = true;
  try {
    const response = await api.getCompanyByUnp(normalizedUnp);
    const company = getCompanyFromEgr(response);
    if (company.fullLegalName && !(qualifyForm.value.full_legal_name || '').trim()) {
      qualifyForm.value.full_legal_name = company.fullLegalName;
    }
    if (company.legalAddress && !(qualifyForm.value.legal_address || '').trim()) {
      qualifyForm.value.legal_address = company.legalAddress;
    }
  } catch (error) {
    console.error(error);
    setToast(`Не удалось получить данные ЕГР: ${getApiErrorMessage(error)}`);
  } finally {
    qualifyCompanyLookupLoading.value = false;
  }
};

const onCreatePhoneBlur = async () => {
  validateCreatePhoneOnBlur();
  if (createPhoneError.value) return;
  const phoneDigits = normalizePhoneDigits(createForm.value.phone || '');
  if (!phoneDigits) return;

  try {
    const existing = await findCustomerByIdentity({ phoneDigits });
    if (existing) {
      suggestCustomerForCreate(existing);
      setToast(`Найден существующий клиент #${existing.id}. Выберите действие в подсказке.`);
    }
  } catch (error) {
    console.error(error);
  }
};

const onCreateEmailBlur = async () => {
  createEmailError.value = validateOptionalEmail(createForm.value.email || '');
  if (createEmailError.value) return;
  const email = normalizeEmail(createForm.value.email || '');
  if (!email) return;

  try {
    const existing = await findCustomerByIdentity({ email });
    if (existing) {
      suggestCustomerForCreate(existing);
      setToast(`Найден существующий клиент #${existing.id}. Выберите действие в подсказке.`);
    }
  } catch (error) {
    console.error(error);
  }
};

const onQualifyEmailBlur = async () => {
  qualifyEmailError.value = validateOptionalEmail(qualifyForm.value.email || '');
  if (qualifyEmailError.value) return;
  const email = normalizeEmail(qualifyForm.value.email || '');
  if (!email) return;

  try {
    const existing = await findCustomerByIdentity({ email });
    if (existing) {
      applyCustomerToQualifyForm(existing);
      setToast(`Найден клиент #${existing.id}, реквизиты подставлены.`);
    }
  } catch (error) {
    console.error(error);
  }
};

const autoHydrateQualifyFormByLeadIdentity = async () => {
  const inn = normalizeUnp(qualifyForm.value.inn || '');
  const phoneDigits = normalizePhoneDigits(qualifyForm.value.phone || '');
  const email = normalizeEmail(qualifyForm.value.email || '');
  if (!inn && !phoneDigits && !email) return;

  try {
    const existing = await findCustomerByIdentity({ inn: inn || undefined, phoneDigits: phoneDigits || undefined, email: email || undefined });
    if (!existing) return;
    applyCustomerToQualifyForm(existing);
    void hydrateQualifyRequisitesFromCustomer(existing.id);
  } catch (error) {
    console.error(error);
  }
};

const onQualifyIbanBlur = async () => {
  const normalized = normalizeIban(qualifyForm.value.iban || '');
  qualifyForm.value.iban = normalized;
  qualifyIbanError.value = validateOptionalByIban(normalized);
  if (qualifyIbanError.value) return;
  if (normalized.length < 10) return;

  qualifyBankLookupLoading.value = true;
  try {
    const response = await api.getBankBySearch(normalized);
    const bank = getBankFromLookup(response);
    if (bank.bankName && !(qualifyForm.value.bank_name || '').trim()) {
      qualifyForm.value.bank_name = bank.bankName;
    }
    if (bank.bic && !(qualifyForm.value.bic || '').trim()) {
      qualifyForm.value.bic = bank.bic;
    }
  } catch (error) {
    console.error(error);
    setToast(`Не удалось получить данные банка: ${getApiErrorMessage(error)}`);
  } finally {
    qualifyBankLookupLoading.value = false;
  }
};
</script>

<template>
  <div class="min-h-screen bg-[var(--mv-bg)] text-slate-100">
    <div class="mx-auto max-w-[1400px] px-4 py-6 md:px-8">
      <header class="mb-5 rounded-[2rem] border border-slate-700/70 bg-gradient-to-r from-slate-900 to-slate-800 p-5">
        <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h1 class="text-2xl font-bold">Leads Dashboard</h1>
          <button class="btn-mini" @click="showCreateModal = true">Новый лид</button>
        </div>

        <div class="mb-3 flex flex-wrap gap-2">
          <button
            v-for="item in tabItems"
            :key="item.key"
            class="rounded-[12px] px-3 py-1.5 text-sm font-semibold transition"
            :class="statusTab === item.key ? 'bg-[var(--mv-teal)] text-white' : 'bg-slate-800 text-slate-300 hover:text-white'"
            @click="statusTab = item.key as LeadTab"
          >
            {{ item.label }}
          </button>
        </div>

        <div class="grid gap-3 md:grid-cols-5">
          <input v-model="search" class="field-input" placeholder="Поиск: имя, телефон, email, УНП, ID" />
          <select v-model="source" class="field-input">
            <option value="">Все источники</option>
            <option value="phone">Телефон</option>
            <option value="site">Сайт</option>
            <option value="bot">Бот</option>
            <option value="email">Email</option>
            <option value="manager">Менеджер</option>
            <option value="other">Другое</option>
          </select>
          <select v-model="sort" class="field-input">
            <option value="created_at_desc">Новые сверху</option>
            <option value="created_at_asc">Старые сверху</option>
            <option value="updated_at_desc">Недавно обновленные</option>
            <option value="followup_asc">Ближайшее касание</option>
          </select>
          <label class="inline-flex items-center gap-2 rounded-[12px] border border-slate-700 bg-slate-900 px-3 py-2">
            <input v-model="overdueOnly" type="checkbox" />
            Только просроченные
          </label>
          <label class="inline-flex items-center gap-2 rounded-[12px] border border-slate-700 bg-slate-900 px-3 py-2">
            <input v-model="includeArchived" type="checkbox" />
            Показать архив
          </label>
        </div>
      </header>

      <p v-if="toast" class="mb-4 rounded-[12px] bg-[#007f80] px-4 py-2 text-sm font-semibold text-white">{{ toast }}</p>
      <div
        v-if="lastQualifyResult"
        class="mb-4 rounded-[14px] border border-emerald-500/50 bg-emerald-900/20 px-4 py-3 text-sm text-emerald-100"
      >
        <p class="font-semibold">
          Лид #{{ lastQualifyResult.leadId }} квалифицирован: клиент #{{ lastQualifyResult.customerId }}, сделка #{{ lastQualifyResult.orderId }}.
        </p>
        <div class="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-emerald-200/90">
          <span>Статус лида: {{ statusLabels[lastQualifyResult.leadStatus] || lastQualifyResult.leadStatus }}</span>
          <span>Сегмент: {{ segmentLabels[lastQualifyResult.segmentHint] || lastQualifyResult.segmentHint }}</span>
          <span>Статус сделки: {{ orderStatusLabels[lastQualifyResult.orderStatus] || lastQualifyResult.orderStatus }}</span>
        </div>
        <div class="mt-2 flex flex-wrap gap-2">
          <button class="btn-mini" @click="navigateToOrders(lastQualifyResult.orderId)">Открыть сделку</button>
          <button class="btn-mini-outline" @click="navigateToCustomerProfile({ id: lastQualifyResult.customerId })">Открыть клиента</button>
          <button class="btn-mini-outline" @click="lastQualifyResult = null">Скрыть</button>
        </div>
      </div>
      <p v-if="loading" class="mb-4 text-sm text-slate-300">Загрузка лидов...</p>

      <div v-if="!loading && leads.length === 0" class="rounded-[2rem] border border-slate-700 bg-slate-900/60 p-8 text-center">
        <p class="text-lg font-semibold text-white">Лиды не найдены</p>
        <p class="mt-2 text-sm text-slate-400">Попробуйте изменить фильтры или создайте новый лид.</p>
      </div>

      <div v-else class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <article
          v-for="lead in leads"
          :key="lead.id"
          class="rounded-[2rem] border border-slate-700 bg-slate-800 p-5 shadow-lg"
          :class="isOverdue(lead) ? 'ring-2 ring-red-500/70' : 'ring-1 ring-transparent'"
        >
          <header class="mb-3 flex items-start justify-between gap-2">
            <div>
              <p class="text-lg font-semibold text-white">{{ lead.name || lead.company_name || `Лид #${lead.id}` }}</p>
              <p class="text-sm text-slate-300">{{ lead.phone || lead.email || 'Контакт не указан' }}</p>
            </div>
            <span class="rounded-full bg-slate-700 px-2 py-1 text-xs text-slate-200">{{ statusLabels[lead.status] || lead.status }}</span>
          </header>

          <div class="space-y-1 text-sm text-slate-200">
            <p>Источник: <span class="text-slate-300">{{ sourceLabels[lead.source] || lead.source }}</span></p>
            <p>Сегмент: <span class="text-slate-300">{{ segmentLabels[lead.segment_hint] || lead.segment_hint }}</span></p>
            <p v-if="lead.inn">УНП: {{ lead.inn }}</p>
            <p class="line-clamp-3">{{ lead.request_text }}</p>
            <p class="text-xs text-slate-400">След. касание: {{ formatDate(lead.next_followup_date) }}</p>
            <p v-if="lead.loss_reason" class="text-xs text-amber-300">Причина: {{ lead.loss_reason }}</p>
            <p v-if="lead.converted_order_id" class="text-xs text-emerald-300">Сделка: #{{ lead.converted_order_id }}</p>
          </div>

          <footer class="mt-4 flex flex-wrap gap-2">
            <button
              v-if="lead.status === 'new'"
              class="btn-mini-outline"
              :disabled="saving"
              @click="updateLead(lead.id, { status: 'contacted' }, 'Лид отмечен как обработанный')"
            >
              Связаться
            </button>
            <button
              v-if="lead.status === 'new' || lead.status === 'contacted'"
              class="btn-mini"
              :disabled="saving"
              @click="openQualifyModal(lead)"
            >
              Квалифицировать
            </button>
            <button
              v-if="lead.status === 'new' || lead.status === 'contacted'"
              class="btn-mini-outline"
              :disabled="saving"
              @click="markLost(lead, 'lost')"
            >
              Отказ
            </button>
            <button
              v-if="lead.status === 'new' || lead.status === 'contacted'"
              class="btn-mini-outline"
              :disabled="saving"
              @click="markLost(lead, 'spam')"
            >
              Спам
            </button>
            <button
              v-if="lead.converted_order_id"
              class="btn-mini-outline"
              @click="navigateToOrders(lead.converted_order_id)"
            >
              К сделке
            </button>
          </footer>
        </article>
      </div>
    </div>

    <div v-if="showCreateModal" class="fixed inset-0 z-[60] overflow-y-auto bg-black/60 p-4">
      <div class="mx-auto my-6 w-full max-w-2xl rounded-[2rem] border border-slate-700 bg-slate-900 p-6">
        <h2 class="mb-4 text-xl font-semibold">Новый лид</h2>
        <label class="field-label mb-3">
          <span>Найти существующего клиента</span>
          <input
            v-model="customerLookupQuery"
            class="field-input"
            placeholder="Имя, телефон, УНП, email"
          />
          <span class="text-xs text-slate-400">Если клиент уже есть в базе, выберите его и поля заполнятся автоматически.</span>
        </label>
        <div v-if="customerLookupLoading" class="mb-3 text-xs text-slate-400">Ищем клиентов...</div>
        <div v-else-if="customerLookupResults.length" class="mb-3 max-h-44 space-y-2 overflow-auto rounded-xl border border-slate-700 p-2">
          <button
            v-for="customer in customerLookupResults"
            :key="customer.id"
            type="button"
            class="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-left text-sm hover:border-slate-500"
            @click="applyCustomerToCreateForm(customer)"
          >
            <p class="font-semibold text-white">{{ customer.full_legal_name || customer.name || `Клиент #${customer.id}` }}</p>
            <p class="text-xs text-slate-300">
              {{ customer.phone || 'Без телефона' }}
              <span v-if="customer.inn"> · УНП {{ customer.inn }}</span>
              <span v-if="customer.email"> · {{ customer.email }}</span>
            </p>
          </button>
        </div>
        <div v-if="selectedExistingCustomer" class="mb-3 flex items-center justify-between gap-2 rounded-lg border border-emerald-500/40 bg-emerald-900/20 px-3 py-2">
          <p class="text-xs text-emerald-300">
            Выбран клиент #{{ selectedExistingCustomer.id }}.
          </p>
          <button type="button" class="btn-mini-outline text-xs" @click="navigateToCustomerProfile(selectedExistingCustomer)">
            Открыть клиента
          </button>
        </div>
        <div v-else-if="createSuggestedCustomer" class="mb-3 rounded-lg border border-amber-500/40 bg-amber-900/20 px-3 py-3">
          <p class="text-xs text-amber-200">
            Найден клиент #{{ createSuggestedCustomer.id }}:
            {{ createSuggestedCustomer.full_legal_name || createSuggestedCustomer.name || `Клиент #${createSuggestedCustomer.id}` }}.
          </p>
          <div class="mt-2 flex flex-wrap gap-2">
            <button type="button" class="btn-mini text-xs" @click="applyCustomerToCreateForm(createSuggestedCustomer)">
              Использовать данные клиента
            </button>
            <button type="button" class="btn-mini-outline text-xs" @click="dismissCreateCustomerSuggestion">
              Продолжить как новый лид
            </button>
            <button type="button" class="btn-mini-outline text-xs" @click="navigateToCustomerProfile(createSuggestedCustomer)">
              Открыть клиента
            </button>
          </div>
        </div>
        <div v-if="Object.keys(createServerErrors).length" class="mb-3 rounded-lg border border-red-500/40 bg-red-900/20 px-3 py-2 text-xs text-red-200">
          <p v-for="(message, field) in createServerErrors" :key="`create-${field}`">
            {{ getFieldLabel(field) }}: {{ message }}
          </p>
        </div>
        <div class="grid gap-3 md:grid-cols-2">
          <input
            v-model="createForm.name"
            class="field-input"
            :class="createServerErrors.name ? 'border-red-500 focus:outline-red-400' : ''"
            placeholder="Имя / Компания"
          />
          <label class="field-label">
            <span>Телефон</span>
            <input
              ref="createPhoneInputRef"
              v-model="createForm.phone"
              class="field-input"
              :class="createPhoneError ? 'border-red-500 focus:outline-red-400' : ''"
              type="tel"
              inputmode="tel"
              placeholder="+375 (XX) XXX-XX-XX"
              @blur="onCreatePhoneBlur"
            />
            <span v-if="createPhoneError" class="text-xs text-red-300">{{ createPhoneError }}</span>
          </label>
          <input
            v-model="createForm.email"
            class="field-input"
            :class="createEmailError || createServerErrors.email ? 'border-red-500 focus:outline-red-400' : ''"
            placeholder="Email"
            @blur="onCreateEmailBlur"
          />
          <span v-if="createEmailError" class="text-xs text-red-300 md:-mt-2 md:col-span-2">{{ createEmailError }}</span>
          <label class="field-label">
            <span>УНП</span>
            <input
              v-model="createForm.inn"
              class="field-input"
              :class="createInnError || createServerErrors.inn ? 'border-red-500 focus:outline-red-400' : ''"
              placeholder="УНП"
              inputmode="numeric"
              @blur="onCreateInnBlur"
            />
            <span v-if="createCompanyLookupLoading" class="text-xs text-slate-400">Подтягиваем данные ЕГР...</span>
            <span v-if="createInnError" class="text-xs text-red-300">{{ createInnError }}</span>
          </label>
          <input
            v-model="createForm.company_name"
            class="field-input"
            :class="createServerErrors.company_name ? 'border-red-500 focus:outline-red-400' : ''"
            placeholder="Полное название компании"
          />
          <select v-model="createForm.source" class="field-input" :class="createServerErrors.source ? 'border-red-500 focus:outline-red-400' : ''">
            <option value="manager">Менеджер</option>
            <option value="phone">Телефон</option>
            <option value="site">Сайт</option>
            <option value="bot">Бот</option>
            <option value="email">Email</option>
            <option value="other">Другое</option>
          </select>
          <DateTimeField
            v-model="createForm.next_followup_date"
            class="md:col-span-2"
            label="Следующее касание"
            placeholder="дд.мм.гггг, --:--"
            :error="createServerErrors.next_followup_date"
          />
          <label class="field-label md:col-span-2">
            <span>Запрос</span>
            <textarea
              v-model="createForm.request_text"
              class="field-input min-h-[100px]"
              :class="createRequestError || createServerErrors.request_text ? 'border-red-500 focus:outline-red-400' : ''"
              placeholder="Краткое описание запроса"
            />
            <span v-if="createRequestError" class="text-xs text-red-300">{{ createRequestError }}</span>
          </label>
        </div>
        <div class="mt-5 flex justify-end gap-2">
          <button class="btn-mini-outline" :disabled="saving" @click="showCreateModal = false">Отмена</button>
          <button class="btn-mini" :disabled="saving" @click="submitCreateLead">Создать</button>
        </div>
      </div>
    </div>

    <div v-if="showQualifyModal && selectedLead" class="fixed inset-0 z-[60] overflow-y-auto bg-black/60 p-4">
      <div class="mx-auto my-6 w-full max-w-2xl rounded-[2rem] border border-slate-700 bg-slate-900 p-6">
        <h2 class="mb-4 text-xl font-semibold">Квалифицировать лид #{{ selectedLead.id }}</h2>
        <label class="field-label mb-3">
          <span>Найти существующего клиента</span>
          <input
            v-model="qualifyCustomerLookupQuery"
            class="field-input"
            placeholder="Имя, телефон, УНП, email"
          />
        </label>
        <div v-if="qualifyCustomerLookupLoading" class="mb-3 text-xs text-slate-400">Ищем клиентов...</div>
        <div v-else-if="qualifyCustomerLookupResults.length" class="mb-3 max-h-44 space-y-2 overflow-auto rounded-xl border border-slate-700 p-2">
          <button
            v-for="customer in qualifyCustomerLookupResults"
            :key="`qualify-customer-${customer.id}`"
            type="button"
            class="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-left text-sm hover:border-slate-500"
            @click="applyCustomerToQualifyForm(customer)"
          >
            <p class="font-semibold text-white">{{ customer.full_legal_name || customer.name || `Клиент #${customer.id}` }}</p>
            <p class="text-xs text-slate-300">
              {{ customer.phone || 'Без телефона' }}
              <span v-if="customer.inn"> · УНП {{ customer.inn }}</span>
              <span v-if="customer.email"> · {{ customer.email }}</span>
            </p>
          </button>
        </div>
        <div v-if="selectedQualifyCustomer" class="mb-3 flex items-center justify-between gap-2 rounded-lg border border-emerald-500/40 bg-emerald-900/20 px-3 py-2">
          <p class="text-xs text-emerald-300">
            Выбран клиент #{{ selectedQualifyCustomer.id }}.
          </p>
          <button type="button" class="btn-mini-outline text-xs" @click="navigateToCustomerProfile(selectedQualifyCustomer)">
            Открыть клиента
          </button>
        </div>
        <div
          v-if="selectedQualifyCustomerDetail && qualifyChangedRequisites.length"
          class="mb-3 rounded-lg border border-amber-500/40 bg-amber-900/20 px-3 py-3 text-xs text-amber-100"
        >
          <p class="font-semibold text-amber-50">Обнаружены отличия в реквизитах клиента</p>
          <p class="mt-1 text-amber-200/90">
            По умолчанию непустые значения клиента не перезаписываются. Отметьте, что нужно обновить.
          </p>
          <div class="mt-2 space-y-2">
            <label
              v-for="row in qualifyChangedRequisites"
              :key="`diff-${row.key}`"
              class="flex items-start gap-2 rounded-md border border-amber-500/20 bg-amber-900/20 px-2 py-2"
            >
              <input v-model="qualifyOverwriteFields[row.key]" type="checkbox" class="mt-0.5" />
              <span>
                <strong>{{ row.label }}</strong><br />
                <span class="text-amber-200/90">Было: {{ row.existing }}</span><br />
                <span class="text-amber-100">Станет: {{ row.incoming }}</span>
              </span>
            </label>
          </div>
        </div>
        <div
          v-if="qualifyCriticalOverwriteRows.length"
          class="mb-3 rounded-lg border border-red-500/40 bg-red-900/20 px-3 py-3 text-xs text-red-100"
        >
          <p class="font-semibold text-red-50">Подтверждение перезаписи критичных реквизитов</p>
          <p class="mt-1 text-red-200/90">Эти значения будут обновлены у выбранного клиента:</p>
          <ul class="mt-2 list-inside list-disc space-y-1 text-red-100">
            <li v-for="row in qualifyCriticalOverwriteRows" :key="`critical-${row.key}`">
              {{ row.label }}: {{ row.existing }} -> {{ row.incoming }}
            </li>
          </ul>
          <div class="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              class="btn-mini bg-red-600/80 hover:bg-red-500"
              @click="
                qualifyCriticalOverwriteConfirmed = true;
                qualifyLead();
              "
            >
              Подтвердить и продолжить
            </button>
            <button type="button" class="btn-mini-outline" @click="clearQualifyCriticalOverwriteConfirm">
              Отмена
            </button>
          </div>
        </div>
        <div class="mb-3 rounded-lg border border-slate-700 bg-slate-800/70 px-3 py-2 text-xs text-slate-300">
          <p class="font-semibold text-slate-100">Preview квалификации</p>
          <p>
            Клиент:
            <span class="text-slate-100">{{ qualifyPreview.customerLabel }}</span>
          </p>
          <p>
            Тип клиента:
            <span class="text-slate-100">{{ customerTypeLabels[qualifyPreview.predictedCustomerType] || qualifyPreview.predictedCustomerType }}</span>
          </p>
          <p>
            Сегмент:
            <span class="text-slate-100">{{ segmentLabels[qualifyPreview.predictedSegment] || qualifyPreview.predictedSegment }}</span>
          </p>
          <p v-if="qualifyPreview.inn">Матч по УНП: <span class="text-slate-100">{{ qualifyPreview.inn }}</span></p>
          <p v-if="qualifyPreview.phoneDigits">Матч по телефону: <span class="text-slate-100">{{ qualifyPreview.phoneDigits }}</span></p>
          <p v-if="qualifyPreview.email">Матч по email: <span class="text-slate-100">{{ qualifyPreview.email }}</span></p>
          <p v-if="qualifyPreview.matchedBy">
            Приоритет матча:
            <span class="text-slate-100">{{ qualifyPreview.matchedBy === 'inn' ? 'УНП' : qualifyPreview.matchedBy === 'phone' ? 'Телефон' : 'Email' }}</span>
          </p>
          <p>
            Реквизиты для записи:
            <span v-if="qualifyPreview.requisitesToWrite.length" class="text-slate-100">
              {{ qualifyPreview.requisitesToWrite.map((item) => item.label).join(', ') }}
            </span>
            <span v-else class="text-slate-400">не указаны</span>
          </p>
          <p>
            Фактически будут записаны:
            <span v-if="qualifyWriteSummary.length" class="text-slate-100">
              {{
                qualifyWriteSummary
                  .map((item) => item.mode === 'overwrite' ? `${item.label} (обновление)` : item.label)
                  .join(', ')
              }}
            </span>
            <span v-else class="text-slate-400">нет изменений в реквизитах клиента</span>
          </p>
        </div>
        <div v-if="Object.keys(qualifyServerErrors).length" class="mb-3 rounded-lg border border-red-500/40 bg-red-900/20 px-3 py-2 text-xs text-red-200">
          <p v-for="(message, field) in qualifyServerErrors" :key="`qualify-${field}`">
            {{ getFieldLabel(field) }}: {{ message }}
          </p>
        </div>
        <div class="grid gap-3 md:grid-cols-2">
          <input
            v-model="qualifyForm.name"
            class="field-input"
            :class="qualifyServerErrors.name ? 'border-red-500 focus:outline-red-400' : ''"
            placeholder="Имя клиента"
          />
          <label class="field-label">
            <span>Телефон</span>
            <input
              ref="qualifyPhoneInputRef"
              v-model="qualifyForm.phone"
              class="field-input"
              :class="qualifyPhoneError ? 'border-red-500 focus:outline-red-400' : ''"
              type="tel"
              inputmode="tel"
              placeholder="+375 (XX) XXX-XX-XX"
              @blur="validateQualifyPhoneOnBlur"
            />
            <span v-if="qualifyPhoneError" class="text-xs text-red-300">{{ qualifyPhoneError }}</span>
          </label>
          <input
            v-model="qualifyForm.email"
            class="field-input"
            :class="qualifyEmailError || qualifyServerErrors.email ? 'border-red-500 focus:outline-red-400' : ''"
            placeholder="Email"
            @blur="onQualifyEmailBlur"
          />
          <span v-if="qualifyEmailError" class="text-xs text-red-300 md:-mt-2 md:col-span-2">{{ qualifyEmailError }}</span>
          <label class="field-label">
            <span>УНП</span>
            <input
              v-model="qualifyForm.inn"
              class="field-input"
              :class="qualifyInnError || qualifyServerErrors.inn ? 'border-red-500 focus:outline-red-400' : ''"
              placeholder="УНП"
              inputmode="numeric"
              @blur="onQualifyInnBlur"
            />
            <span v-if="qualifyCompanyLookupLoading" class="text-xs text-slate-400">Подтягиваем данные ЕГР...</span>
            <span v-if="qualifyInnError" class="text-xs text-red-300">{{ qualifyInnError }}</span>
          </label>
          <input
            v-model="qualifyForm.full_legal_name"
            class="field-input md:col-span-2"
            :class="qualifyServerErrors.full_legal_name ? 'border-red-500 focus:outline-red-400' : ''"
            placeholder="Полное наименование (для юрлица)"
          />
          <input
            v-model="qualifyForm.legal_address"
            class="field-input md:col-span-2"
            :class="qualifyServerErrors.legal_address ? 'border-red-500 focus:outline-red-400' : ''"
            placeholder="Юридический адрес"
          />
          <label class="field-label">
            <span>IBAN (расчетный счет)</span>
            <input
              v-model="qualifyForm.iban"
              class="field-input"
              :class="qualifyIbanError || qualifyServerErrors.iban ? 'border-red-500 focus:outline-red-400' : ''"
              placeholder="BY.."
              @blur="onQualifyIbanBlur"
            />
            <span v-if="qualifyBankLookupLoading" class="text-xs text-slate-400">Подтягиваем данные банка...</span>
            <span v-if="qualifyIbanError" class="text-xs text-red-300">{{ qualifyIbanError }}</span>
          </label>
          <input
            v-model="qualifyForm.bic"
            class="field-input"
            :class="qualifyServerErrors.bic ? 'border-red-500 focus:outline-red-400' : ''"
            placeholder="BIC банка"
          />
          <input
            v-model="qualifyForm.bank_name"
            class="field-input md:col-span-2"
            :class="qualifyServerErrors.bank_name ? 'border-red-500 focus:outline-red-400' : ''"
            placeholder="Название банка"
          />
          <input
            v-model="qualifyForm.delivery_address"
            class="field-input md:col-span-2"
            :class="qualifyServerErrors.delivery_address ? 'border-red-500 focus:outline-red-400' : ''"
            placeholder="Адрес доставки/монтажа"
          />
          <label class="field-label md:col-span-2">
            <span>Комментарий сделки</span>
            <textarea
              v-model="qualifyForm.order_comment"
              class="field-input min-h-[90px]"
              :class="qualifyServerErrors.order_comment ? 'border-red-500 focus:outline-red-400' : ''"
            />
          </label>
        </div>
        <div class="mt-5 flex justify-end gap-2">
          <button class="btn-mini-outline" :disabled="saving" @click="showQualifyModal = false">Отмена</button>
          <button class="btn-mini" :disabled="saving" @click="qualifyLead">Создать клиента и сделку</button>
        </div>
      </div>
    </div>
  </div>
</template>
