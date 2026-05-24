<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ManagerContractsService, ManagerDocsService, ManagerOrdersService } from '../../client';
import type {
  DocumentTemplateItem,
  ManagerCustomerContractItemResponse,
  ManagerOrderDetailResponse,
  ManagerOrderDocumentItem,
} from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
import AdditionalConditionsLibrary from './AdditionalConditionsLibrary.vue';
import DocumentSendModal from './DocumentSendModal.vue';

type ToastType = 'success' | 'error';
type DocumentRoleType = 'seller_buyer' | 'executor_customer' | 'contractor_customer';

const props = defineProps<{
  order: ManagerOrderDetailResponse;
  activeProposalId?: number | null;
  beforeGenerate?: (type: string) => boolean | void | Promise<boolean | void>;
}>();

const emit = defineEmits<{
  refresh: [];
  toast: [payload: { message: string; type?: ToastType }];
}>();

const DOCUMENT_FILE_ACCEPT = '.pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const ONE_TIME_CONTRACT_VALUE = 'one-time-contract';

const DOCUMENT_TYPES = [
  { type: 'contract', label: 'Договор' },
  { type: 'invoice', label: 'Счет' },
  { type: 'act', label: 'Акт' },
  { type: 'defect_act', label: 'Дефектный акт' },
  { type: 'offer', label: 'КП' },
  { type: 'tn2', label: 'ТН-2' },
  { type: 'ttn1', label: 'ТТН-1' },
];

const DOCUMENT_ROLE_OPTIONS: Array<{ value: DocumentRoleType; label: string }> = [
  { value: 'seller_buyer', label: 'Продавец / Покупатель' },
  { value: 'executor_customer', label: 'Исполнитель / Заказчик' },
  { value: 'contractor_customer', label: 'Подрядчик / Заказчик' },
];

const documents = ref<ManagerOrderDocumentItem[]>([]);
const customerContracts = ref<ManagerCustomerContractItemResponse[]>([]);
const contractTemplates = ref<DocumentTemplateItem[]>([]);
const selectedCustomerContractId = ref<number | null>(props.order.customer_contract_id || null);
const selectedDocumentRoleType = ref<string | null>(props.order.document_role_type || null);
const selectedContractTemplateId = ref<string>('');
const additionalConditions = ref(props.order.additional_conditions || '');
const additionalConditionsSaved = ref(props.order.additional_conditions || '');
const isSavingAdditionalConditions = ref(false);
const documentDate = ref(new Date().toISOString().slice(0, 10));
const isGeneratingDoc = ref(false);
const processingDocId = ref<number | null>(null);
const docDropdownOpen = ref(false);
const showDocumentSendModal = ref(false);
const isUploadingDoc = ref(false);
const fileInputRef = ref<HTMLInputElement | null>(null);
const externalContractOpen = ref(false);
const externalContractNumber = ref('');
const externalContractDate = ref(new Date().toISOString().slice(0, 10));
const externalContractUrl = ref('');
const externalContractFile = ref<File | null>(null);
const isRegisteringExternalContract = ref(false);

const notify = (message: string, type: ToastType = 'success') => {
  emit('toast', { message, type });
};

const normalizeRoleType = (value: unknown): DocumentRoleType => {
  const raw = String(value || '').trim();
  if (raw === 'executor_customer' || raw === 'contractor_customer') return raw;
  return 'seller_buyer';
};

const getRoleLabel = (value?: string | null) => (
  DOCUMENT_ROLE_OPTIONS.find((option) => option.value === normalizeRoleType(value))?.label || 'Продавец / Покупатель'
);

