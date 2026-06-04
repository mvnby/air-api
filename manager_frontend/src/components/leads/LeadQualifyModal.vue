<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { api } from '../../api';
import type { LeadsInboxItemResponse } from '../../api';
import type { ManagerCustomerBranchItemResponse, ManagerOrderUpdatePayload } from '../../client';
import { useBelarusPhoneMask } from '../../composables/useBelarusPhoneMask';
import { useB2BLookup } from '../../composables/useB2BLookup';

const props = defineProps<{
  lead: LeadsInboxItemResponse;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'success', orderId: number): void;
}>();

type CustomerTypeChoice = '' | 'individual' | 'company';
type ServiceTypeChoice = '' | 'turnkey' | 'install_only' | 'pre_install' | 'maintenance' | 'repair' | 'dismantling';
type OptionalSectionKey = 'contacts' | 'company' | 'branch' | 'extra';

const isCustomerType = (value: unknown): value is Exclude<CustomerTypeChoice, ''> =>
  value === 'individual' || value === 'company';

const normalizeServiceType = (value: unknown): ServiceTypeChoice => {
  const raw = String(value || '').trim();
  if (
    raw === 'turnkey'
    || raw === 'install_only'
    || raw === 'pre_install'
    || raw === 'maintenance'
    || raw === 'repair'
    || raw === 'dismantling'
  ) {
    return raw;
  }
  return '';
};

const cleanText = (value: unknown) => {
  const cleaned = String(value ?? '').trim();
  return cleaned || undefined;
};

const isLoading = ref(false);
const attemptedSubmit = ref(false);

const initialCustomerType = isCustomerType(props.lead.customer_type) ? props.lead.customer_type : '';
const customerType = ref<CustomerTypeChoice>(initialCustomerType);
const customerTypeChosenByManager = ref(false);
const serviceType = ref<ServiceTypeChoice>(normalizeServiceType(props.lead.service_type));

const customerName = ref(props.lead.customer_name || props.lead.customer_full_legal_name || '');
const customerPhone = ref(props.lead.phone || '');
const customerEmail = ref(props.lead.email || '');
const phoneInputRef = ref<HTMLInputElement | null>(null);
const { unmaskedValue: unmaskedPhone } = useBelarusPhoneMask(phoneInputRef, customerPhone, { lazy: false });

const customerDeliveryAddress = ref(props.lead.customer_delivery_address || '');
const companyName = ref(props.lead.customer_name || '');
const companyInn = ref(props.lead.customer_inn || '');
const companyFullLegalName = ref(props.lead.customer_full_legal_name || '');
const companyLegalAddress = ref('');
const companyIban = ref('');
const companyBic = ref('');
const companyBankName = ref('');

const objectType = ref(props.lead.object_type || '');
const equipmentClass = ref(props.lead.equipment_class || '');
const marketingSource = ref(props.lead.marketing_source || '');
const managerComment = ref(props.lead.comment || '');

const optionalSections = ref<Record<OptionalSectionKey, boolean>>({
  contacts: false,
  company: false,
  branch: false,
  extra: false,
});

const existingCustomerId = ref<number | null>(null);
const customerBranches = ref<ManagerCustomerBranchItemResponse[]>([]);
const selectedBranchId = ref<number | null>(null);
const branchesLoading = ref(false);
const newBranchName = ref('');
const newBranchAddress = ref('');
const creatingBranch = ref(false);

const { lookupCompany, lookupBank, isEgrLoading, isBankLoading } = useB2BLookup();

const searchTimeout = ref<number | null>(null);
const searchStatus = ref<'idle' | 'searching' | 'found' | 'not_found'>('idle');
const foundCustomerName = ref('');
const selectedBranch = computed(() => customerBranches.value.find((branch) => branch.id === selectedBranchId.value) || null);

const missingCustomerType = computed(() => !customerType.value);
const missingServiceType = computed(() => !serviceType.value);
const canSubmit = computed(() => !isLoading.value && !missingCustomerType.value && !missingServiceType.value);

