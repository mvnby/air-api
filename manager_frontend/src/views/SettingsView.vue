<script setup lang="ts">
import { computed, ref, onMounted } from 'vue';
import { api } from '../api';
import type {
    DocumentTemplateItem,
    DocumentTemplatePayload,
    ManagerCatalogCustomerItemResponse,
    ManagerGoogleAuthStatusResponse,
    ManagerRepairComplaintPresetCreatePayload,
    ManagerRepairComplaintPresetResponse,
    ManagerRepairComplaintPresetUpdatePayload,
    ManagerSettingResponse,
    ManagerSettingUpdatePayload,
} from '../client';
import { ManagerDocsService, ManagerRepairComplaintsService, ManagerSettingsService } from '../client';
import { getApiErrorMessage } from '../utils/api-errors';

const settings = ref<ManagerSettingResponse[]>([]);
const loading = ref(false);
const error = ref('');
const toast = ref('');
const toastType = ref<'success' | 'error'>('success');

// A set to keep track of which settings are currently being saved
const savingKeys = ref<Set<string>>(new Set());
type DocumentRoleType = 'seller_buyer' | 'executor_customer' | 'contractor_customer';
type SettingsTab = 'general' | 'documentTemplates' | 'repairComplaints';
type ManagedDocumentType = 'contract' | 'act' | 'invoice' | 'defect_act';
type DocumentTemplateFileOption = {
    id: string;
    name: string;
    mime_type?: string | null;
    created_time?: string | null;
};
interface ContractTemplateForm {
    id: string;
    name: string;
    document_role_type: DocumentRoleType;
    is_open_contract: boolean;
}
type DocumentTemplateForm = {
    document_template_id?: number | null;
    name: string;
    doc_type: ManagedDocumentType;
    google_template_id: string;
    document_role_type: DocumentRoleType;
    description: string;
    is_default: boolean;
    is_active: boolean;
    is_open_contract: boolean;
    client_restricted: boolean;
    sort_order: number;
    customer_ids: number[];
    linked_contract_template_ids: number[];
    linked_act_template_ids: number[];
};
type RepairComplaintPresetForm = {
    id?: number | null;
    complaint_group: string;
    customer_phrase: string;
    document_wording: string;
    likely_diagnosis: string;
    is_favorite: boolean;
    is_active: boolean;
    sort_order: number;
    comment: string;
};
const DOCUMENT_ROLE_OPTIONS: Array<{ value: DocumentRoleType; label: string }> = [
    { value: 'seller_buyer', label: 'Продавец / Покупатель' },
    { value: 'executor_customer', label: 'Исполнитель / Заказчик' },
    { value: 'contractor_customer', label: 'Подрядчик / Заказчик' },
];
const contractTemplateDrafts = ref<Record<string, ContractTemplateForm[]>>({});
const documentTemplates = ref<DocumentTemplateForm[]>([]);
const customers = ref<ManagerCatalogCustomerItemResponse[]>([]);
const templateFiles = ref<DocumentTemplateFileOption[]>([]);
const customerSearch = ref('');
const templateFolderId = ref('1SClclCJS2FUVtfF-vbVqN8zI77Sl_E9t');
const activeSettingsTab = ref<SettingsTab>('general');
const loadingTemplateFiles = ref(false);
const loadingCustomerSearch = ref(false);
const savingTemplateKeys = ref<Set<string>>(new Set());
const deletingTemplateId = ref<number | null>(null);
const repairComplaintPresets = ref<RepairComplaintPresetForm[]>([]);
const repairComplaintSearch = ref('');
const repairComplaintGroupFilter = ref('');
const loadingRepairComplaints = ref(false);
const savingRepairComplaintKeys = ref<Set<string>>(new Set());
const deletingRepairComplaintId = ref<number | null>(null);

// Create form
const showCreateForm = ref(false);
const newKey = ref('');
const newValue = ref('');
const newDescription = ref('');
const creating = ref(false);
const googleAuthStatus = ref<ManagerGoogleAuthStatusResponse | null>(null);
const googleAuthLoading = ref(false);
const googleAuthBusy = ref(false);

const goToBackups = () => {
    if (window.location.pathname !== '/manager/settings/backup') {
        window.history.pushState({}, '', '/manager/settings/backup');
        window.dispatchEvent(new PopStateEvent('popstate'));
    }
};

const setToast = (msg: string, type: 'success' | 'error' = 'success') => {
    toast.value = msg;
    toastType.value = type;
    window.setTimeout(() => { toast.value = ''; }, 3000);
}

const DOCUMENT_TYPE_OPTIONS: Array<{ value: ManagedDocumentType; label: string; addLabel: string }> = [
    { value: 'contract', label: 'Договор', addLabel: 'Договор' },
    { value: 'invoice', label: 'Счет / счет-договор', addLabel: 'Счет' },
    { value: 'act', label: 'Акт', addLabel: 'Акт' },
    { value: 'defect_act', label: 'Дефектный акт', addLabel: 'Дефектный акт' },
];
const REPAIR_COMPLAINT_GROUP_OPTIONS = [
    { value: 'water_drainage', label: 'Вода / дренаж' },
    { value: 'noise_vibration', label: 'Шум / вибрация' },
    { value: 'cooling', label: 'Охлаждение' },
    { value: 'smell_contamination', label: 'Запах / загрязнение' },
    { value: 'control_electronics', label: 'Управление / электроника' },
    { value: 'freezing', label: 'Обмерзание' },
    { value: 'shutdown_error', label: 'Отключение / ошибка' },
    { value: 'other', label: 'Другое' },
];

const emptyDocumentTemplate = (docType: ManagedDocumentType = 'contract'): DocumentTemplateForm => ({
    document_template_id: null,
    name: '',
    doc_type: docType,
    google_template_id: '',
    document_role_type: 'seller_buyer',
    description: '',
    is_default: false,
    is_active: true,
    is_open_contract: false,
    client_restricted: false,
    sort_order: documentTemplates.value.length * 10,
    customer_ids: [],
    linked_contract_template_ids: [],
    linked_act_template_ids: [],
});

const mapTemplateItemToForm = (item: DocumentTemplateItem): DocumentTemplateForm => ({
    document_template_id: item.document_template_id ?? null,
    name: item.name || '',
    doc_type: normalizeDocumentType(item.doc_type),
    google_template_id: item.id || '',
    document_role_type: normalizeRoleType(item.document_role_type),
    description: item.description || '',
    is_default: item.is_default === true,
    is_active: item.is_active !== false,
    is_open_contract: item.is_open_contract === true,
    client_restricted: item.client_restricted === true,
    sort_order: Number(item.sort_order ?? 0),
    customer_ids: [...(item.customer_ids ?? [])],
    linked_contract_template_ids: [...(item.linked_contract_template_ids ?? [])],
    linked_act_template_ids: [...(item.linked_act_template_ids ?? [])],
});