const isCompanyOrder = computed(() => props.order.customer?.type === 'company' || !!props.order.customer?.inn);
const oneTimeContractDocument = computed(() => (
  [...documents.value]
    .filter((doc) => doc.doc_type === 'contract')
    .sort((a, b) => b.id - a.id)[0] || null
));
const hasOrderContract = computed(() => !!oneTimeContractDocument.value);
const hasContract = computed(() => (isCompanyOrder.value ? !!selectedCustomerContractId.value : false) || hasOrderContract.value);
const hasOrderInvoice = computed(() => documents.value.some((doc) => doc.doc_type === 'invoice'));
const hasClosingBaseDocument = computed(() => hasContract.value || hasOrderInvoice.value);
const selectedContractTemplate = computed(() => contractTemplates.value.find((template) => template.id === selectedContractTemplateId.value) || null);
const selectedOpenContract = computed(() => (
  customerContracts.value.find((contract) => contract.id === selectedCustomerContractId.value) || null
));
const inheritedDocumentRoleType = computed(() => normalizeRoleType(
  selectedDocumentRoleType.value
    || selectedOpenContract.value?.document_role_type
    || selectedContractTemplate.value?.document_role_type
    || props.order.effective_document_role_type
));
const documentSummary = computed(() => {
  const base = hasContract.value ? 'договор есть' : (hasOrderInvoice.value ? 'есть счет' : 'без договора');
  return `${documents.value.length} док. · ${base}`;
});
const hasDocumentSetupWarning = computed(() => isCompanyOrder.value && !selectedCustomerContractId.value && !hasClosingBaseDocument.value);

const datedDocumentTypes = new Set(['contract', 'act', 'defect_act', 'tn2', 'ttn1']);
const getDocumentDateForType = (type: string) => (
  datedDocumentTypes.has(type) && documentDate.value ? `${documentDate.value}T00:00:00` : undefined
);

const isDocumentTypeLocked = (type: string) => (
  type === 'act' ? !hasClosingBaseDocument.value : (type === 'ttn1' || type === 'tn2') && !hasContract.value
);
const lockedDocumentTitle = (type: string) => (
  type === 'act' ? 'Сначала создайте договор или счет' : 'Сначала создайте договор'
);

const documentProposalName = (doc: ManagerOrderDocumentItem) => {
  if (!doc.proposal_id) return '';
  const proposal = (props.order.proposals || []).find((item) => item.id === doc.proposal_id);
  return proposal?.name || `вариант #${doc.proposal_id}`;
};

const selectedContractBinding = computed({
  get: () => {
    if (selectedCustomerContractId.value) return `open:${selectedCustomerContractId.value}`;
    if (oneTimeContractDocument.value) return ONE_TIME_CONTRACT_VALUE;
    return '';
  },
  set: (value: string) => {
    void updateContractBinding(value);
  },
});

const selectedDocumentRoleBinding = computed({
  get: () => selectedDocumentRoleType.value || '',
  set: (value: string) => {
    void updateDocumentRoleBinding(value);
  },
});

const hasAdditionalConditionsChanges = computed(() => additionalConditions.value !== additionalConditionsSaved.value);

const loadDocuments = async () => {
  try {
    const res = await ManagerDocsService.getManagerOrderDocuments(props.order.id);
    documents.value = res.items;
  } catch (error) {
    console.error('Failed to load documents', error);
  }
};

const loadContractTemplates = async () => {
  try {
    const res = await ManagerDocsService.getDocTemplates('contract', props.order.id);
    contractTemplates.value = res.items.filter((template) => !template.is_open_contract);
    if (contractTemplates.value.length > 0 && contractTemplates.value[0]) {
      selectedContractTemplateId.value = contractTemplates.value[0].id;
    }
  } catch (error) {
    console.warn('Failed to load contract templates', error);
  }
};

const loadCustomerContracts = async () => {
  if (!props.order.customer?.id) {
    customerContracts.value = [];
    selectedCustomerContractId.value = null;
    return;
  }
  try {
    const res = await ManagerContractsService.getManagerCustomerContracts(props.order.customer.id);
    customerContracts.value = res.items.filter((contract) => contract.status === 'active');
    selectedCustomerContractId.value = props.order.customer_contract_id || null;
  } catch (error) {
    console.error('Failed to load customer contracts', error);
  }
};