const serviceOptions: Array<{ value: ServiceTypeChoice; label: string; hint: string; icon: string }> = [
  { value: 'turnkey', label: 'Покупка + монтаж', hint: 'нужно подобрать и установить', icon: 'shopping_cart' },
  { value: 'install_only', label: 'Монтаж', hint: 'оборудование уже есть', icon: 'construction' },
  { value: 'pre_install', label: 'Закладка трассы', hint: 'этап ремонта', icon: 'route' },
  { value: 'maintenance', label: 'Обслуживание', hint: 'ТО, чистка, сервис', icon: 'ac_unit' },
  { value: 'repair', label: 'Ремонт', hint: 'диагностика и восстановление', icon: 'build_circle' },
  { value: 'dismantling', label: 'Демонтаж', hint: 'снять или перенести', icon: 'move_down' },
];

const customerTypeOptions: Array<{ value: Exclude<CustomerTypeChoice, ''>; label: string; hint: string; icon: string }> = [
  { value: 'individual', label: 'Физлицо', hint: 'частный клиент', icon: 'person' },
  { value: 'company', label: 'Юрлицо', hint: 'компания или ИП', icon: 'business' },
];

const selectCustomerType = (value: Exclude<CustomerTypeChoice, ''>) => {
  customerType.value = value;
  customerTypeChosenByManager.value = true;
  searchCustomer();
};

const resetBranches = () => {
  customerBranches.value = [];
  selectedBranchId.value = null;
  newBranchName.value = '';
  newBranchAddress.value = '';
};

const loadBranches = async (customerId: number) => {
  branchesLoading.value = true;
  try {
    const response = await api.getManagerCustomerBranches(customerId);
    customerBranches.value = response.items || [];
    const hasCurrent = selectedBranchId.value
      ? customerBranches.value.some((branch) => branch.id === selectedBranchId.value)
      : false;
    selectedBranchId.value = hasCurrent ? selectedBranchId.value : null;
  } catch (error) {
    console.error('Failed to load customer branches', error);
    resetBranches();
  } finally {
    branchesLoading.value = false;
  }
};

const searchCustomer = async () => {
  const query = customerType.value === 'company'
    ? companyInn.value
    : (unmaskedPhone.value || customerPhone.value);
  if (!query || query.length < 5) {
    searchStatus.value = 'idle';
    existingCustomerId.value = null;
    foundCustomerName.value = '';
    resetBranches();
    return;
  }

  try {
    searchStatus.value = 'searching';
    const res = await api.getManagerCustomers(1, 1, query);
    const match = res.items?.[0];
    if (match) {
      existingCustomerId.value = match.id;
      foundCustomerName.value = match.name || match.full_legal_name || 'Неизвестно';
      searchStatus.value = 'found';
      const matchType = isCustomerType(match.type) ? match.type : '';
      const matchLooksCompany = matchType === 'company' || Boolean(match.inn || match.full_legal_name);
      if (matchLooksCompany) {
        customerType.value = 'company';
      } else if (
        matchType === 'individual'
        && (initialCustomerType === 'individual' || (customerTypeChosenByManager.value && customerType.value === 'individual'))
      ) {
        customerType.value = 'individual';
      }
      if (!customerName.value) customerName.value = match.name || match.full_legal_name || '';
      if (!customerEmail.value) customerEmail.value = match.email || '';
      if (!companyInn.value) companyInn.value = match.inn || '';
      if (!companyFullLegalName.value) companyFullLegalName.value = match.full_legal_name || '';
      await loadBranches(match.id);
      return;
    }
    existingCustomerId.value = null;
    searchStatus.value = 'not_found';
    foundCustomerName.value = '';
    resetBranches();
  } catch (e) {
    console.error('Customer search failed', e);
    searchStatus.value = 'idle';
    existingCustomerId.value = null;
    foundCustomerName.value = '';
    resetBranches();
  }
};

const onSearchInput = () => {
  if (searchTimeout.value) clearTimeout(searchTimeout.value);
  searchTimeout.value = window.setTimeout(searchCustomer, 500);
};

watch(() => props.lead, () => {
  if (customerPhone.value || companyInn.value) {
    searchCustomer();
  }
}, { immediate: true });

const onInnBlur = async () => {
  if (!companyInn.value || companyInn.value.length !== 9) return;
  const data = await lookupCompany(companyInn.value);
  if (data) {
    if (!companyFullLegalName.value) companyFullLegalName.value = data.fullLegalName || '';
    if (!companyLegalAddress.value) companyLegalAddress.value = data.legalAddress || '';
    if (!companyName.value) companyName.value = data.fullLegalName || '';
  }
};