const emptyRepairComplaintPreset = (): RepairComplaintPresetForm => ({
    id: null,
    complaint_group: repairComplaintGroupFilter.value || 'other',
    customer_phrase: '',
    document_wording: '',
    likely_diagnosis: '',
    is_favorite: false,
    is_active: true,
    sort_order: repairComplaintPresets.value.length * 10,
    comment: '',
});

const mapRepairComplaintPresetToForm = (item: ManagerRepairComplaintPresetResponse): RepairComplaintPresetForm => ({
    id: item.id,
    complaint_group: item.complaint_group || 'other',
    customer_phrase: item.customer_phrase || '',
    document_wording: item.document_wording || '',
    likely_diagnosis: item.likely_diagnosis || '',
    is_favorite: item.is_favorite === true,
    is_active: item.is_active !== false,
    sort_order: Number(item.sort_order ?? 0),
    comment: item.comment || '',
});

const repairComplaintPayload = (preset: RepairComplaintPresetForm): ManagerRepairComplaintPresetCreatePayload => ({
    complaint_group: preset.complaint_group.trim() || 'other',
    customer_phrase: preset.customer_phrase.trim(),
    document_wording: preset.document_wording.trim(),
    likely_diagnosis: preset.likely_diagnosis.trim(),
    is_favorite: preset.is_favorite,
    is_active: preset.is_active,
    sort_order: Number(preset.sort_order || 0),
    comment: preset.comment.trim() || undefined,
});

const documentTemplatePayload = (template: DocumentTemplateForm): DocumentTemplatePayload => ({
    name: template.name.trim(),
    doc_type: template.doc_type,
    google_template_id: template.google_template_id.trim(),
    document_role_type: normalizeRoleType(template.document_role_type),
    description: template.description.trim() || undefined,
    is_default: template.is_default,
    is_active: template.is_active,
    is_open_contract: template.doc_type === 'contract' ? template.is_open_contract : false,
    client_restricted: template.client_restricted,
    sort_order: Number(template.sort_order || 0),
    customer_ids: template.customer_ids,
    linked_contract_template_ids: template.doc_type === 'act' ? template.linked_contract_template_ids : [],
    linked_act_template_ids: template.doc_type === 'contract' || template.doc_type === 'invoice' ? template.linked_act_template_ids : [],
});

const contractDocumentTemplates = computed(() =>
    documentTemplates.value.filter((template) => ['contract', 'invoice'].includes(template.doc_type) && template.document_template_id),
);
const actDocumentTemplates = computed(() =>
    documentTemplates.value.filter((template) => template.doc_type === 'act' && template.document_template_id),
);
const selectedCustomerMap = computed(() => new Map(customers.value.map((customer) => [customer.id, customer])));
const filteredTemplateFiles = computed(() => {
    const usedIds = new Set(documentTemplates.value.map((template) => template.google_template_id).filter(Boolean));
    return templateFiles.value.filter((file) => file.id && (!usedIds.has(file.id) || documentTemplates.value.some((template) => template.google_template_id === file.id)));
});

const loadGoogleAuthStatus = async () => {
    googleAuthLoading.value = true;
    try {
        googleAuthStatus.value = await api.getManagerGoogleAuthStatus();
    } catch (e) {
        setToast(getApiErrorMessage(e), 'error');
    } finally {
        googleAuthLoading.value = false;
    }
};

const openGoogleAuth = async () => {
    googleAuthBusy.value = true;
    try {
        const response = await api.getManagerGoogleAuthUrl();
        window.open(response.url, '_blank', 'noopener,noreferrer');
        setToast('Открыли Google Login в новой вкладке');
    } catch (e) {
        setToast(getApiErrorMessage(e), 'error');
    } finally {
        googleAuthBusy.value = false;
    }
};

const loadSettings = async () => {
    loading.value = true;
    error.value = '';
    try {
        const res = await api.listManagerSettings();
        settings.value = res.items.filter((setting) => setting.key !== 'contract_templates');
        contractTemplateDrafts.value = Object.fromEntries(
            res.items
                .filter((setting) => setting.key === 'contract_templates')
                .map((setting) => [setting.key, parseContractTemplates(setting.value)]),
        );
    } catch (e) {
        error.value = getApiErrorMessage(e);
    } finally {
        loading.value = false;
    }
};

const loadDocumentTemplates = async () => {
    try {
        const res = await ManagerDocsService.listManagerDocumentTemplates();
        documentTemplates.value = res.items.map(mapTemplateItemToForm);
    } catch (e) {
        setToast(getApiErrorMessage(e), 'error');
    }
};

const loadRepairComplaintPresets = async () => {
    loadingRepairComplaints.value = true;
    try {
        const res = await ManagerRepairComplaintsService.listManagerRepairComplaintPresets(
            repairComplaintSearch.value.trim(),
            repairComplaintGroupFilter.value || null,
            true,
            false,
            200,
        );
        repairComplaintPresets.value = res.items.map(mapRepairComplaintPresetToForm);
    } catch (e) {
        setToast(getApiErrorMessage(e), 'error');
    } finally {
        loadingRepairComplaints.value = false;
    }
};

const addRepairComplaintPreset = () => {
    repairComplaintPresets.value = [emptyRepairComplaintPreset(), ...repairComplaintPresets.value];
};

const saveRepairComplaintPreset = async (preset: RepairComplaintPresetForm) => {
    const key = String(preset.id || `new:${preset.complaint_group}:${preset.sort_order}`);
    if (savingRepairComplaintKeys.value.has(key)) return;
    if (!preset.customer_phrase.trim()) {
        setToast('Заполните жалобу клиента', 'error');
        return;
    }
    savingRepairComplaintKeys.value.add(key);
    try {
        const payload = repairComplaintPayload(preset);
        const saved = preset.id
            ? await ManagerRepairComplaintsService.updateManagerRepairComplaintPreset(preset.id, payload as ManagerRepairComplaintPresetUpdatePayload)
            : await ManagerRepairComplaintsService.createManagerRepairComplaintPreset(payload);
        const savedForm = mapRepairComplaintPresetToForm(saved);
        const index = repairComplaintPresets.value.indexOf(preset);
        if (index >= 0) {
            repairComplaintPresets.value[index] = savedForm;
        }
        setToast('Пресет жалобы сохранен');
    } catch (e) {
        setToast(getApiErrorMessage(e), 'error');
    } finally {
        savingRepairComplaintKeys.value.delete(key);
    }
};