const resetFromOrder = () => {
  selectedCustomerContractId.value = props.order.customer_contract_id || null;
  selectedDocumentRoleType.value = props.order.document_role_type || null;
  additionalConditionsSaved.value = props.order.additional_conditions || '';
  additionalConditions.value = props.order.additional_conditions || '';
};

watch(() => props.order.id, () => {
  resetFromOrder();
  void loadDocuments();
  void loadContractTemplates();
  void loadCustomerContracts();
}, { immediate: true });

watch(() => [
  props.order.customer_contract_id,
  props.order.document_role_type,
  props.order.additional_conditions,
], () => {
  resetFromOrder();
});

const saveAdditionalConditions = async (showSuccessToast = true) => {
  if (!hasAdditionalConditionsChanges.value) return true;
  const valueToSave = additionalConditions.value;
  isSavingAdditionalConditions.value = true;
  try {
    await ManagerOrdersService.patchManagerOrder(props.order.id, {
      additional_conditions: valueToSave,
    });
    additionalConditionsSaved.value = valueToSave;
    if (showSuccessToast) notify('Условия сохранены', 'success');
    return true;
  } catch (error) {
    notify(`Ошибка сохранения условий: ${getApiErrorMessage(error)}`, 'error');
    return false;
  } finally {
    isSavingAdditionalConditions.value = false;
  }
};

const useOneTimeContractForClosingDocs = async () => {
  if (!selectedCustomerContractId.value) return;
  selectedCustomerContractId.value = null;
  await ManagerOrdersService.patchManagerOrder(props.order.id, {
    customer_contract_id: null,
  });
};

const updateContractBinding = async (value: string) => {
  const nextCustomerContractId = value.startsWith('open:') ? Number(value.slice(5)) : null;
  if (nextCustomerContractId !== null && Number.isNaN(nextCustomerContractId)) return;
  try {
    selectedCustomerContractId.value = nextCustomerContractId;
    await ManagerOrdersService.patchManagerOrder(props.order.id, {
      customer_contract_id: nextCustomerContractId,
    });
    emit('refresh');
  } catch (error) {
    notify(`Ошибка выбора договора: ${getApiErrorMessage(error)}`, 'error');
  }
};

const updateDocumentRoleBinding = async (value: string) => {
  const nextRole = value ? normalizeRoleType(value) : null;
  try {
    selectedDocumentRoleType.value = nextRole;
    await ManagerOrdersService.patchManagerOrder(props.order.id, {
      document_role_type: nextRole,
    });
    emit('refresh');
  } catch (error) {
    notify(`Ошибка выбора ролей: ${getApiErrorMessage(error)}`, 'error');
  }
};

