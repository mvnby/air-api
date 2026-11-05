import { computed, ref, watch, type Ref } from 'vue';
import { confirmDialog, notify } from '../../services/ui-feedback';
import { managerSession } from '../../services/manager-session';
import { getRoleLabel } from '../../features/documents/model/document-formatters';
import { ManagerContractsService, ManagerDocsService, ManagerDocumentSystemService, type DocumentLegalEntityItem, type DocumentTemplateItem, type ManagerCustomerContractItemResponse } from "../../client";
import { getApiErrorMessage } from "../../utils/api-errors";

export function useCustomerContractsPanel(customerId: Ref<number>) {

const error = ref('');

const contracts = ref<ManagerCustomerContractItemResponse[]>([]);

const contractsLoading = ref(false);
const issuers = ref<DocumentLegalEntityItem[]>([]);
const issuersLoading = ref(false);
const issuersError = ref('');
const scopeKey = computed(() => [customerId.value, managerSession.auth.value?.tenant_id, managerSession.auth.value?.storefront_id].join('/'));
let listRequest = 0;
let issuerRequest = 0;

const loadIssuers = async () => {
  const request = ++issuerRequest;
  const scope = scopeKey.value;
  issuersLoading.value = true;
  issuersError.value = '';
  try {
    const result = await ManagerDocumentSystemService.listManagerDocumentLegalEntities();
    if (request === issuerRequest && scope === scopeKey.value) issuers.value = result.items;
  } catch (e) {
    if (request === issuerRequest && scope === scopeKey.value) issuersError.value = `Не удалось загрузить юрлица: ${getApiErrorMessage(e)}`;
  } finally {
    if (request === issuerRequest && scope === scopeKey.value) issuersLoading.value = false;
  }
};

const contractSaving = ref(false);

const contractUploadSaving = ref(false);

const showContractForm = ref(false);

const showContractUploadForm = ref(false);

const contractTemplates = ref<DocumentTemplateItem[]>([]);

const openContractTemplates = computed(() => contractTemplates.value.filter((template) => template.is_open_contract));

const getTemplateRoleLabel = (templateId?: string | null) => {
  const template = contractTemplates.value.find((item) => item.id === templateId);
  return getRoleLabel(template?.document_role_type);
};

const toInputDate = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

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

const setToast = notify;

const loadCustomerContracts = async () => {
  if (!customerId.value) return;
  const request = ++listRequest;
  const scope = scopeKey.value;
  contractsLoading.value = true;
  error.value = "";
  try {
    const res = await ManagerContractsService.getManagerCustomerContracts(customerId.value);
    if (request === listRequest && scope === scopeKey.value) {
      contracts.value = res.items;
      if (contracts.value.length && !issuersLoading.value && !issuers.value.length) void loadIssuers();
    }
  } catch (e) {
    if (request === listRequest && scope === scopeKey.value) error.value = `Не удалось загрузить договоры: ${getApiErrorMessage(e)}`;
  } finally {
    if (request === listRequest && scope === scopeKey.value) contractsLoading.value = false;
  }
};

const loadContractTemplates = async () => {
  const scope = scopeKey.value;
  try {
    const res = await ManagerDocsService.getDocTemplates(
      'contract',
      undefined,
      customerId.value,
    );
    if (scope === scopeKey.value) contractTemplates.value = res.items;
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
  const id = customerId.value;
  if (!id || contract.customer_id !== id) return;
  if (!await confirmDialog({ title: 'Архивировать договор?', description: contract.number, confirmText: 'Архивировать', variant: 'warning' })) return;
  if (customerId.value !== id) return;
  try {
    await ManagerContractsService.archiveManagerCustomerContract(id, contract.id);
    await loadCustomerContracts();
    setToast('Договор архивирован');
  } catch (e) {
    setToast(`Не удалось архивировать договор: ${getApiErrorMessage(e)}`);
  }
};

const deleteContract = async (contract: ManagerCustomerContractItemResponse) => {
  const id = customerId.value;
  if (!id || contract.customer_id !== id || !contract.can_delete) return;
  if (!await confirmDialog({
    title: 'Удалить договор?',
    description: `${contract.number} будет удалён из CRM и Google Drive.`,
    confirmText: 'Удалить договор',
    variant: 'danger',
  })) return;
  if (customerId.value !== id) return;
  try {
    await ManagerContractsService.deleteManagerCustomerContract(id, contract.id);
    await loadCustomerContracts();
    setToast('Договор удален');
  } catch (e) {
    setToast(`Не удалось удалить договор: ${getApiErrorMessage(e)}`);
  }
};
watch(scopeKey, async (scope) => {
  issuerRequest++;
  issuers.value = [];
  issuersLoading.value = false;
  issuersError.value = '';
  contracts.value = [];
  contractTemplates.value = [];
  showContractForm.value = false;
  showContractUploadForm.value = false;
  await Promise.all([loadCustomerContracts(), loadContractTemplates()]);
  if (scope !== scopeKey.value) return;
  if (new URLSearchParams(window.location.search).get('openContract') === '1') openContractForm();
}, { immediate: true });
return {
  contracts, contractsLoading, error, loadCustomerContracts, issuers, issuersLoading, issuersError, loadIssuers,
  openContractUploadForm, openContractForm, showContractForm, createContract, contractForm,
  syncContractValidUntil, openContractTemplates, getTemplateRoleLabel, contractSaving, showContractUploadForm,
  uploadContract, contractUploadForm, syncUploadContractValidUntil, onContractUploadFileChange, contractUploadSaving,
  archiveContract, deleteContract,
};
}