const onIbanBlur = async () => {
  if (!companyIban.value || companyIban.value.length < 15) return;
  const data = await lookupBank(companyIban.value);
  if (data) {
    if (!companyBankName.value) companyBankName.value = data.bankName || '';
    if (!companyBic.value) companyBic.value = data.bic || '';
  }
};

const createBranchForExistingCustomer = async () => {
  if (!existingCustomerId.value || creatingBranch.value) return;
  const deliveryAddress = newBranchAddress.value.trim();
  if (!deliveryAddress) {
    alert('Введите адрес филиала');
    return;
  }
  creatingBranch.value = true;
  try {
    const created = await api.createManagerCustomerBranch(existingCustomerId.value, {
      name: newBranchName.value.trim() || undefined,
      delivery_address: deliveryAddress,
      is_default: customerBranches.value.length === 0,
    });
    customerBranches.value = [created, ...customerBranches.value.filter((branch) => branch.id !== created.id)];
    selectedBranchId.value = created.id;
    customerDeliveryAddress.value = created.delivery_address;
    newBranchName.value = '';
    newBranchAddress.value = '';
  } catch (error) {
    console.error('Failed to create branch', error);
    alert('Не удалось создать филиал');
  } finally {
    creatingBranch.value = false;
  }
};

const onSelectedBranchChange = () => {
  const branch = selectedBranch.value;
  if (!branch) return;
  customerDeliveryAddress.value = branch.delivery_address;
};

const sectionSummary = (key: OptionalSectionKey) => {
  if (key === 'contacts') {
    return [customerName.value, customerPhone.value, customerEmail.value, customerDeliveryAddress.value]
      .filter(Boolean)
      .slice(0, 2)
      .join(' · ') || 'можно заполнить позже';
  }
  if (key === 'company') {
    return [companyInn.value ? `УНП ${companyInn.value}` : '', companyFullLegalName.value || companyName.value]
      .filter(Boolean)
      .join(' · ') || 'реквизиты не обязательны';
  }
  if (key === 'branch') {
    return selectedBranch.value?.name || objectType.value || 'филиал и объект не обязательны';
  }
  return [marketingSource.value, equipmentClass.value].filter(Boolean).join(' · ') || 'дополнения не обязательны';
};

const buildPayload = (): ManagerOrderUpdatePayload => {
  const payload: ManagerOrderUpdatePayload = {
    status: 'negotiation',
    customer_type: customerType.value || undefined,
    service_type: serviceType.value || undefined,
  };

  if (existingCustomerId.value) {
    payload.customer_id = existingCustomerId.value;
  }
  if (selectedBranchId.value !== null) {
    payload.customer_branch_id = selectedBranchId.value;
  }

  const deliveryAddress = cleanText(customerDeliveryAddress.value || selectedBranch.value?.delivery_address);
  if (deliveryAddress) payload.customer_delivery_address = deliveryAddress;

  const name = cleanText(customerType.value === 'company'
    ? (companyName.value || companyFullLegalName.value || customerName.value)
    : customerName.value);
  if (name) payload.customer_name = name;

  const phone = cleanText(unmaskedPhone.value || customerPhone.value);
  if (phone) payload.customer_phone = phone;

  const email = cleanText(customerEmail.value);
  if (email) payload.customer_email = email;

  if (customerType.value === 'company') {
    const inn = cleanText(companyInn.value);
    const fullLegalName = cleanText(companyFullLegalName.value || companyName.value);
    const legalAddress = cleanText(companyLegalAddress.value);
    const iban = cleanText(companyIban.value);
    const bic = cleanText(companyBic.value);
    const bankName = cleanText(companyBankName.value);
    if (inn) payload.customer_inn = inn;
    if (fullLegalName) payload.customer_full_legal_name = fullLegalName;
    if (legalAddress) payload.customer_legal_address = legalAddress;
    if (iban) payload.customer_iban = iban;
    if (bic) payload.customer_bic = bic;
    if (bankName) payload.customer_bank_name = bankName;
  }

  const comment = cleanText(managerComment.value);
  if (comment) payload.comment = comment;

  const selectedObjectType = cleanText(objectType.value);
  const selectedEquipmentClass = cleanText(equipmentClass.value);
  const selectedMarketingSource = cleanText(marketingSource.value);
  if (selectedObjectType) payload.object_type = selectedObjectType;
  if (selectedEquipmentClass) payload.equipment_class = selectedEquipmentClass;
  if (selectedMarketingSource) payload.marketing_source = selectedMarketingSource;

  return payload;
};