const deleteRepairComplaintPreset = async (preset: RepairComplaintPresetForm) => {
    if (!preset.id) {
        repairComplaintPresets.value = repairComplaintPresets.value.filter((item) => item !== preset);
        return;
    }
    if (!confirm(`Удалить пресет "${preset.customer_phrase}"?`)) return;
    deletingRepairComplaintId.value = preset.id;
    try {
        await ManagerRepairComplaintsService.deleteManagerRepairComplaintPreset(preset.id);
        repairComplaintPresets.value = repairComplaintPresets.value.filter((item) => item.id !== preset.id);
        setToast('Пресет жалобы удален');
    } catch (e) {
        setToast(getApiErrorMessage(e), 'error');
    } finally {
        deletingRepairComplaintId.value = null;
    }
};

const loadCustomers = async (search = '') => {
    loadingCustomerSearch.value = true;
    try {
        const res = await api.getManagerCustomers(1, 20, search.trim() || undefined, undefined, false);
        const selectedIds = new Set(documentTemplates.value.flatMap((template) => template.customer_ids));
        const existingSelected = customers.value.filter((customer) => selectedIds.has(customer.id));
        const merged = [...existingSelected, ...res.items];
        customers.value = Array.from(new Map(merged.map((customer) => [customer.id, customer])).values());
    } catch (e) {
        setToast(getApiErrorMessage(e), 'error');
    } finally {
        loadingCustomerSearch.value = false;
    }
};

const loadTemplateFiles = async () => {
    loadingTemplateFiles.value = true;
    try {
        const res = await ManagerDocsService.listManagerDocumentTemplateFiles(templateFolderId.value.trim() || undefined, 100);
        templateFiles.value = res.items.map((item) => ({
            id: item.id,
            name: item.name,
            mime_type: item.mime_type,
            created_time: item.created_time,
        }));
    } catch (e) {
        setToast(getApiErrorMessage(e), 'error');
    } finally {
        loadingTemplateFiles.value = false;
    }
};

const addDocumentTemplate = (docType: ManagedDocumentType) => {
    documentTemplates.value = [emptyDocumentTemplate(docType), ...documentTemplates.value];
};

const selectTemplateFile = (template: DocumentTemplateForm, fileId: string) => {
    template.google_template_id = fileId;
    const file = templateFiles.value.find((item) => item.id === fileId);
    if (file && !template.name.trim()) {
        template.name = file.name.replace(/\.[^.]+$/, '');
    }
};

const selectedCustomersForTemplate = (template: DocumentTemplateForm) => (
    template.customer_ids
        .map((customerId) => selectedCustomerMap.value.get(customerId))
        .filter((customer): customer is ManagerCatalogCustomerItemResponse => Boolean(customer))
);

const addCustomerToTemplate = (template: DocumentTemplateForm, customerId: number | string) => {
    const normalizedId = Number(customerId);
    if (!normalizedId || template.customer_ids.includes(normalizedId)) return;
    template.customer_ids = [...template.customer_ids, normalizedId];
    template.client_restricted = true;
};

const removeCustomerFromTemplate = (template: DocumentTemplateForm, customerId: number) => {
    template.customer_ids = template.customer_ids.filter((id) => id !== customerId);
    if (!template.customer_ids.length) {
        template.client_restricted = false;
    }
};

const customerLabel = (customer: ManagerCatalogCustomerItemResponse) => {
    const title = customer.full_legal_name || customer.name || `Клиент #${customer.id}`;
    return customer.inn ? `${title} · УНП ${customer.inn}` : title;
};

const saveDocumentTemplate = async (template: DocumentTemplateForm) => {
    const key = String(template.document_template_id || `new:${template.doc_type}:${template.sort_order}`);
    if (savingTemplateKeys.value.has(key)) return;
    if (!template.name.trim() || !template.google_template_id.trim()) {
        setToast('Заполните название и Google Template ID', 'error');
        return;
    }
    savingTemplateKeys.value.add(key);
    try {
        const payload = documentTemplatePayload(template);
        const saved = template.document_template_id
            ? await ManagerDocsService.patchManagerDocumentTemplate(template.document_template_id, payload)
            : await ManagerDocsService.createManagerDocumentTemplate(payload);
        const savedForm = mapTemplateItemToForm(saved);
        const index = documentTemplates.value.indexOf(template);
        if (index >= 0) {
            documentTemplates.value[index] = savedForm;
        }
        setToast('Шаблон сохранен');
    } catch (e) {
        setToast(getApiErrorMessage(e), 'error');
    } finally {
        savingTemplateKeys.value.delete(key);
    }
};

const deleteDocumentTemplate = async (template: DocumentTemplateForm) => {
    if (!template.document_template_id) {
        documentTemplates.value = documentTemplates.value.filter((item) => item !== template);
        return;
    }
    if (!confirm(`Удалить шаблон "${template.name}"?`)) return;
    deletingTemplateId.value = template.document_template_id;
    try {
        await ManagerDocsService.deleteManagerDocumentTemplate(template.document_template_id);
        documentTemplates.value = documentTemplates.value.filter((item) => item.document_template_id !== template.document_template_id);
        setToast('Шаблон удален');
    } catch (e) {
        setToast(getApiErrorMessage(e), 'error');
    } finally {
        deletingTemplateId.value = null;
    }
};

const normalizeRoleType = (value: unknown): DocumentRoleType => {
    const raw = String(value || '').trim();
    if (raw === 'executor_customer' || raw === 'contractor_customer') return raw;
    return 'seller_buyer';
};

const normalizeDocumentType = (value: unknown): ManagedDocumentType => {
    const raw = String(value || '').trim();
    if (raw === 'act' || raw === 'invoice' || raw === 'defect_act') return raw;
    return 'contract';
};

const parseContractTemplates = (raw: string): ContractTemplateForm[] => {
    try {
        const items = JSON.parse(raw || '[]');
        if (!Array.isArray(items)) return [];
        return items
            .filter((item) => item && typeof item === 'object')
            .map((item) => ({
                id: String(item.id || '').trim(),
                name: String(item.name || '').trim(),
                document_role_type: normalizeRoleType(item.document_role_type),
                is_open_contract: item.is_open_contract === true,
            }))
            .filter((item) => item.id || item.name);
    } catch {
        return [];
    }
};

const ensureContractTemplateDraft = (setting: ManagerSettingResponse) => {
    if (!contractTemplateDrafts.value[setting.key]) {
        contractTemplateDrafts.value[setting.key] = parseContractTemplates(setting.value);
    }
    return contractTemplateDrafts.value[setting.key] ?? [];
};

