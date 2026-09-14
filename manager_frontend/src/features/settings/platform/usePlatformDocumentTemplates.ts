import { computed, ref } from 'vue';
import { api } from '../../../api';
import type { DocumentTemplateItem, DocumentTemplatePayload, ManagerCatalogCustomerItemResponse } from '../../../client';
import { ManagerDocsService } from '../../../client';
import { getApiErrorMessage } from '../../../utils/api-errors';
import { confirmDialog } from '../../../services/ui-feedback';
import { normalizeDocumentType, normalizeRoleType } from './platform-settings-types';
import type { DocumentTemplateFileOption, DocumentTemplateForm, ManagedDocumentType } from './platform-settings-types';

export const usePlatformDocumentTemplates = (setToast: (message: string, type?: 'success' | 'error') => void) => {
const documentTemplates = ref<DocumentTemplateForm[]>([]);
const customers = ref<ManagerCatalogCustomerItemResponse[]>([]);
const templateFiles = ref<DocumentTemplateFileOption[]>([]);
const customerSearch = ref('');
const templateFolderId = ref('1SClclCJS2FUVtfF-vbVqN8zI77Sl_E9t');
const loadingTemplateFiles = ref(false);
const loadingCustomerSearch = ref(false);
const savingTemplateKeys = ref<Set<string>>(new Set());
const deletingTemplateId = ref<number | null>(null);
const emptyDocumentTemplate = (docType: ManagedDocumentType = 'contract'): DocumentTemplateForm => ({
    document_template_id: null,
    name: '',
    doc_type: docType,
    google_template_id: '',
    document_role_type: 'seller_buyer',
    description: '',
    base_document_type_label: '',
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
    base_document_type_label: item.base_document_type_label || '',
    is_default: item.is_default === true,
    is_active: item.is_active !== false,
    is_open_contract: item.is_open_contract === true,
    client_restricted: item.client_restricted === true,
    sort_order: Number(item.sort_order ?? 0),
    customer_ids: [...(item.customer_ids ?? [])],
    linked_contract_template_ids: [...(item.linked_contract_template_ids ?? [])],
    linked_act_template_ids: [...(item.linked_act_template_ids ?? [])],
});

const documentTemplatePayload = (template: DocumentTemplateForm): DocumentTemplatePayload => ({
    name: template.name.trim(),
    doc_type: template.doc_type,
    google_template_id: template.google_template_id.trim(),
    document_role_type: normalizeRoleType(template.document_role_type),
    description: template.description.trim() || undefined,
    base_document_type_label: template.base_document_type_label.trim() || undefined,
    is_default: template.is_default,
    is_active: template.is_active,
    is_open_contract: template.doc_type === 'contract' ? template.is_open_contract : false,
    client_restricted: template.client_restricted,
    sort_order: Number(template.sort_order || 0),
    customer_ids: template.customer_ids,
    linked_contract_template_ids: template.doc_type === 'act' ? template.linked_contract_template_ids : [],
    linked_act_template_ids: template.doc_type === 'contract' || template.doc_type === 'invoice' || template.doc_type === 'warranty_certificate' ? template.linked_act_template_ids : [],
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
const loadDocumentTemplates = async () => {
    try {
        const res = await ManagerDocsService.listManagerDocumentTemplates();
        documentTemplates.value = res.items.map(mapTemplateItemToForm);
    } catch (e) {
        setToast(getApiErrorMessage(e), 'error');
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
    if (!await confirmDialog({ title: 'Удалить шаблон?', description: template.name, confirmText: 'Удалить', variant: 'danger' })) return;
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

    return { documentTemplates, customers, templateFiles, customerSearch, templateFolderId, loadingTemplateFiles, loadingCustomerSearch, savingTemplateKeys, deletingTemplateId, contractDocumentTemplates, actDocumentTemplates, filteredTemplateFiles, loadDocumentTemplates, loadCustomers, loadTemplateFiles, addDocumentTemplate, selectTemplateFile, selectedCustomersForTemplate, addCustomerToTemplate, removeCustomerFromTemplate, customerLabel, saveDocumentTemplate, deleteDocumentTemplate };
};