const submitQualify = async () => {
  attemptedSubmit.value = true;
  if (!canSubmit.value) return;

  isLoading.value = true;
  try {
    await api.patchManagerOrder(props.lead.id, buildPayload());
    emit('success', props.lead.id);
  } catch (e) {
    console.error(e);
    alert('Ошибка при сохранении данных');
  } finally {
    isLoading.value = false;
  }
};
</script>

<template>
  <div class="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4 font-sans text-slate-800 backdrop-blur-sm dark:text-slate-200">
    <div class="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl dark:bg-slate-900">
      <div class="flex shrink-0 items-center justify-between border-b border-slate-100 bg-slate-50/70 px-6 py-4 dark:border-slate-800 dark:bg-slate-900/60">
        <div class="min-w-0">
          <h2 class="flex items-center gap-2 text-lg font-bold">
            <span class="material-icons-round text-teal-600 dark:text-teal-500">bolt</span>
            Быстрая квалификация #{{ lead.id }}
          </h2>
          <p class="mt-1 text-xs text-slate-500">Минимум для сделки: тип клиента и суть задачи.</p>
        </div>
        <button
          class="flex h-8 w-8 items-center justify-center rounded-full text-slate-500 transition-colors hover:bg-slate-200 dark:hover:bg-slate-700"
          @click="emit('close')"
        >
          <span class="material-icons-round text-[18px]">close</span>
        </button>
      </div>

      <div class="flex-1 space-y-5 overflow-y-auto p-6">
        <section class="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/60">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <p class="text-xs font-bold uppercase tracking-wide text-slate-400">Входящий запрос</p>
              <p class="mt-1 text-sm font-semibold text-slate-900 dark:text-white">
                {{ lead.customer_name || lead.customer_full_legal_name || customerPhone || customerEmail || 'Контакт не указан' }}
              </p>
              <div class="mt-2 flex flex-wrap gap-2 text-xs text-slate-500 dark:text-slate-400">
                <span v-if="customerPhone" class="inline-flex items-center gap-1">
                  <span class="material-icons-round text-[14px]">call</span>
                  {{ customerPhone }}
                </span>
                <span v-if="customerEmail" class="inline-flex items-center gap-1">
                  <span class="material-icons-round text-[14px]">email</span>
                  {{ customerEmail }}
                </span>
                <span v-if="lead.source" class="inline-flex items-center gap-1">
                  <span class="material-icons-round text-[14px]">campaign</span>
                  {{ lead.source }}
                </span>
              </div>
            </div>
            <span
              v-if="searchStatus === 'found'"
              class="inline-flex items-center gap-1 rounded-full bg-teal-100 px-3 py-1 text-xs font-bold text-teal-700 dark:bg-teal-500/10 dark:text-teal-300"
            >
              <span class="material-icons-round text-[15px]">person_search</span>
              Клиент найден
            </span>
          </div>
          <p v-if="lead.comment" class="mt-3 whitespace-pre-line rounded-xl bg-white p-3 text-sm leading-relaxed text-slate-700 dark:bg-slate-900/70 dark:text-slate-200">
            {{ lead.comment }}
          </p>
        </section>

        <section class="space-y-4">
          <div>
            <div class="mb-2 flex items-center justify-between gap-3">
              <h3 class="flex items-center gap-2 text-sm font-bold text-slate-900 dark:text-white">
                <span class="material-icons-round text-[18px] text-teal-600 dark:text-teal-400">person</span>
                Клиент
              </h3>
              <span v-if="attemptedSubmit && missingCustomerType" class="text-xs font-semibold text-red-500">Выберите тип клиента</span>
            </div>
            <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <button
                v-for="option in customerTypeOptions"
                :key="option.value"
                type="button"
                class="flex items-center gap-3 rounded-xl border px-4 py-3 text-left transition-all"
                :class="customerType === option.value
                  ? 'border-teal-500 bg-teal-50 text-teal-800 shadow-sm dark:border-teal-400 dark:bg-teal-500/10 dark:text-teal-200'
                  : attemptedSubmit && missingCustomerType
                    ? 'border-red-300 bg-red-50 text-slate-700 dark:border-red-500/50 dark:bg-red-500/10 dark:text-slate-200'
                    : 'border-slate-200 bg-white text-slate-700 hover:border-teal-300 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200'"
                @click="selectCustomerType(option.value)"
              >
                <span class="material-icons-round text-[20px]">{{ option.icon }}</span>
                <span class="min-w-0">
                  <span class="block text-sm font-bold">{{ option.label }}</span>
                  <span class="block text-xs opacity-70">{{ option.hint }}</span>
                </span>
              </button>
            </div>
          </div>

          <div>
            <div class="mb-2 flex items-center justify-between gap-3">
              <h3 class="flex items-center gap-2 text-sm font-bold text-slate-900 dark:text-white">
                <span class="material-icons-round text-[18px] text-teal-600 dark:text-teal-400">build</span>
                Суть задачи
              </h3>
              <span v-if="attemptedSubmit && missingServiceType" class="text-xs font-semibold text-red-500">Выберите задачу</span>
            </div>
            <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <button
                v-for="option in serviceOptions"
                :key="option.value"
                type="button"
                class="flex items-center gap-3 rounded-xl border px-4 py-3 text-left transition-all"
                :class="serviceType === option.value
                  ? 'border-teal-500 bg-teal-50 text-teal-800 shadow-sm dark:border-teal-400 dark:bg-teal-500/10 dark:text-teal-200'
                  : attemptedSubmit && missingServiceType
                    ? 'border-red-300 bg-red-50 text-slate-700 dark:border-red-500/50 dark:bg-red-500/10 dark:text-slate-200'
                    : 'border-slate-200 bg-white text-slate-700 hover:border-teal-300 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200'"
                @click="serviceType = option.value"
              >
                <span class="material-icons-round text-[20px]">{{ option.icon }}</span>
                <span class="min-w-0">
                  <span class="block text-sm font-bold">{{ option.label }}</span>
                  <span class="block text-xs opacity-70">{{ option.hint }}</span>
                </span>
              </button>
            </div>
          </div>
        </section>

        <div v-if="searchStatus === 'found'" class="flex items-start gap-3 rounded-xl border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-800 dark:border-teal-800 dark:bg-teal-900/30 dark:text-teal-300">
          <span class="material-icons-round mt-0.5 text-teal-500">info</span>
          <div>
            <strong>Найдена карточка клиента: {{ foundCustomerName }}</strong><br>
            Сделка будет привязана к этому профилю.
            <a
              :href="'/manager/customers/profile?customerId=' + existingCustomerId"
              target="_blank"
              class="ml-2 font-semibold underline hover:text-teal-600 dark:hover:text-teal-200"
              title="Открыть в новой вкладке"
            >
              Профиль
            </a>
          </div>
        </div>

        <section class="space-y-2">
          <button
            type="button"
            class="flex w-full items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-left transition-colors hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700/70"
            @click="optionalSections.contacts = !optionalSections.contacts"
          >
            <span>
              <span class="block text-sm font-bold">Контакты и адрес</span>
              <span class="block text-xs text-slate-500">{{ sectionSummary('contacts') }}</span>
            </span>
            <span class="material-icons-round text-slate-400">{{ optionalSections.contacts ? 'expand_less' : 'expand_more' }}</span>
          </button>
          <div v-if="optionalSections.contacts" class="grid grid-cols-1 gap-4 rounded-xl bg-slate-50 p-4 dark:bg-slate-800/60 md:grid-cols-2">
            <label class="block text-xs font-semibold text-slate-500">
              Имя / контакт
              <input v-model="customerName" type="text" class="mt-1 w-full rounded-xl border-0 bg-white px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 dark:bg-slate-900">
            </label>
            <label class="block text-xs font-semibold text-slate-500">
              Телефон
              <input ref="phoneInputRef" v-model="customerPhone" type="text" class="mt-1 w-full rounded-xl border-0 bg-white px-4 py-2.5 text-sm font-medium focus:ring-2 focus:ring-teal-500 dark:bg-slate-900" @input="onSearchInput">
            </label>
            <label class="block text-xs font-semibold text-slate-500 md:col-span-2">
              Email
              <input v-model="customerEmail" type="email" class="mt-1 w-full rounded-xl border-0 bg-white px-4 py-2.5 text-sm font-medium focus:ring-2 focus:ring-teal-500 dark:bg-slate-900">
            </label>
            <label class="block text-xs font-semibold text-slate-500 md:col-span-2">
              Адрес объекта / доставки
              <input v-model="customerDeliveryAddress" type="text" class="mt-1 w-full rounded-xl border-0 bg-white px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 dark:bg-slate-900" placeholder="Адрес можно добавить позже">
            </label>
          </div>

          <button
            v-if="customerType === 'company'"
            type="button"
            class="flex w-full items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-left transition-colors hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700/70"
            @click="optionalSections.company = !optionalSections.company"
          >
            <span>
              <span class="block text-sm font-bold">Реквизиты компании</span>
              <span class="block text-xs text-slate-500">{{ sectionSummary('company') }}</span>
            </span>
            <span class="material-icons-round text-slate-400">{{ optionalSections.company ? 'expand_less' : 'expand_more' }}</span>
          </button>
          <div v-if="customerType === 'company' && optionalSections.company" class="grid grid-cols-1 gap-4 rounded-xl bg-slate-50 p-4 dark:bg-slate-800/60 md:grid-cols-2">
            <label class="block text-xs font-semibold text-slate-500">
              УНП
              <span class="relative mt-1 block">
                <input v-model="companyInn" type="text" class="w-full rounded-xl border-0 bg-white px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 dark:bg-slate-900" placeholder="9 цифр" @input="onSearchInput" @blur="onInnBlur">
                <span v-if="isEgrLoading" class="absolute right-3 top-2.5">
                  <span class="material-icons-round animate-spin text-sm text-teal-500">refresh</span>
                </span>
              </span>
            </label>
            <label class="block text-xs font-semibold text-slate-500">
              Короткое название
              <input v-model="companyName" type="text" class="mt-1 w-full rounded-xl border-0 bg-white px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 dark:bg-slate-900">
            </label>
            <label class="block text-xs font-semibold text-slate-500 md:col-span-2">
              Полное юридическое название
              <input v-model="companyFullLegalName" type="text" class="mt-1 w-full rounded-xl border-0 bg-white px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 dark:bg-slate-900">
            </label>
            <label class="block text-xs font-semibold text-slate-500 md:col-span-2">
              Юридический адрес
              <input v-model="companyLegalAddress" type="text" class="mt-1 w-full rounded-xl border-0 bg-white px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 dark:bg-slate-900">
            </label>
            <label class="block text-xs font-semibold text-slate-500 md:col-span-2">
              IBAN
              <span class="relative mt-1 block">
                <input v-model="companyIban" type="text" class="w-full rounded-xl border-0 bg-white px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 dark:bg-slate-900" @blur="onIbanBlur">
                <span v-if="isBankLoading" class="absolute right-3 top-2.5">
                  <span class="material-icons-round animate-spin text-sm text-teal-500">refresh</span>
                </span>
              </span>
            </label>
            <label class="block text-xs font-semibold text-slate-500">
              BIC
              <input v-model="companyBic" type="text" class="mt-1 w-full rounded-xl border-0 bg-white px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 dark:bg-slate-900">
            </label>
            <label class="block text-xs font-semibold text-slate-500">
              Банк
              <input v-model="companyBankName" type="text" class="mt-1 w-full rounded-xl border-0 bg-white px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 dark:bg-slate-900">
            </label>
          </div>

          <button
            type="button"
            class="flex w-full items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-left transition-colors hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700/70"
            @click="optionalSections.branch = !optionalSections.branch"
          >
            <span>
              <span class="block text-sm font-bold">Филиал и объект</span>
              <span class="block text-xs text-slate-500">{{ sectionSummary('branch') }}</span>
            </span>
            <span class="material-icons-round text-slate-400">{{ optionalSections.branch ? 'expand_less' : 'expand_more' }}</span>
          </button>
          <div v-if="optionalSections.branch" class="grid grid-cols-1 gap-4 rounded-xl bg-slate-50 p-4 dark:bg-slate-800/60 md:grid-cols-2">
            <label v-if="existingCustomerId" class="block text-xs font-semibold text-slate-500 md:col-span-2">
              Филиал клиента
              <select
                v-model="selectedBranchId"
                class="mt-1 w-full rounded-xl border-0 bg-white px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 dark:bg-slate-900"
                :disabled="branchesLoading"
                @change="onSelectedBranchChange"
              >
                <option :value="null">Без филиала</option>
                <option v-for="branch in customerBranches" :key="`branch-${branch.id}`" :value="branch.id">
                  {{ branch.name || `Филиал #${branch.id}` }} — {{ branch.delivery_address }}
                </option>
              </select>
              <span v-if="branchesLoading" class="mt-1 block text-xs text-slate-500">Загрузка филиалов...</span>
              <span v-else-if="!customerBranches.length" class="mt-1 block text-xs text-slate-500">У клиента пока нет филиалов.</span>
            </label>
            <template v-if="existingCustomerId">
              <label class="block text-xs font-semibold text-slate-500">
                Новый филиал
                <input v-model="newBranchName" type="text" class="mt-1 w-full rounded-xl border-0 bg-white px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 dark:bg-slate-900" placeholder="Склад / Объект">
              </label>
              <label class="block text-xs font-semibold text-slate-500">
                Адрес филиала
                <input v-model="newBranchAddress" type="text" class="mt-1 w-full rounded-xl border-0 bg-white px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 dark:bg-slate-900" placeholder="Минск, Ленина 1">
              </label>
              <div class="md:col-span-2">
                <button
                  type="button"
                  class="rounded-xl border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-700"
                  :disabled="creatingBranch || !existingCustomerId"
                  @click="createBranchForExistingCustomer"
                >
                  {{ creatingBranch ? 'Создаем филиал...' : 'Создать филиал и выбрать' }}
                </button>
              </div>
            </template>
            <label class="block text-xs font-semibold text-slate-500 md:col-span-2">
              Тип объекта
              <select v-model="objectType" class="mt-1 w-full rounded-xl border-0 bg-white px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 dark:bg-slate-900">
                <option value="">Не указано</option>
                <option value="apartment">Квартира</option>
                <option value="house">Частный дом</option>
                <option value="office">Офис / магазин</option>
                <option value="industrial">Пром / серверная</option>
              </select>
            </label>
          </div>

          <button
            type="button"
            class="flex w-full items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-left transition-colors hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700/70"
            @click="optionalSections.extra = !optionalSections.extra"
          >
            <span>
              <span class="block text-sm font-bold">Дополнительно</span>
              <span class="block text-xs text-slate-500">{{ sectionSummary('extra') }}</span>
            </span>
            <span class="material-icons-round text-slate-400">{{ optionalSections.extra ? 'expand_less' : 'expand_more' }}</span>
          </button>
          <div v-if="optionalSections.extra" class="grid grid-cols-1 gap-4 rounded-xl bg-slate-50 p-4 dark:bg-slate-800/60 md:grid-cols-2">
            <label class="block text-xs font-semibold text-slate-500">
              Источник
              <select v-model="marketingSource" class="mt-1 w-full rounded-xl border-0 bg-white px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 dark:bg-slate-900">
                <option value="">Не указано</option>
                <option value="site">Сайт</option>
                <option value="instagram">Instagram / TikTok</option>
                <option value="referral">Рекомендация</option>
                <option value="onliner">Onliner</option>
                <option value="kufar">Kufar / 103</option>
                <option value="email">Email</option>
                <option value="phone">Телефон</option>
                <option value="manager">Менеджер</option>
              </select>
            </label>
            <label class="block text-xs font-semibold text-slate-500">
              Предпочтения по классу
              <select v-model="equipmentClass" class="mt-1 w-full rounded-xl border-0 bg-white px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 dark:bg-slate-900">
                <option value="">Не определился</option>
                <option value="economy">Эконом</option>
                <option value="standard">Цена / качество</option>
                <option value="premium">Премиум</option>
              </select>
            </label>
            <label class="block text-xs font-semibold text-slate-500 md:col-span-2">
              Комментарий
              <textarea
                v-model="managerComment"
                rows="3"
                class="mt-1 w-full resize-y rounded-xl border-0 bg-white px-4 py-3 text-sm focus:ring-2 focus:ring-teal-500 dark:bg-slate-900"
                placeholder="Контекст для сделки, КП или выезда"
              ></textarea>
            </label>
          </div>
        </section>
      </div>

      <div class="flex shrink-0 gap-3 border-t border-slate-100 bg-slate-50 px-6 py-4 dark:border-slate-800 dark:bg-slate-900">
        <button
          class="flex flex-1 items-center justify-center gap-2 rounded-xl bg-teal-600 py-3 font-bold text-white transition-colors hover:bg-teal-700 disabled:opacity-50"
          :disabled="isLoading"
          @click="submitQualify"
        >
          <span v-if="isLoading" class="material-icons-round animate-spin">refresh</span>
          <span v-else class="material-icons-round">arrow_forward</span>
          Создать сделку
        </button>
      </div>
    </div>
  </div>
</template>