const addContractTemplateRow = (setting: ManagerSettingResponse) => {
    ensureContractTemplateDraft(setting).push({
        id: '',
        name: '',
        document_role_type: 'seller_buyer',
        is_open_contract: false,
    });
};

const removeContractTemplateRow = (setting: ManagerSettingResponse, index: number) => {
    ensureContractTemplateDraft(setting).splice(index, 1);
};

const saveContractTemplates = async (setting: ManagerSettingResponse) => {
    const rows = ensureContractTemplateDraft(setting)
        .map((row) => ({
            id: row.id.trim(),
            name: row.name.trim(),
            document_role_type: normalizeRoleType(row.document_role_type),
            is_open_contract: row.is_open_contract === true,
        }))
        .filter((row) => row.id && row.name);
    setting.value = JSON.stringify(rows, null, 2);
    await saveSetting(setting);
};

const saveSetting = async (setting: ManagerSettingResponse) => {
    if (savingKeys.value.has(setting.key)) return;
    
    savingKeys.value.add(setting.key);
    error.value = '';
    
    try {
        const payload: ManagerSettingUpdatePayload = {
            value: setting.value,
            description: setting.description || undefined
        };
        const updated = await api.updateManagerSetting(setting.key, payload);
        
        // Update local state with the exact response
        const index = settings.value.findIndex(s => s.key === updated.key);
        if (index !== -1) {
            settings.value[index] = updated;
        }
        
        setToast('Настройка сохранена');
    } catch (e) {
        error.value = getApiErrorMessage(e);
        // Reload to revert to actual state in case of error
        await loadSettings(); 
    } finally {
        savingKeys.value.delete(setting.key);
    }
};

const createSetting = async () => {
    if (!newKey.value.trim() || !newValue.value.trim()) {
        setToast('Заполните ключ и значение', 'error');
        return;
    }
    creating.value = true;
    error.value = '';
    try {
        await ManagerSettingsService.createManagerSetting({
            key: newKey.value.trim(),
            value: newValue.value.trim(),
            description: newDescription.value.trim() || undefined,
        });
        setToast('Настройка создана');
        newKey.value = '';
        newValue.value = '';
        newDescription.value = '';
        showCreateForm.value = false;
        await loadSettings();
    } catch (e) {
        setToast(getApiErrorMessage(e), 'error');
    } finally {
        creating.value = false;
    }
};

const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('ru-RU', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
    });
};

onMounted(() => {
    void loadSettings();
    void loadDocumentTemplates().then(() => loadCustomers());
    void loadRepairComplaintPresets();
    void loadTemplateFiles();
    void loadGoogleAuthStatus();
});
</script>

