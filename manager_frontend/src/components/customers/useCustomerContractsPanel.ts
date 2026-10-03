import { computed, ref, onMounted, type Ref } from 'vue';
import { notify } from '../../services/ui-feedback';
import { confirmDialog } from "../../services/ui-feedback";
import { ManagerContractsService, ManagerDocsService, type DocumentTemplateItem, type ManagerCustomerContractItemResponse } from "../../client";
import { getApiErrorMessage } from "../../utils/api-errors";

export function useCustomerContractsPanel(customerId: Ref<number>) {

const error = ref('');

const contracts = ref<ManagerCustomerContractItemResponse[]>([]);

const contractsLoading = ref(false);

const contractSaving = ref(false);

const contractUploadSaving = ref(false);

const showContractForm = ref(false);

const showContractUploadForm = ref(false);

type DocumentRoleType = 'seller_buyer' | 'executor_customer' | 'contractor_customer' | 'seller_payer' | 'executor_payer';

const DOCUMENT_ROLE_OPTIONS: Array<{ value: DocumentRoleType; label: string }> = [
  { value: 'seller_buyer', label: 'Продавец / Покупатель' },
  { value: 'seller_payer', label: 'Продавец / Плательщик' },
  { value: 'executor_customer', label: 'Исполнитель / Заказчик' },
  { value: 'executor_payer', label: 'Исполнитель / Плательщик' },
  { value: 'contractor_customer', label: 'Подрядчик / Заказчик' },
];

const contractTemplates = ref<DocumentTemplateItem[]>([]);

const openContractTemplates = computed(() => contractTemplates.value.filter((template) => template.is_open_contract));

const normalizeRoleType = (value: unknown): DocumentRoleType => {
  const raw = String(value || '').trim();
  if (raw === 'executor_customer' || raw === 'contractor_customer' || raw === 'seller_payer' || raw === 'executor_payer') return raw;
  return 'seller_buyer';
};

const getRoleLabel = (value?: string | null) => (
  DOCUMENT_ROLE_OPTIONS.find((option) => option.value === normalizeRoleType(value))?.label || 'Продавец / Покупатель'
);

const getTemplateRoleLabel = (templateId?: string | null) => {
  const template = contractTemplates.value.find((item) => item.id === templateId);
  return getRoleLabel(template?.document_role_type);
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
  contractsLoading.value = true;
  error.value = "";
  try {
    const res = await ManagerContractsService.getManagerCustomerContracts(customerId.value);
    contracts.value = res.items;
  } catch (e) {
    error.value = `Не удалось загрузить договоры: ${getApiErrorMessage(e)}`;
  } finally {
    contractsLoading.value = false;
  }
};

const loadContractTemplates = async () => {
  try {
    const res = await ManagerDocsService.getDocTemplates(
      'contract',
      undefined,
      customerId.value,
    );
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
  if (!await confirmDialog({ title: 'Архивировать договор?', description: contract.number, confirmText: 'Архивировать', variant: 'warning' })) return;
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
  if (!await confirmDialog({
    title: 'Удалить договор?',
    description: `${contract.number} будет удалён из CRM и Google Drive.`,
    confirmText: 'Удалить договор',
    variant: 'danger',
  })) return;
  try {
    await ManagerContractsService.deleteManagerCustomerContract(customerId.value, contract.id);
    await loadCustomerContracts();
    setToast('Договор удален');
  } catch (e) {
    setToast(`Не удалось удалить договор: ${getApiErrorMessage(e)}`);
  }
};
onMounted(async () => { await Promise.all([loadCustomerContracts(), loadContractTemplates()]); if (new URLSearchParams(window.location.search).get('openContract') === '1') openContractForm(); });
return { contracts, openContractUploadForm, openContractForm, showContractForm, createContract, contractForm, syncContractValidUntil, openContractTemplates, getTemplateRoleLabel, contractSaving, showContractUploadForm, uploadContract, contractUploadForm, syncUploadContractValidUntil, onContractUploadFileChange, contractUploadSaving, contractsLoading, formatDateOnly, getRoleLabel, archiveContract, deleteContract, setToast, buildDefaultContractForm, loadCustomerContracts, toInputDate, contractTemplates, DOCUMENT_ROLE_OPTIONS, normalizeRoleType, error };
}