const openCustomerProfileForContract = () => {
  const customerId = props.order.customer?.id;
  if (!customerId) return;
  const currentPath = `${window.location.pathname}${window.location.search}`;
  const target = `/manager/customers/profile?customerId=${customerId}&openContract=1&returnTo=${encodeURIComponent(currentPath)}`;
  window.history.pushState({}, '', target);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

const openDocumentSendModal = () => {
  if (!documents.value.length) {
    notify('Сначала создайте или загрузите документ', 'error');
    return;
  }
  showDocumentSendModal.value = true;
};

const handleDocumentsSent = () => {
  notify('Письмо отправлено', 'success');
  emit('refresh');
};

const generateDocument = async (type: string) => {
  isGeneratingDoc.value = true;
  docDropdownOpen.value = false;
  try {
    const beforeResult = await props.beforeGenerate?.(type);
    if (beforeResult === false) return;
    if (!(await saveAdditionalConditions(false))) return;
    if (type === 'contract' && isCompanyOrder.value) {
      await useOneTimeContractForClosingDocs();
    }
    const template = (type === 'contract' && selectedContractTemplateId.value)
      ? selectedContractTemplate.value
      : undefined;
    const proposalId = type === 'offer' ? (props.activeProposalId ?? undefined) : undefined;
    const res = await ManagerOrdersService.generateManagerOrderDocument(
      props.order.id,
      type,
      template?.document_template_id ?? undefined,
      template && !template.document_template_id ? template.id : undefined,
      getDocumentDateForType(type),
      proposalId,
    );
    window.open(res.edit_url, '_blank');
    await loadDocuments();
    emit('refresh');
    notify('Документ создан', 'success');
  } catch (error) {
    notify(`Ошибка генерации: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    isGeneratingDoc.value = false;
  }
};

const triggerFileUpload = () => {
  fileInputRef.value?.click();
};

const handleFileUpload = async (event: Event) => {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0] as File | undefined;
  if (!file) return;

  isUploadingDoc.value = true;
  try {
    await ManagerDocsService.uploadManagerOrderDocument(props.order.id, { file });
    await loadDocuments();
    emit('refresh');
    notify('Документ загружен', 'success');
  } catch (error) {
    notify(`Ошибка загрузки: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    isUploadingDoc.value = false;
    if (fileInputRef.value) fileInputRef.value.value = '';
  }
};

const handleAttachDocumentFile = async (doc: ManagerOrderDocumentItem, event: Event) => {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0] as File | undefined;
  if (!file) return;

  processingDocId.value = doc.id;
  try {
    await ManagerDocsService.attachManagerDocFile(doc.id, { file });
    await loadDocuments();
    emit('refresh');
    notify('Файл прикреплен', 'success');
  } catch (error) {
    notify(`Ошибка прикрепления: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    processingDocId.value = null;
    target.value = '';
  }
};

const downloadDocument = async (doc: ManagerOrderDocumentItem) => {
  processingDocId.value = doc.id;
  try {
    const response = await ManagerDocsService.getManagerDocDownload(doc.id);
    const url = window.URL.createObjectURL(new Blob([response]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `${doc.number || doc.doc_type}.pdf`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  } catch (error) {
    notify('Ошибка скачивания', 'error');
  } finally {
    processingDocId.value = null;
  }
};

const deleteDocument = async (docId: number) => {
  if (!confirm('Удалить документ?')) return;
  processingDocId.value = docId;
  try {
    await ManagerDocsService.deleteManagerDoc(docId);
    await loadDocuments();
    emit('refresh');
    notify('Документ удален', 'success');
  } catch (error) {
    notify('Ошибка удаления', 'error');
  } finally {
    processingDocId.value = null;
  }
};

const handleExternalContractFile = (event: Event) => {
  const target = event.target as HTMLInputElement;
  externalContractFile.value = target.files?.[0] || null;
};

const resetExternalContractForm = () => {
  externalContractNumber.value = '';
  externalContractDate.value = new Date().toISOString().slice(0, 10);
  externalContractUrl.value = '';
  externalContractFile.value = null;
};

const registerExternalContract = async () => {
  const number = externalContractNumber.value.trim();
  if (!number) {
    notify('Укажите номер договора', 'error');
    return;
  }
  if (!externalContractDate.value) {
    notify('Укажите дату договора', 'error');
    return;
  }

  isRegisteringExternalContract.value = true;
  try {
    await ManagerDocsService.registerManagerExternalContract(props.order.id, {
      number,
      contract_date: `${externalContractDate.value}T00:00:00`,
      external_url: externalContractUrl.value.trim() || undefined,
      file: externalContractFile.value || undefined,
    });
    await loadDocuments();
    selectedCustomerContractId.value = null;
    externalContractOpen.value = false;
    resetExternalContractForm();
    emit('refresh');
    notify('Внешний договор добавлен', 'success');
  } catch (error) {
    notify(`Ошибка добавления договора: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    isRegisteringExternalContract.value = false;
  }
};
</script>

<template>
  <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700/60 dark:bg-slate-900/60 sm:p-5">
    <DocumentSendModal
      v-model="showDocumentSendModal"
      :order="order"
      :documents="documents"
      @sent="handleDocumentsSent"
    />

    <div class="mb-4 flex flex-col gap-3 border-b border-slate-100 pb-4 dark:border-slate-800 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h3 class="font-['Space_Grotesk'] text-lg font-bold text-slate-900 dark:text-white">Документы</h3>
        <p
          class="mt-1 text-xs font-medium"
          :class="hasDocumentSetupWarning ? 'text-amber-600 dark:text-amber-400' : 'text-slate-500 dark:text-slate-400'"
        >
          {{ documentSummary }}
        </p>
      </div>

      <div class="relative flex flex-wrap items-center gap-2 sm:justify-end">
        <button
          class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-teal-600 px-3 text-sm font-semibold text-white shadow-sm hover:bg-teal-700 focus:outline-none focus:ring-2 focus:ring-teal-500/50 disabled:opacity-50"
          title="Отправить документы"
          :disabled="!documents.length || isUploadingDoc || !!processingDocId || isGeneratingDoc"
          @click="openDocumentSendModal"
        >
          <span class="material-icons-round text-[18px]">send</span>
          Отправить
        </button>

        <button
          class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[#007f80] px-3 text-sm font-semibold text-white shadow-sm hover:bg-teal-600 focus:outline-none focus:ring-2 focus:ring-teal-500/50 disabled:opacity-50"
          :disabled="isGeneratingDoc || !!processingDocId || isUploadingDoc"
          @click="docDropdownOpen = !docDropdownOpen"
        >
          <span class="material-icons-round text-[18px]">add_circle</span>
          Создать
        </button>

        <input ref="fileInputRef" type="file" class="hidden" :accept="DOCUMENT_FILE_ACCEPT" @change="handleFileUpload" />
        <button
          class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-slate-700 px-3 text-sm font-semibold text-white shadow-sm hover:bg-slate-600 focus:outline-none focus:ring-2 focus:ring-slate-500/50 disabled:opacity-50"
          title="Загрузить файл"
          :disabled="isUploadingDoc || !!processingDocId || isGeneratingDoc"
          @click="triggerFileUpload"
        >
          <span v-if="isUploadingDoc" class="material-icons-round animate-spin text-[18px]">loop</span>
          <span v-else class="material-icons-round text-[18px]">upload_file</span>
          Загрузить
        </button>

        <div
          v-if="docDropdownOpen"
          class="absolute right-0 top-full z-20 mt-2 w-64 rounded-xl border border-slate-200 bg-white p-1 text-slate-800 shadow-xl dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
        >
          <div v-if="contractTemplates.length > 1" class="border-b border-slate-200 px-3 py-2 dark:border-slate-700">
            <label class="mb-1 block text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Шаблон договора</label>
            <select
              v-model="selectedContractTemplateId"
              class="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200"
            >
              <option v-for="template in contractTemplates" :key="template.id" :value="template.id">{{ template.name }}</option>
            </select>
          </div>

          <div class="border-b border-slate-200 px-3 py-2 dark:border-slate-700">
            <label class="mb-1 block text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Дата документа</label>
            <input
              v-model="documentDate"
              type="date"
              class="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200"
            />
          </div>

          <button
            v-for="dtype in DOCUMENT_TYPES"
            :key="dtype.type"
            class="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-100 disabled:text-slate-400 disabled:opacity-70 disabled:hover:bg-transparent dark:text-slate-200 dark:hover:bg-slate-700 dark:disabled:text-slate-500"
            :disabled="isDocumentTypeLocked(dtype.type)"
            :title="isDocumentTypeLocked(dtype.type) ? lockedDocumentTitle(dtype.type) : ''"
            @click="generateDocument(dtype.type)"
          >
            {{ dtype.label }}
            <span v-if="isDocumentTypeLocked(dtype.type)" class="material-icons-round text-[16px] text-amber-500">lock</span>
          </button>
        </div>
      </div>
    </div>

    <div class="space-y-3">
      <div v-if="isCompanyOrder" class="rounded-xl border border-slate-200 bg-slate-50/70 p-3 dark:border-slate-700/50 dark:bg-slate-800/40">
        <div class="mb-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <label class="block text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Договор для актов и накладных</label>
          <button
            type="button"
            class="inline-flex w-fit items-center gap-1 rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
            @click="externalContractOpen = !externalContractOpen"
          >
            <span class="material-icons-round text-[16px]">post_add</span>
            Внешний договор
          </button>
        </div>

        <select
          v-model="selectedContractBinding"
          class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
        >
          <option value="">Выберите договор</option>
          <option v-if="oneTimeContractDocument" :value="ONE_TIME_CONTRACT_VALUE">
            Разовый договор заказа · {{ oneTimeContractDocument.number }}
          </option>
          <option v-for="contract in customerContracts" :key="contract.id" :value="`open:${contract.id}`">
            Открытый договор · {{ contract.number }} · до {{ new Date(contract.valid_until).toLocaleDateString('ru-RU') }}
          </option>
        </select>

        <p v-if="oneTimeContractDocument && customerContracts.length" class="mt-2 text-xs text-slate-500 dark:text-slate-400">
          Выберите, куда ссылать закрывающие документы: на разовый договор заказа или на открытый договор клиента.
        </p>

        <form
          v-if="externalContractOpen"
          class="mt-3 space-y-3 rounded-lg border border-dashed border-teal-300 bg-teal-50/40 p-3 dark:border-teal-700/70 dark:bg-teal-950/20"
          @submit.prevent="registerExternalContract"
        >
          <div class="grid gap-3 sm:grid-cols-2">
            <label class="text-xs font-medium text-slate-600 dark:text-slate-300">Номер договора
              <input
                v-model="externalContractNumber"
                type="text"
                class="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                placeholder="Например, 44-ЭА/2026"
              />
            </label>
            <label class="text-xs font-medium text-slate-600 dark:text-slate-300">Дата договора
              <input
                v-model="externalContractDate"
                type="date"
                class="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              />
            </label>
          </div>
          <label class="block text-xs font-medium text-slate-600 dark:text-slate-300">Ссылка на договор
            <input
              v-model="externalContractUrl"
              type="url"
              class="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              placeholder="https://..."
            />
          </label>
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <label class="inline-flex cursor-pointer items-center gap-2 text-xs font-semibold text-slate-600 dark:text-slate-300">
              <span class="material-icons-round text-[18px] text-teal-600 dark:text-teal-400">upload_file</span>
              <span>{{ externalContractFile?.name || 'Прикрепить файл вместо ссылки' }}</span>
              <input type="file" class="hidden" :accept="DOCUMENT_FILE_ACCEPT" @change="handleExternalContractFile" />
            </label>
            <div class="flex justify-end gap-2">
              <button
                type="button"
                class="rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
                @click="externalContractOpen = false"
              >
                Отмена
              </button>
              <button
                type="submit"
                class="inline-flex items-center gap-1 rounded-lg bg-teal-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-teal-700 disabled:opacity-60"
                :disabled="isRegisteringExternalContract"
              >
                <span v-if="isRegisteringExternalContract" class="material-icons-round animate-spin text-[16px]">loop</span>
                <span v-else class="material-icons-round text-[16px]">check</span>
                Добавить договор
              </button>
            </div>
          </div>
        </form>

        <div
          v-if="customerContracts.length === 0"
          class="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed border-slate-300 bg-white p-3 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-800/50 dark:text-slate-300"
        >
          <span>У клиента нет открытых договоров.</span>
          <button
            type="button"
            class="rounded-lg bg-teal-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-teal-700 focus:outline-none focus:ring-2 focus:ring-teal-500/50"
            @click="openCustomerProfileForContract"
          >
            Создать открытый договор
          </button>
        </div>
        <p v-else-if="!selectedCustomerContractId && !hasClosingBaseDocument" class="mt-2 text-xs text-amber-600 dark:text-amber-400">
          Для актов нужен договор или счет, для накладных нужен договор.
        </p>
      </div>

      <AdditionalConditionsLibrary
        v-model="additionalConditions"
        :saving="isSavingAdditionalConditions"
      />

      <div class="rounded-xl border border-slate-200 bg-slate-50/70 p-3 dark:border-slate-700/50 dark:bg-slate-800/40">
        <label class="mb-1 block text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Роли сторон в актах и счетах</label>
        <select
          v-model="selectedDocumentRoleBinding"
          class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
        >
          <option value="">По договору / шаблону · {{ getRoleLabel(inheritedDocumentRoleType) }}</option>
          <option v-for="option in DOCUMENT_ROLE_OPTIONS" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </div>

      <div v-if="documents.length" class="space-y-3">
        <div
          v-for="doc in documents"
          :key="doc.id"
          class="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-3 text-slate-700 shadow-sm dark:border-slate-700/50 dark:bg-[#1e293b] dark:text-slate-300 dark:shadow-none"
        >
          <div class="flex min-w-0 items-center gap-3">
            <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-slate-100 text-teal-600 dark:bg-slate-800 dark:text-teal-400">
              <span class="material-icons-round text-xl">description</span>
            </div>
            <div class="min-w-0">
              <p class="truncate text-sm font-medium text-slate-900 dark:text-white">{{ doc.number || doc.doc_type }}</p>
              <p class="truncate text-xs text-slate-500 dark:text-slate-400">
                {{ new Date(doc.date).toLocaleDateString('ru-RU') }} · <span class="uppercase">{{ doc.doc_type }}</span>
                <span v-if="documentProposalName(doc)"> · {{ documentProposalName(doc) }}</span>
              </p>
            </div>
          </div>
          <div class="flex shrink-0 items-center gap-1 sm:gap-2">
            <a
              v-if="doc.edit_url"
              :href="doc.edit_url"
              target="_blank"
              class="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-white"
              title="Открыть"
            >
              <span class="material-icons-round text-[18px]">open_in_new</span>
            </a>
            <button
              v-if="doc.is_downloadable"
              class="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-900 disabled:opacity-50 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-white"
              :disabled="processingDocId === doc.id"
              title="Скачать PDF"
              @click="downloadDocument(doc)"
            >
              <span class="material-icons-round text-[18px]">download</span>
            </button>
            <label
              v-else
              class="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-teal-600 hover:bg-teal-50 hover:text-teal-700 dark:text-teal-400 dark:hover:bg-teal-900/30 dark:hover:text-teal-300"
              title="Добавить файл"
            >
              <span class="material-icons-round text-[18px]">attach_file</span>
              <input type="file" class="hidden" :accept="DOCUMENT_FILE_ACCEPT" :disabled="processingDocId === doc.id" @change="handleAttachDocumentFile(doc, $event)" />
            </label>
            <button
              class="flex h-8 w-8 items-center justify-center rounded-lg text-red-400 hover:bg-red-500/10 hover:text-red-500 disabled:opacity-50"
              :disabled="processingDocId === doc.id"
              title="Удалить"
              @click="deleteDocument(doc.id)"
            >
              <span class="material-icons-round text-[18px]">delete</span>
            </button>
          </div>
        </div>
      </div>
      <div v-else class="rounded-xl border border-dashed border-slate-300 py-5 text-center text-sm italic text-slate-500 dark:border-slate-700">
        Нет сформированных документов
      </div>
    </div>
  </section>
</template>