<template>
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full">
        <!-- Toast Notification -->
        <Transition name="toast">
            <div v-if="toast" class="fixed top-20 right-8 z-50 px-4 py-3 rounded-lg shadow-xl flex items-center gap-3"
                 :class="toastType === 'success' ? 'bg-teal-600 border border-teal-500 text-white shadow-teal-900/30' : 'bg-red-600 border border-red-500 text-white shadow-red-900/30'">
                <span class="material-icons-round text-xl">{{ toastType === 'success' ? 'check_circle' : 'error' }}</span>
                <span class="text-sm font-medium">{{ toast }}</span>
            </div>
        </Transition>

        <div class="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div class="pl-16 sm:pl-0">
                <h1 class="text-2xl font-bold text-gray-900 dark:text-white tracking-tight flex items-center gap-3">
                    <span class="material-icons-round text-teal-600 dark:text-teal-400">settings</span>
                    Настройки
                </h1>
                <p class="mt-1 text-sm text-gray-500 dark:text-slate-400">
                    Управление глобальными параметрами и конфигурацией сайта
                </p>
            </div>
            
            <div class="grid w-full grid-cols-3 gap-2 sm:flex sm:w-auto sm:items-center">
                <button
                    @click="goToBackups"
                    class="flex min-w-0 items-center justify-center gap-2 bg-red-600 hover:bg-red-500 active:bg-red-700 text-white font-medium py-2.5 px-3 sm:px-4 rounded-lg shadow-sm transition-all text-sm"
                >
                    <span class="material-icons-round text-[18px]">warning</span>
                    <span class="min-w-0 leading-tight">DR / Бэкапы</span>
                </button>
                <button 
                    @click="showCreateForm = !showCreateForm"
                    class="flex min-w-0 items-center justify-center gap-2 bg-teal-600 hover:bg-teal-500 active:bg-teal-700 text-white font-medium py-2.5 px-3 sm:px-4 rounded-lg shadow-sm transition-all text-sm"
                >
                    <span class="material-icons-round text-[18px]">{{ showCreateForm ? 'close' : 'add_circle' }}</span>
                    <span class="min-w-0 leading-tight">{{ showCreateForm ? 'Отмена' : 'Добавить' }}</span>
                </button>
                <button 
                    @click="loadSettings"
                    class="flex min-w-0 items-center justify-center gap-2 bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 hover:bg-gray-50 dark:hover:bg-slate-700 active:bg-gray-100 dark:active:bg-slate-600 text-gray-700 dark:text-slate-300 font-medium py-2.5 px-3 sm:px-4 rounded-lg shadow-sm transition-all text-sm"
                    :disabled="loading"
                >
                    <span class="material-icons-round text-[18px]" :class="{'animate-spin': loading}">refresh</span>
                    <span class="min-w-0 leading-tight">Обновить</span>
                </button>
            </div>
        </div>

        <div class="mb-6 flex flex-wrap gap-2 rounded-xl border border-gray-200 bg-white p-2 shadow-sm dark:border-slate-700/60 dark:bg-[#1e293b]">
            <button
                type="button"
                class="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors"
                :class="activeSettingsTab === 'general' ? 'bg-teal-600 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-800'"
                @click="activeSettingsTab = 'general'"
            >
                <span class="material-icons-round text-[18px]">tune</span>
                Основные
            </button>
            <button
                type="button"
                class="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors"
                :class="activeSettingsTab === 'documentTemplates' ? 'bg-teal-600 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-800'"
                @click="activeSettingsTab = 'documentTemplates'"
            >
                <span class="material-icons-round text-[18px]">description</span>
                Шаблоны документов
            </button>
            <button
                type="button"
                class="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors"
                :class="activeSettingsTab === 'repairComplaints' ? 'bg-teal-600 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-800'"
                @click="activeSettingsTab = 'repairComplaints'"
            >
                <span class="material-icons-round text-[18px]">build_circle</span>
                Жалобы ремонта
            </button>
        </div>

        <div v-if="activeSettingsTab === 'general'" class="mb-6 bg-white dark:bg-[#1e293b] rounded-xl shadow-sm border border-gray-200 dark:border-slate-700/60 p-6">
            <div class="flex items-start justify-between gap-4 flex-wrap">
                <div>
                    <h3 class="text-base font-semibold text-gray-900 dark:text-slate-200 mb-1 flex items-center gap-2">
                        <span class="material-icons-round text-teal-500 text-[20px]">account_tree</span>
                        Google Integration
                    </h3>
                    <p class="text-xs text-gray-500 dark:text-slate-400">
                        Авторизация Google API для документов и Google Sheets.
                    </p>
                </div>
                <button
                    @click="loadGoogleAuthStatus"
                    class="flex items-center gap-2 bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 hover:bg-gray-50 dark:hover:bg-slate-700 active:bg-gray-100 dark:active:bg-slate-600 text-gray-700 dark:text-slate-300 font-medium py-2 px-3 rounded-lg shadow-sm transition-all text-xs"
                    :disabled="googleAuthLoading || googleAuthBusy"
                >
                    <span class="material-icons-round text-[16px]" :class="{ 'animate-spin': googleAuthLoading }">refresh</span>
                    Проверить
                </button>
            </div>

            <div class="mt-4 p-3 rounded-lg border"
                :class="googleAuthStatus?.valid
                    ? 'bg-green-50 border-green-200 text-green-800 dark:bg-green-500/10 dark:border-green-500/40 dark:text-green-300'
                    : 'bg-amber-50 border-amber-200 text-amber-800 dark:bg-amber-500/10 dark:border-amber-500/40 dark:text-amber-300'">
                <div class="text-sm font-medium">
                    <span v-if="googleAuthLoading">Проверяем статус...</span>
                    <span v-else-if="googleAuthStatus?.valid">Подключено</span>
                    <span v-else>Не подключено / токен истёк</span>
                </div>
                <div v-if="googleAuthStatus?.expiry" class="text-xs mt-1 opacity-80">
                    Действует до: {{ googleAuthStatus.expiry }}
                </div>
            </div>

            <div class="mt-4 flex flex-wrap items-center gap-2">
                <button
                    @click="openGoogleAuth"
                    class="flex items-center justify-center gap-2 bg-teal-600 hover:bg-teal-500 active:bg-teal-700 text-white font-medium py-2 px-4 rounded-lg shadow-sm transition-all text-sm disabled:opacity-60"
                    :disabled="googleAuthBusy"
                >
                    <span class="material-icons-round text-[18px]">open_in_new</span>
                    Подключить Google
                </button>
            </div>
        </div>

        <div v-if="activeSettingsTab === 'documentTemplates'" class="mb-6 bg-white dark:bg-[#1e293b] rounded-xl shadow-sm border border-gray-200 dark:border-slate-700/60 p-6">
            <div class="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <h3 class="text-base font-semibold text-gray-900 dark:text-slate-200 mb-1 flex items-center gap-2">
                        <span class="material-icons-round text-teal-500 text-[20px]">description</span>
                        Шаблоны документов
                    </h3>
                    <p class="text-xs text-gray-500 dark:text-slate-400">
                        Общие формы для всех клиентов и редкие персональные формы по УНП/названию.
                    </p>
                </div>
                <div class="flex flex-wrap gap-2">
                    <button
                        v-for="option in DOCUMENT_TYPE_OPTIONS"
                        :key="option.value"
                        type="button"
                        class="flex items-center gap-1 rounded-lg px-3 py-2 text-xs font-medium text-white shadow-sm"
                        :class="option.value === 'act' ? 'bg-slate-700 hover:bg-slate-600' : 'bg-teal-600 hover:bg-teal-500'"
                        @click="addDocumentTemplate(option.value)"
                    >
                        <span class="material-icons-round text-[16px]">add</span>
                        {{ option.addLabel }}
                    </button>
                </div>
            </div>

            <div class="mt-5 rounded-xl border border-teal-100 bg-teal-50/60 p-4 dark:border-teal-500/30 dark:bg-teal-500/10">
                <label class="mb-2 block text-xs font-medium text-teal-800 dark:text-teal-200">Папка Google Drive с шаблонами</label>
                <div class="flex flex-col gap-2 sm:flex-row">
                    <input
                        v-model="templateFolderId"
                        type="text"
                        class="min-w-0 flex-1 rounded-lg border border-teal-200 bg-white px-3 py-2 font-mono text-sm text-gray-900 shadow-sm dark:border-teal-500/40 dark:bg-slate-900 dark:text-slate-200"
                        placeholder="Google Drive folder ID"
                    />
                    <button
                        type="button"
                        class="flex items-center justify-center gap-2 rounded-lg bg-white px-3 py-2 text-sm font-medium text-teal-700 shadow-sm ring-1 ring-teal-200 hover:bg-teal-50 disabled:opacity-60 dark:bg-slate-900 dark:text-teal-200 dark:ring-teal-500/40 dark:hover:bg-slate-800"
                        :disabled="loadingTemplateFiles"
                        @click="loadTemplateFiles"
                    >
                        <span class="material-icons-round text-[18px]" :class="{ 'animate-spin': loadingTemplateFiles }">refresh</span>
                        Обновить список
                    </button>
                </div>
            </div>

            <div class="mt-5 space-y-3">
                <div
                    v-for="template in documentTemplates"
                    :key="template.document_template_id || `${template.doc_type}-${template.sort_order}-${template.google_template_id}`"
                    class="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-slate-700 dark:bg-slate-900/50"
                >
                    <div class="grid grid-cols-1 gap-3 lg:grid-cols-[170px_1fr_1.2fr_180px_120px]">
                        <div>
                            <label class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Тип</label>
                            <select
                                v-model="template.doc_type"
                                class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                            >
                                <option v-for="option in DOCUMENT_TYPE_OPTIONS" :key="option.value" :value="option.value">
                                    {{ option.label }}
                                </option>
                            </select>
                        </div>
                        <div>
                            <label class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Название</label>
                            <input
                                v-model="template.name"
                                type="text"
                                class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                                placeholder="Название для менеджера"
                            />
                        </div>
                        <div>
                            <label class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Файл шаблона</label>
                            <select
                                :value="template.google_template_id"
                                class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                                @change="selectTemplateFile(template, ($event.target as HTMLSelectElement).value)"
                            >
                                <option value="">Выберите файл из папки templates</option>
                                <option v-for="file in filteredTemplateFiles" :key="file.id" :value="file.id">
                                    {{ file.name }}
                                </option>
                            </select>
                            <input
                                v-model="template.google_template_id"
                                type="text"
                                class="mt-2 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 font-mono text-xs text-gray-600 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400"
                                placeholder="или Google Template ID вручную"
                            />
                        </div>
                        <div>
                            <label class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Роли</label>
                            <select
                                v-model="template.document_role_type"
                                class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                            >
                                <option v-for="option in DOCUMENT_ROLE_OPTIONS" :key="option.value" :value="option.value">
                                    {{ option.label }}
                                </option>
                            </select>
                        </div>
                        <div>
                            <label class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Позиция</label>
                            <input
                                v-model.number="template.sort_order"
                                type="number"
                                class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                                placeholder="0"
                            />
                        </div>
                    </div>

                    <div class="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-3">
                        <textarea
                            v-model="template.description"
                            rows="3"
                            class="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                            placeholder="Комментарий для менеджера"
                        />
                        <div>
                            <label class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Доступность</label>
                            <div class="rounded-lg border border-gray-300 bg-white p-3 shadow-sm dark:border-slate-600 dark:bg-slate-900">
                                <label class="flex items-center gap-2 text-sm text-gray-700 dark:text-slate-300">
                                    <input
                                        type="checkbox"
                                        class="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500"
                                        :checked="!template.client_restricted"
                                        @change="template.client_restricted = !($event.target as HTMLInputElement).checked; if (!template.client_restricted) template.customer_ids = []"
                                    />
                                    Для всех клиентов
                                </label>
                                <div v-if="template.client_restricted" class="mt-3 space-y-2">
                                    <div class="flex gap-2">
                                        <input
                                            v-model="customerSearch"
                                            type="search"
                                            class="min-w-0 flex-1 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-900 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
                                            placeholder="Найти по УНП или названию"
                                            @keydown.enter.prevent="loadCustomers(customerSearch)"
                                        />
                                        <button
                                            type="button"
                                            class="rounded-lg bg-slate-700 px-3 py-2 text-xs font-medium text-white hover:bg-slate-600 disabled:opacity-60"
                                            :disabled="loadingCustomerSearch"
                                            @click="loadCustomers(customerSearch)"
                                        >
                                            Найти
                                        </button>
                                    </div>
                                    <select
                                        class="w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-900 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
                                        @change="addCustomerToTemplate(template, ($event.target as HTMLSelectElement).value); ($event.target as HTMLSelectElement).value = ''"
                                    >
                                        <option value="">Добавить найденного клиента</option>
                                        <option
                                            v-for="customer in customers"
                                            :key="customer.id"
                                            :value="customer.id"
                                            :disabled="template.customer_ids.includes(customer.id)"
                                        >
                                            {{ customerLabel(customer) }}
                                        </option>
                                    </select>
                                    <div class="flex flex-wrap gap-2">
                                        <button
                                            v-for="customer in selectedCustomersForTemplate(template)"
                                            :key="customer.id"
                                            type="button"
                                            class="inline-flex items-center gap-1 rounded-full bg-teal-50 px-3 py-1 text-xs font-medium text-teal-800 ring-1 ring-teal-200 dark:bg-teal-500/10 dark:text-teal-200 dark:ring-teal-500/30"
                                            @click="removeCustomerFromTemplate(template, customer.id)"
                                        >
                                            {{ customerLabel(customer) }}
                                            <span class="material-icons-round text-[14px]">close</span>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div v-if="template.doc_type === 'contract' || template.doc_type === 'invoice'">
                            <label class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Связанные акты</label>
                            <select
                                v-model="template.linked_act_template_ids"
                                multiple
                                class="h-24 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                            >
                                <option v-for="act in actDocumentTemplates" :key="act.document_template_id || 0" :value="act.document_template_id || 0">
                                    {{ act.name }}
                                </option>
                            </select>
                        </div>
                        <div v-else-if="template.doc_type === 'act'">
                            <label class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Для договоров / счетов</label>
                            <select
                                v-model="template.linked_contract_template_ids"
                                multiple
                                class="h-24 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                            >
                                <option v-for="contract in contractDocumentTemplates" :key="contract.document_template_id || 0" :value="contract.document_template_id || 0">
                                    {{ contract.name }}
                                </option>
                            </select>
                        </div>
                        <div v-else class="rounded-lg border border-gray-200 bg-white p-3 text-sm text-gray-500 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
                            Дефектный акт выбирается как отдельный шаблон без привязки к договору или счету.
                        </div>
                    </div>

                    <div class="mt-3 flex flex-wrap items-center justify-between gap-3">
                        <div class="flex flex-wrap gap-3 text-sm text-gray-700 dark:text-slate-300">
                            <label class="flex items-center gap-2">
                                <input v-model="template.is_active" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500" />
                                Активен
                            </label>
                            <label class="flex items-center gap-2">
                                <input v-model="template.is_default" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500" />
                                По умолчанию
                            </label>
                            <label v-if="template.doc_type === 'contract'" class="flex items-center gap-2">
                                <input v-model="template.is_open_contract" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500" />
                                Открытый договор
                            </label>
                        </div>
                        <div class="flex gap-2">
                            <button
                                type="button"
                                class="rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-medium text-red-600 shadow-sm hover:bg-red-50 dark:border-red-500/40 dark:bg-slate-900 dark:text-red-300 dark:hover:bg-red-500/10"
                                :disabled="deletingTemplateId === template.document_template_id"
                                @click="deleteDocumentTemplate(template)"
                            >
                                Удалить
                            </button>
                            <button
                                type="button"
                                class="rounded-lg bg-teal-600 px-4 py-2 text-xs font-medium text-white shadow-sm hover:bg-teal-500 disabled:opacity-60"
                                :disabled="savingTemplateKeys.has(String(template.document_template_id || `new:${template.doc_type}:${template.sort_order}`))"
                                @click="saveDocumentTemplate(template)"
                            >
                                Сохранить
                            </button>
                        </div>
                    </div>
                </div>
                <p v-if="!documentTemplates.length" class="rounded-lg border border-dashed border-gray-300 p-4 text-sm text-gray-500 dark:border-slate-700 dark:text-slate-400">
                    Управляемые шаблоны пока не добавлены. Старые шаблоны из JSON продолжают работать как fallback до миграции.
                </p>
            </div>
        </div>

        <div v-if="activeSettingsTab === 'repairComplaints'" class="mb-6 bg-white dark:bg-[#1e293b] rounded-xl shadow-sm border border-gray-200 dark:border-slate-700/60 p-6">
            <div class="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <h3 class="text-base font-semibold text-gray-900 dark:text-slate-200 mb-1 flex items-center gap-2">
                        <span class="material-icons-round text-teal-500 text-[20px]">build_circle</span>
                        Жалобы и диагнозы для ремонта
                    </h3>
                    <p class="text-xs text-gray-500 dark:text-slate-400">
                        Менеджер выбирает жалобу в заказе, а карточка подставляет формулировку для акта и вероятный диагноз.
                    </p>
                </div>
                <button
                    type="button"
                    class="flex items-center gap-1 rounded-lg bg-teal-600 px-3 py-2 text-xs font-medium text-white shadow-sm hover:bg-teal-500"
                    @click="addRepairComplaintPreset"
                >
                    <span class="material-icons-round text-[16px]">add</span>
                    Добавить жалобу
                </button>
            </div>

            <div class="mt-5 grid gap-3 md:grid-cols-[1fr_240px_auto]">
                <input
                    v-model="repairComplaintSearch"
                    type="search"
                    class="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                    placeholder="Поиск по жалобе, формулировке или диагнозу"
                    @keydown.enter.prevent="loadRepairComplaintPresets"
                />
                <select
                    v-model="repairComplaintGroupFilter"
                    class="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                    @change="loadRepairComplaintPresets"
                >
                    <option value="">Все группы</option>
                    <option v-for="group in REPAIR_COMPLAINT_GROUP_OPTIONS" :key="group.value" :value="group.value">
                        {{ group.label }}
                    </option>
                </select>
                <button
                    type="button"
                    class="flex items-center justify-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-60 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
                    :disabled="loadingRepairComplaints"
                    @click="loadRepairComplaintPresets"
                >
                    <span class="material-icons-round text-[18px]" :class="{ 'animate-spin': loadingRepairComplaints }">refresh</span>
                    Обновить
                </button>
            </div>

            <div class="mt-5 space-y-3">
                <div
                    v-for="preset in repairComplaintPresets"
                    :key="preset.id || `new:${preset.complaint_group}:${preset.sort_order}`"
                    class="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-slate-700 dark:bg-slate-900/50"
                >
                    <div class="grid grid-cols-1 gap-3 lg:grid-cols-[180px_1fr_110px]">
                        <div>
                            <label class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Группа</label>
                            <select
                                v-model="preset.complaint_group"
                                class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                            >
                                <option v-for="group in REPAIR_COMPLAINT_GROUP_OPTIONS" :key="group.value" :value="group.value">
                                    {{ group.label }}
                                </option>
                            </select>
                        </div>
                        <div>
                            <label class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Как говорит клиент *</label>
                            <input
                                v-model="preset.customer_phrase"
                                type="text"
                                class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                                placeholder="Не холодит, капает вода, шумит..."
                            />
                        </div>
                        <div>
                            <label class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Порядок</label>
                            <input
                                v-model.number="preset.sort_order"
                                type="number"
                                class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                            />
                        </div>
                    </div>

                    <div class="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
                        <label class="block">
                            <span class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Формулировка в акт</span>
                            <textarea
                                v-model="preset.document_wording"
                                rows="3"
                                class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                                placeholder="Официальная формулировка для дефектного акта"
                            />
                        </label>
                        <label class="block">
                            <span class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Вероятный диагноз</span>
                            <textarea
                                v-model="preset.likely_diagnosis"
                                rows="3"
                                class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                                placeholder="Внутренняя подсказка для менеджера/мастера"
                            />
                        </label>
                    </div>

                    <div class="mt-3 flex flex-wrap items-center justify-between gap-3">
                        <div class="flex flex-wrap gap-3 text-sm text-gray-700 dark:text-slate-300">
                            <label class="flex items-center gap-2">
                                <input v-model="preset.is_active" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500" />
                                Активна
                            </label>
                            <label class="flex items-center gap-2">
                                <input v-model="preset.is_favorite" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500" />
                                Избранная
                            </label>
                        </div>
                        <div class="flex gap-2">
                            <button
                                type="button"
                                class="rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-medium text-red-600 shadow-sm hover:bg-red-50 disabled:opacity-60 dark:border-red-500/40 dark:bg-slate-900 dark:text-red-300 dark:hover:bg-red-500/10"
                                :disabled="deletingRepairComplaintId === preset.id"
                                @click="deleteRepairComplaintPreset(preset)"
                            >
                                Удалить
                            </button>
                            <button
                                type="button"
                                class="rounded-lg bg-teal-600 px-4 py-2 text-xs font-medium text-white shadow-sm hover:bg-teal-500 disabled:opacity-60"
                                :disabled="savingRepairComplaintKeys.has(String(preset.id || `new:${preset.complaint_group}:${preset.sort_order}`))"
                                @click="saveRepairComplaintPreset(preset)"
                            >
                                Сохранить
                            </button>
                        </div>
                    </div>
                </div>
                <p v-if="!repairComplaintPresets.length" class="rounded-lg border border-dashed border-gray-300 p-4 text-sm text-gray-500 dark:border-slate-700 dark:text-slate-400">
                    Жалобы не найдены. Добавьте первую или сбросьте фильтр.
                </p>
            </div>
        </div>

        <!-- Create Setting Form -->
        <Transition name="toast">
            <div v-if="activeSettingsTab === 'general' && showCreateForm" class="mb-6 bg-white dark:bg-[#1e293b] rounded-xl shadow-sm border-2 border-teal-500/50 p-6">
                <h3 class="text-base font-semibold text-gray-900 dark:text-slate-200 mb-4 flex items-center gap-2">
                    <span class="material-icons-round text-teal-500 text-[20px]">add_circle</span>
                    Новый параметр
                </h3>
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                        <label class="block text-xs font-medium text-gray-500 dark:text-slate-400 mb-1">Ключ *</label>
                        <input
                            v-model="newKey"
                            type="text"
                            class="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-teal-500 transition-colors shadow-sm font-mono text-sm"
                            placeholder="contract_templates"
                            :disabled="creating"
                        />
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-500 dark:text-slate-400 mb-1">Значение *</label>
                        <input
                            v-model="newValue"
                            type="text"
                            class="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-teal-500 transition-colors shadow-sm text-sm"
                            placeholder='[{"id": "...", "name": "..."}]'
                            :disabled="creating"
                        />
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-500 dark:text-slate-400 mb-1">Описание</label>
                        <div class="flex gap-2">
                            <input
                                v-model="newDescription"
                                type="text"
                                class="flex-1 bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-teal-500 transition-colors shadow-sm text-sm"
                                placeholder="Описание параметра"
                                :disabled="creating"
                            />
                            <button
                                @click="createSetting"
                                class="flex items-center gap-1 px-4 py-2 text-sm font-medium text-white bg-teal-600 hover:bg-teal-500 active:bg-teal-700 transition-colors rounded-lg disabled:opacity-50 shadow-sm whitespace-nowrap"
                                :disabled="creating || !newKey.trim() || !newValue.trim()"
                            >
                                <span v-if="creating" class="material-icons-round text-sm animate-spin">refresh</span>
                                <span v-else class="material-icons-round text-sm">save</span>
                                Создать
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </Transition>

        <div v-if="error" class="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/50 text-red-600 dark:text-red-400 p-4 rounded-xl mb-6">
            {{ error }}
        </div>

        <div v-if="activeSettingsTab === 'general' && loading && !settings.length" class="flex justify-center py-20">
            <div class="w-8 h-8 rounded-full border-4 border-gray-200 dark:border-slate-700 border-t-teal-500 animate-spin"></div>
        </div>

        <div v-else-if="activeSettingsTab === 'general'" class="space-y-4">
            <div v-for="setting in settings" :key="setting.key" class="bg-white dark:bg-[#1e293b] rounded-xl shadow-sm border border-gray-200 dark:border-slate-700/60 p-6 flex flex-col md:flex-row gap-6 items-start md:items-center transition-colors">
                <div class="flex-1 space-y-2 w-full">
                    <div>
                        <h3 class="text-sm font-semibold text-gray-900 dark:text-slate-200 font-mono bg-gray-100 dark:bg-slate-800 px-2 py-1 rounded inline-block mb-1 border border-gray-200 dark:border-slate-700">
                            {{ setting.key }}
                        </h3>
                        <p class="text-xs text-gray-500 dark:text-slate-400">
                            Изменено: {{ formatDate(setting.updated_at) }}
                        </p>
                    </div>
                </div>
                
                <div v-if="setting.key === 'contract_templates'" class="flex-[2] w-full space-y-3">
                    <div class="flex items-center justify-between gap-3">
                        <label class="block text-xs font-medium text-gray-500 dark:text-slate-400">Шаблоны договоров</label>
                        <button
                            type="button"
                            class="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-teal-700 bg-teal-50 hover:bg-teal-100 dark:bg-teal-500/10 dark:text-teal-300 dark:hover:bg-teal-500/20 rounded-lg"
                            @click="addContractTemplateRow(setting)"
                        >
                            <span class="material-icons-round text-[16px]">add</span>
                            Добавить шаблон
                        </button>
                    </div>
                    <div class="space-y-2">
                        <div
                            v-for="(template, index) in ensureContractTemplateDraft(setting)"
                            :key="`${setting.key}-${index}`"
                            class="grid grid-cols-1 gap-2 md:grid-cols-[1fr_1.4fr_220px_150px_auto] md:items-center"
                        >
                            <input
                                v-model="template.name"
                                type="text"
                                class="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-teal-500 transition-colors shadow-sm text-sm"
                                placeholder="Название для менеджера"
                                :disabled="savingKeys.has(setting.key)"
                            />
                            <input
                                v-model="template.id"
                                type="text"
                                class="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-teal-500 transition-colors shadow-sm text-sm font-mono"
                                placeholder="Google Template ID"
                                :disabled="savingKeys.has(setting.key)"
                            />
                            <select
                                v-model="template.document_role_type"
                                class="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-teal-500 transition-colors shadow-sm text-sm"
                                :disabled="savingKeys.has(setting.key)"
                            >
                                <option v-for="option in DOCUMENT_ROLE_OPTIONS" :key="option.value" :value="option.value">
                                    {{ option.label }}
                                </option>
                            </select>
                            <label class="flex h-10 items-center gap-2 rounded-lg border border-gray-300 bg-gray-50 px-3 text-sm text-gray-700 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200">
                                <input
                                    v-model="template.is_open_contract"
                                    type="checkbox"
                                    class="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500"
                                    :disabled="savingKeys.has(setting.key)"
                                />
                                <span>Открытый</span>
                            </label>
                            <button
                                type="button"
                                class="flex h-10 w-10 items-center justify-center rounded-lg text-red-500 transition-colors hover:bg-red-500/10"
                                title="Удалить шаблон"
                                :disabled="savingKeys.has(setting.key)"
                                @click="removeContractTemplateRow(setting, index)"
                            >
                                <span class="material-icons-round text-[20px]">delete</span>
                            </button>
                        </div>
                    </div>
                    <p v-if="!ensureContractTemplateDraft(setting).length" class="text-sm text-gray-500 dark:text-slate-400">
                        Шаблоны еще не добавлены.
                    </p>
                </div>
                <div v-else class="flex-1 w-full space-y-3">
                    <div>
                        <label class="block text-xs font-medium text-gray-500 dark:text-slate-400 mb-1">Значение</label>
                        <input
                            v-model="setting.value"
                            type="text"
                            class="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-teal-500 transition-colors shadow-sm"
                            :disabled="savingKeys.has(setting.key)"
                        />
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-500 dark:text-slate-400 mb-1">Описание</label>
                        <input
                            v-model="setting.description"
                            type="text"
                            class="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-teal-500 transition-colors shadow-sm text-sm"
                            :disabled="savingKeys.has(setting.key)"
                            placeholder="Добавьте описание..."
                        />
                    </div>
                </div>
                
                <div class="md:w-32 flex-shrink-0 flex justify-end w-full md:block">
                    <button
                        @click="setting.key === 'contract_templates' ? saveContractTemplates(setting) : saveSetting(setting)"
                        class="w-full flex justify-center items-center gap-2 px-4 py-2.5 text-sm font-medium text-white bg-teal-600 hover:bg-teal-500 active:bg-teal-700 transition-colors rounded-lg disabled:opacity-50 shadow-sm"
                        :disabled="savingKeys.has(setting.key)"
                    >
                        <span v-if="savingKeys.has(setting.key)" class="material-icons-round text-sm animate-spin">refresh</span>
                        <span v-else class="material-icons-round text-sm">save</span>
                        Сохранить
                    </button>
                </div>
            </div>
            
            <div v-if="settings.length === 0 && !loading" class="bg-white dark:bg-[#1e293b] rounded-xl border border-gray-200 dark:border-slate-700/60 p-12 text-center">
                <p class="text-gray-500 dark:text-slate-400">Настройки не найдены.</p>
            </div>
        </div>
    </div>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.toast-enter-from,
.toast-leave-to {
    opacity: 0;
    transform: translateY(-1rem) translateX(2rem);
}
</style>
