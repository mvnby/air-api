import { computed, ref, watch } from 'vue';
import {
  ManagerDocumentSystemService,
  type DocumentLegalEntityItem,
  type DocumentPdfRuntimeStatus,
  type ManagedDocumentItem,
  type NativeDocumentTemplateItem,
  type NativeTemplateVersionItem,
} from '../../../client';
import { getApiErrorMessage } from '../../../utils/api-errors';
import { confirmDialog } from '../../../services/ui-feedback';
import {
  createDefaultConsumerDocumentTerms,
  isConsumerDocumentType,
  type ConsumerDocumentTerms,
} from '../model/consumer-document-terms';
import {
  createDefaultBusinessDocumentTerms,
  businessTermsValidationError,
  isBusinessTermsDocumentType,
  serializeBusinessTerms,
  type BusinessDocumentTerms,
} from '../model/business-document-terms';
import {
  actTermsValidationError,
  createDefaultActTerms,
  type ActTerms,
} from '../model/act-terms';

type ManagedWorkspaceInput = {
  orderId: () => number;
  proposalId: () => number | null;
  notify: (message: string, type?: 'success' | 'error') => void;
  refresh: () => void;
};

export const useManagedDocumentWorkspace = (input: ManagedWorkspaceInput) => {
  const documents = ref<ManagedDocumentItem[]>([]);
  const legalEntities = ref<DocumentLegalEntityItem[]>([]);
  const templates = ref<NativeDocumentTemplateItem[]>([]);
  const templateVersions = ref<NativeTemplateVersionItem[]>([]);
  const pdfRuntime = ref<DocumentPdfRuntimeStatus | null>(null);
  const selectedLegalEntityId = ref<number | null>(null);
  const selectedTemplateId = ref<number | null>(null);
  const documentType = ref('contract');
  const businessRole = ref<'payment_request' | 'offer'>('payment_request');
  const issueDate = ref(new Date().toISOString().slice(0, 10));
  const issueCity = ref('');
  const replacesDocumentId = ref<number | null>(null);
  const baseDocumentId = ref<number | null>(null);
  const baseCustomerContractId = ref<number | null>(null);
  const consumerTerms = ref<ConsumerDocumentTerms>(createDefaultConsumerDocumentTerms());
  const businessTerms = ref<BusinessDocumentTerms>(createDefaultBusinessDocumentTerms());
  const actTerms = ref<ActTerms>(createDefaultActTerms());
  const busy = ref(false);
  const loading = ref(false);
  const templatesLoading = ref(false);
  const templateVersionsLoading = ref(false);
  const voidTarget = ref<ManagedDocumentItem | null>(null);
  const voidReason = ref('');
  let requestId = 0;
  let templateRequestId = 0;
  let versionRequestId = 0;
  let preferredTemplateId: number | null = null;

  const defaultGoodsWarrantyMonths = (legalEntityId = selectedLegalEntityId.value) => {
    const entity = legalEntities.value.find((item) => item.id === legalEntityId);
    const configured = Number(entity?.requisites.default_goods_warranty_months);
    return Number.isFinite(configured) && configured >= 0 && configured <= 240 ? configured : 36;
  };
  const selectedGoodsWarrantyDefault = computed(() => defaultGoodsWarrantyMonths());

  const resetConsumerTerms = () => {
    consumerTerms.value = createDefaultConsumerDocumentTerms(defaultGoodsWarrantyMonths());
  };
  const resetBusinessTerms = () => {
    businessTerms.value = createDefaultBusinessDocumentTerms();
  };
  const resetActTerms = () => {
    actTerms.value = createDefaultActTerms();
  };

  const selectedTemplateHasActiveVersion = computed(() => (
    templateVersions.value.some((item) => item.status === 'active')
  ));
  const issueBlockedReason = computed(() => {
    if (!pdfRuntime.value) return 'Проверяем сервис PDF…';
    if (!pdfRuntime.value.available) return pdfRuntime.value.detail || 'Сервис PDF не настроен';
    return '';
  });
  const draftBlockedReason = computed(() => {
    if (templatesLoading.value || templateVersionsLoading.value) return 'Загружаем подходящий шаблон…';
    if (!selectedLegalEntityId.value) return 'Нет юридического лица';
    const businessTermsError = isBusinessTermsDocumentType(documentType.value)
      ? businessTermsValidationError(documentType.value, businessTerms.value)
      : '';
    if (businessTermsError) {
      return businessTermsError;
    }
    if (documentType.value === 'act') {
      const actTermsError = actTermsValidationError(actTerms.value);
      if (actTermsError) return actTermsError;
    }
    if (isConsumerDocumentType(documentType.value)) {
      const requisites = legalEntities.value.find(
        (item) => item.id === selectedLegalEntityId.value,
      )?.requisites;
      if (!requisites?.offer_url || !requisites.offer_version || !requisites.offer_published_on) {
        return 'Для документа физлицу заполните ссылку, версию и дату публичной оферты';
      }
    }
    if (!selectedTemplateId.value) return 'Нет шаблона для этого типа';
    if (!selectedTemplateHasActiveVersion.value) return 'У шаблона нет активной DOCX-версии';
    if (['act', 'tn2', 'ttn1'].includes(documentType.value) && !baseDocumentId.value && !baseCustomerContractId.value) {
      return 'Нет подходящего документа-основания';
    }
    return '';
  });

  const loadDocuments = async () => {
    const orderId = input.orderId();
    const currentRequest = ++requestId;
    try {
      const response = await ManagerDocumentSystemService.listManagerManagedOrderDocuments(orderId);
      if (currentRequest === requestId && input.orderId() === orderId) {
        documents.value = response.items.filter((item) => item.provider === 'native');
      }
    } catch (error) {
      input.notify(`Не удалось загрузить CRM-документы: ${getApiErrorMessage(error)}`, 'error');
    }
  };

  const loadTemplateVersions = async () => {
    const legalEntityId = selectedLegalEntityId.value;
    const templateId = selectedTemplateId.value;
    const currentRequest = ++versionRequestId;
    templateVersions.value = [];
    if (!legalEntityId || !templateId) {
      templateVersionsLoading.value = false;
      templateVersions.value = [];
      return;
    }
    templateVersionsLoading.value = true;
    try {
      const response = await ManagerDocumentSystemService.listManagerNativeTemplateVersions(templateId, legalEntityId);
      if (
        currentRequest === versionRequestId
        && selectedTemplateId.value === templateId
        && selectedLegalEntityId.value === legalEntityId
      ) templateVersions.value = response.items;
    } catch {
      if (currentRequest === versionRequestId) templateVersions.value = [];
    } finally {
      if (currentRequest === versionRequestId) templateVersionsLoading.value = false;
    }
  };

  const loadTemplates = async () => {
    const legalEntityId = selectedLegalEntityId.value;
    const type = documentType.value;
    const currentRequest = ++templateRequestId;
    templatesLoading.value = true;
    templates.value = [];
    selectedTemplateId.value = null;
    templateVersions.value = [];
    if (!legalEntityId) {
      templatesLoading.value = false;
      templates.value = [];
      return;
    }
    try {
      const response = await ManagerDocumentSystemService.listManagerNativeDocumentTemplates(legalEntityId, type);
      if (
        currentRequest !== templateRequestId
        || selectedLegalEntityId.value !== legalEntityId
        || documentType.value !== type
      ) return;
      templates.value = response.items.filter((item) => item.is_active);
      const preferred = templates.value.find((item) => item.id === preferredTemplateId);
      selectedTemplateId.value = preferred?.id
        || templates.value.find((item) => item.is_default)?.id
        || templates.value[0]?.id
        || null;
      preferredTemplateId = null;
    } catch (error) {
      if (currentRequest === templateRequestId) {
        templates.value = [];
        selectedTemplateId.value = null;
        input.notify(`Не удалось загрузить шаблоны: ${getApiErrorMessage(error)}`, 'error');
      }
    } finally {
      if (currentRequest === templateRequestId) templatesLoading.value = false;
    }
  };

  const loadWorkspace = async () => {
    loading.value = true;
    replacesDocumentId.value = null;
    baseDocumentId.value = null;
    baseCustomerContractId.value = null;
    resetConsumerTerms();
    resetBusinessTerms();
    resetActTerms();
    try {
      const [entitiesResponse, runtimeResponse] = await Promise.all([
        ManagerDocumentSystemService.listManagerDocumentLegalEntities(),
        ManagerDocumentSystemService.getManagerDocumentPdfRuntime(),
        loadDocuments(),
      ]);
      legalEntities.value = entitiesResponse.items.filter((item) => item.status === 'active');
      pdfRuntime.value = runtimeResponse;
      selectedLegalEntityId.value = legalEntities.value.find((item) => item.is_default)?.id || legalEntities.value[0]?.id || null;
      await loadTemplates();
    } catch (error) {
      input.notify(`Документный контур не загружен: ${getApiErrorMessage(error)}`, 'error');
    } finally {
      loading.value = false;
    }
  };

  watch([selectedLegalEntityId, documentType], () => void loadTemplates(), { flush: 'sync' });
  watch(documentType, (nextType, previousType) => {
    if (isConsumerDocumentType(nextType) && !isConsumerDocumentType(previousType)) {
      resetConsumerTerms();
    }
  });
  watch(selectedLegalEntityId, (legalEntityId, previousLegalEntityId) => {
    const entity = legalEntities.value.find((item) => item.id === legalEntityId);
    issueCity.value = String(entity?.requisites.city || '').trim();
    if (
      isConsumerDocumentType(documentType.value)
      && consumerTerms.value.goods_warranty_months === defaultGoodsWarrantyMonths(previousLegalEntityId)
    ) {
      consumerTerms.value = {
        ...consumerTerms.value,
        goods_warranty_months: defaultGoodsWarrantyMonths(legalEntityId),
      };
    }
    if (
      ['supply', 'supply_installation'].includes(businessTerms.value.contract_scenario || '')
      && businessTerms.value.goods_warranty_months === defaultGoodsWarrantyMonths(previousLegalEntityId)
      && !businessTerms.value.goods_warranty_terms
    ) {
      businessTerms.value = {
        ...businessTerms.value,
        goods_warranty_months: defaultGoodsWarrantyMonths(legalEntityId),
      };
    }
  }, { flush: 'sync' });
  watch(selectedTemplateId, () => void loadTemplateVersions(), { flush: 'sync' });

  const createDraft = async () => {
    if (draftBlockedReason.value || !selectedLegalEntityId.value) return;
    busy.value = true;
    try {
      const payload = {
        legal_entity_id: selectedLegalEntityId.value,
        document_type: documentType.value,
        issue_date: issueDate.value,
        issue_city: issueCity.value.trim() || null,
        template_id: selectedTemplateId.value,
        proposal_id: input.proposalId() || null,
        business_role: documentType.value === 'invoice' ? businessRole.value : null,
        base_document_id: baseDocumentId.value,
        base_customer_contract_id: baseCustomerContractId.value,
        replaces_document_id: replacesDocumentId.value,
        consumer_terms: isConsumerDocumentType(documentType.value) ? consumerTerms.value : undefined,
        business_terms: isBusinessTermsDocumentType(documentType.value)
          ? serializeBusinessTerms(documentType.value, businessTerms.value)
          : undefined,
        act_terms: documentType.value === 'act' ? actTerms.value : undefined,
      };
      await ManagerDocumentSystemService.createManagerManagedDocumentDraft(input.orderId(), payload);
      replacesDocumentId.value = null;
      resetConsumerTerms();
      resetBusinessTerms();
      resetActTerms();
      await loadDocuments();
      input.refresh();
      input.notify('Черновик создан. Данные заказа зафиксированы, но официальный номер ещё не занят.');
    } catch (error) {
      input.notify(`Не удалось создать черновик: ${getApiErrorMessage(error)}`, 'error');
    } finally {
      busy.value = false;
    }
  };

  const issue = async (document: ManagedDocumentItem) => {
    if (issueBlockedReason.value) return;
    busy.value = true;
    try {
      await ManagerDocumentSystemService.issueManagerManagedDocument(document.id);
      await loadDocuments();
      input.refresh();
      input.notify('Документу присвоен официальный номер, DOCX и PDF сохранены.');
    } catch (error) {
      input.notify(`Выпуск не завершён: ${getApiErrorMessage(error)}`, 'error');
      await loadDocuments();
    } finally {
      busy.value = false;
    }
  };

  const deleteDraft = async (document: ManagedDocumentItem) => {
    if (document.status !== 'draft') return;
    if (!await confirmDialog({
      title: 'Удалить черновик?',
      description: 'Официальный номер ещё не присвоен, поэтому черновик можно удалить без следа в нумерации.',
      confirmText: 'Удалить черновик',
      variant: 'danger',
    })) return;
    busy.value = true;
    try {
      await ManagerDocumentSystemService.deleteManagerManagedDocumentDraft(document.id);
      await loadDocuments();
      input.refresh();
      input.notify('Черновик удалён. Официальная нумерация не изменилась.');
    } catch (error) {
      input.notify(`Не удалось удалить черновик: ${getApiErrorMessage(error)}`, 'error');
    } finally {
      busy.value = false;
    }
  };

  const requestVoid = (document: ManagedDocumentItem) => {
    voidTarget.value = document;
    voidReason.value = '';
  };

  const voidDocument = async () => {
    if (!voidTarget.value || !voidReason.value.trim()) return;
    busy.value = true;
    try {
      await ManagerDocumentSystemService.voidManagerManagedDocument(voidTarget.value.id, { reason: voidReason.value.trim() });
      voidTarget.value = null;
      voidReason.value = '';
      await loadDocuments();
      input.refresh();
      input.notify('Документ аннулирован. Номер не будет выдан повторно.');
    } catch (error) {
      input.notify(`Не удалось аннулировать: ${getApiErrorMessage(error)}`, 'error');
    } finally {
      busy.value = false;
    }
  };

  const prepareReplacement = (document: ManagedDocumentItem) => {
    resetConsumerTerms();
    resetBusinessTerms();
    resetActTerms();
    preferredTemplateId = document.document_template_id || null;
    documentType.value = document.doc_type;
    selectedLegalEntityId.value = document.legal_entity_id || selectedLegalEntityId.value;
    businessRole.value = document.business_role === 'offer' ? 'offer' : 'payment_request';
    issueDate.value = (document.official_date || document.date).slice(0, 10);
    issueCity.value = document.issue_city
      || String(legalEntities.value.find((item) => item.id === selectedLegalEntityId.value)?.requisites.city || '').trim();
    replacesDocumentId.value = document.id;
  };

  const downloadArtifact = async (artifactId: string) => {
    const popup = window.open('about:blank', '_blank');
    if (popup) popup.opener = null;
    try {
      const access = await ManagerDocumentSystemService.getManagerDocumentArtifactAccess(artifactId);
      const downloadUrl = new URL(access.url, window.location.origin).toString();
      if (popup) {
        popup.location.replace(downloadUrl);
      } else {
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.rel = 'noopener noreferrer';
        link.target = '_blank';
        link.click();
      }
    } catch (error) {
      popup?.close();
      input.notify(`Не удалось открыть файл: ${getApiErrorMessage(error)}`, 'error');
    }
  };

  return {
    actTerms,
    baseCustomerContractId,
    baseDocumentId,
    businessRole,
    businessTerms,
    busy,
    consumerTerms,
    createDraft,
    deleteDraft,
    documentType,
    documents,
    downloadArtifact,
    draftBlockedReason,
    issue,
    issueBlockedReason,
    issueCity,
    issueDate,
    legalEntities,
    loading,
    loadWorkspace,
    pdfRuntime,
    prepareReplacement,
    replacesDocumentId,
    requestVoid,
    resetConsumerTerms,
    resetBusinessTerms,
    resetActTerms,
    selectedLegalEntityId,
    selectedGoodsWarrantyDefault,
    selectedTemplateId,
    templates,
    templatesLoading,
    voidDocument,
    voidReason,
    voidTarget,
  };
};
