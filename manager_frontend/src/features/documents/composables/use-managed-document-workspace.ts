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
  isSupplyInstallationDocumentType,
  type ConsumerDocumentTerms,
} from '../model/consumer-document-terms';
import {
  calculateInstallationTwoStages,
  normalizeByNAmount,
} from '../model/installation-two-stages';
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
import {
  createDefaultTransportTerms,
  serializeTransportTerms,
  type TransportTerms,
} from '../model/transport-terms';
import { openNativeDocumentPreview } from '../integrations/native-document-preview';

type ManagedWorkspaceInput = {
  orderId: () => number;
  proposalId: () => number | null;
  proposalTotalCents: () => number | null;
  notify: (message: string, type?: 'success' | 'error') => void;
  refresh: () => void;
};

type ConsumerDefaultField = 'equipment_brand' | 'equipment_model' | 'goods_warranty_months' | 'goods_warranty_terms';

const consumerDefaultFields: ConsumerDefaultField[] = [
  'equipment_brand',
  'equipment_model',
  'goods_warranty_months',
  'goods_warranty_terms',
];

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
  const transportTerms = ref<TransportTerms>(createDefaultTransportTerms());
  const consumerDefaultsLoading = ref(false);
  const consumerDefaultsLoaded = ref(false);
  const busy = ref(false);
  const loading = ref(false);
  const templatesLoading = ref(false);
  const templateVersionsLoading = ref(false);
  const voidTarget = ref<ManagedDocumentItem | null>(null);
  const voidReason = ref('');
  let requestId = 0;
  let templateRequestId = 0;
  let versionRequestId = 0;
  let consumerDefaultsRequestId = 0;
  let consumerDefaultsContext = '';
  let consumerDefaultsScope = '';
  const manuallyEditedConsumerDefaultFields = new Set<ConsumerDefaultField>();
  let preferredTemplateId: number | null = null;
  const templateUseCaseKey = computed(() => {
    if (documentType.value === 'contract') return businessTerms.value.contract_scenario || '';
    if (documentType.value === 'invoice') return businessRole.value;
    return '';
  });

  const defaultGoodsWarrantyMonths = (legalEntityId = selectedLegalEntityId.value) => {
    if (isConsumerDocumentType(documentType.value)) return 36;
    const entity = legalEntities.value.find((item) => item.id === legalEntityId);
    const raw = entity?.requisites.default_goods_warranty_months;
    const configured = raw == null || raw === '' ? Number.NaN : Number(raw);
    return Number.isFinite(configured) && configured >= 0 && configured <= 240 ? configured : 36;
  };
  const defaultWorkWarrantyMonths = (legalEntityId = selectedLegalEntityId.value) => {
    const entity = legalEntities.value.find((item) => item.id === legalEntityId);
    const raw = entity?.requisites.default_work_warranty_months;
    const configured = raw == null || raw === '' ? Number.NaN : Number(raw);
    return Number.isFinite(configured) && configured >= 0 && configured <= 240 ? configured : null;
  };
  const selectedGoodsWarrantyDefault = computed(() => defaultGoodsWarrantyMonths());

  const resetConsumerTerms = () => {
    consumerTerms.value = createDefaultConsumerDocumentTerms(
      defaultGoodsWarrantyMonths(),
      defaultWorkWarrantyMonths(),
    );
    manuallyEditedConsumerDefaultFields.clear();
  };
  const resetSoldEquipmentTerms = () => {
    consumerTerms.value = {
      ...consumerTerms.value,
      equipment_brand: null,
      equipment_model: null,
      equipment_serial: null,
      goods_warranty_months: 36,
      goods_warranty_terms: null,
      installation_two_stages: false,
      installation_first_stage_amount: null,
    };
    manuallyEditedConsumerDefaultFields.clear();
  };
  const updateConsumerTerms = (nextTerms: ConsumerDocumentTerms) => {
    for (const field of consumerDefaultFields) {
      if (nextTerms[field] !== consumerTerms.value[field]) {
        manuallyEditedConsumerDefaultFields.add(field);
      }
    }
    consumerTerms.value = nextTerms;
  };
  const loadConsumerDefaults = async () => {
    const orderId = input.orderId();
    const proposalId = input.proposalId();
    const issueDateAtRequest = issueDate.value;
    const requestContext = consumerDefaultsContext;
    const currentRequest = ++consumerDefaultsRequestId;
    consumerDefaultsLoading.value = true;
    consumerDefaultsLoaded.value = false;
    try {
      const defaults = await ManagerDocumentSystemService.getManagerConsumerEquipmentDefaults(
        orderId,
        proposalId,
        issueDateAtRequest || null,
      );
      if (
        currentRequest !== consumerDefaultsRequestId
        || requestContext !== consumerDefaultsContext
        || documentType.value !== 'b2c_supply_installation_act'
        || input.orderId() !== orderId
        || input.proposalId() !== proposalId
      ) return;
      const current = consumerTerms.value;
      consumerTerms.value = {
        ...current,
        equipment_brand: !manuallyEditedConsumerDefaultFields.has('equipment_brand')
          ? defaults.equipment_brand ?? null : current.equipment_brand,
        equipment_model: !manuallyEditedConsumerDefaultFields.has('equipment_model')
          ? defaults.equipment_model ?? null : current.equipment_model,
        goods_warranty_months: !manuallyEditedConsumerDefaultFields.has('goods_warranty_months')
          ? defaults.goods_warranty_months : current.goods_warranty_months,
        goods_warranty_terms: !manuallyEditedConsumerDefaultFields.has('goods_warranty_terms')
          ? defaults.goods_warranty_terms ?? null : current.goods_warranty_terms,
      };
      consumerDefaultsLoaded.value = true;
    } catch (error) {
      if (currentRequest === consumerDefaultsRequestId && requestContext === consumerDefaultsContext) {
        input.notify(`Не удалось подставить оборудование: ${getApiErrorMessage(error)}`, 'error');
      }
    } finally {
      if (currentRequest === consumerDefaultsRequestId && requestContext === consumerDefaultsContext) {
        consumerDefaultsLoading.value = false;
      }
    }
  };
  const resetBusinessTerms = () => {
    businessTerms.value = createDefaultBusinessDocumentTerms();
  };
  const resetActTerms = () => {
    actTerms.value = createDefaultActTerms();
  };
  const resetTransportTerms = () => {
    transportTerms.value = createDefaultTransportTerms();
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
    if (isSupplyInstallationDocumentType(documentType.value) && consumerDefaultsLoading.value) {
      return 'Подставляем данные оборудования…';
    }
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
    if (isSupplyInstallationDocumentType(documentType.value) && consumerTerms.value.installation_two_stages) {
      const validation = calculateInstallationTwoStages(
        consumerTerms.value.installation_first_stage_amount,
        input.proposalTotalCents(),
      );
      if (validation.error) return validation.error;
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
      const activeTemplates = response.items.filter((item) => item.is_active);
      if (documentType.value === 'contract' && templateUseCaseKey.value) {
        const exact = activeTemplates.filter(
          (item) => item.contract_scenario === templateUseCaseKey.value,
        );
        const universal = activeTemplates.filter((item) => !item.contract_scenario);
        templates.value = exact.length ? [...exact, ...universal] : universal;
      } else if (documentType.value === 'invoice') {
        const exact = activeTemplates.filter(
          (item) => item.business_role === templateUseCaseKey.value,
        );
        const universal = activeTemplates.filter((item) => !item.business_role);
        templates.value = exact.length ? [...exact, ...universal] : universal;
      } else {
        templates.value = activeTemplates;
      }
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
    resetTransportTerms();
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

  watch(
    [selectedLegalEntityId, documentType, templateUseCaseKey],
    () => void loadTemplates(),
    { flush: 'sync' },
  );
  watch(documentType, (nextType, previousType) => {
    if (isConsumerDocumentType(nextType) && !isConsumerDocumentType(previousType)) {
      resetConsumerTerms();
    }
    if (['tn2', 'ttn1'].includes(nextType) && !['tn2', 'ttn1'].includes(previousType)) {
      resetTransportTerms();
    }
    if (
      previousType === 'b2c_supply_installation_act'
      && nextType === 'b2c_customer_equipment_installation_act'
    ) {
      resetSoldEquipmentTerms();
    }
  });
  watch(selectedLegalEntityId, (legalEntityId, previousLegalEntityId) => {
    const entity = legalEntities.value.find((item) => item.id === legalEntityId);
    issueCity.value = String(entity?.requisites.city || '').trim();
    if (
      isConsumerDocumentType(documentType.value)
      && consumerTerms.value.work_warranty_months === defaultWorkWarrantyMonths(previousLegalEntityId)
    ) {
      consumerTerms.value = {
        ...consumerTerms.value,
        work_warranty_months: defaultWorkWarrantyMonths(legalEntityId),
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
  watch(
    [documentType, () => input.orderId(), () => input.proposalId(), issueDate],
    ([type, orderId, proposalId, nextIssueDate]) => {
      const scope = type === 'b2c_supply_installation_act' ? `${orderId}:${proposalId || ''}` : '';
      const context = scope ? `${scope}:${nextIssueDate}` : '';
      if (context === consumerDefaultsContext) return;
      const scopeChanged = scope !== consumerDefaultsScope;
      consumerDefaultsScope = scope;
      consumerDefaultsContext = context;
      ++consumerDefaultsRequestId;
      if (!context) {
        consumerDefaultsLoading.value = false;
        consumerDefaultsLoaded.value = false;
        return;
      }
      if (scopeChanged) resetSoldEquipmentTerms();
      void loadConsumerDefaults();
    },
    { flush: 'sync' },
  );
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
        consumer_terms: isConsumerDocumentType(documentType.value)
          ? {
            ...consumerTerms.value,
            goods_warranty_months: isSupplyInstallationDocumentType(documentType.value)
              && !consumerDefaultsLoaded.value
              && !manuallyEditedConsumerDefaultFields.has('goods_warranty_months')
              ? null
              : consumerTerms.value.goods_warranty_months,
            goods_warranty_terms: isSupplyInstallationDocumentType(documentType.value)
              && !consumerDefaultsLoaded.value
              && !manuallyEditedConsumerDefaultFields.has('goods_warranty_terms')
              ? null
              : consumerTerms.value.goods_warranty_terms,
            installation_first_stage_amount: consumerTerms.value.installation_two_stages
              ? normalizeByNAmount(consumerTerms.value.installation_first_stage_amount)
              : null,
          }
          : undefined,
        business_terms: isBusinessTermsDocumentType(documentType.value)
          ? serializeBusinessTerms(documentType.value, businessTerms.value)
          : undefined,
        act_terms: documentType.value === 'act' ? actTerms.value : undefined,
        transport_terms: ['tn2', 'ttn1'].includes(documentType.value)
          ? serializeTransportTerms(transportTerms.value)
          : undefined,
      };
      await ManagerDocumentSystemService.createManagerManagedDocumentDraft(input.orderId(), payload);
      replacesDocumentId.value = null;
      resetConsumerTerms();
      if (isSupplyInstallationDocumentType(documentType.value)) {
        consumerDefaultsContext = '';
        void loadConsumerDefaults();
      }
      resetBusinessTerms();
      resetActTerms();
      resetTransportTerms();
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
    resetTransportTerms();
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

  const previewDraft = async (document: ManagedDocumentItem) => {
    try {
      await openNativeDocumentPreview(document.id);
    } catch (error) {
      input.notify(`Не удалось открыть предпросмотр: ${getApiErrorMessage(error)}`, 'error');
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
    updateConsumerTerms,
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
    previewDraft,
    legalEntities,
    loading,
    loadDocuments,
    loadWorkspace,
    pdfRuntime,
    prepareReplacement,
    replacesDocumentId,
    requestVoid,
    resetConsumerTerms,
    resetBusinessTerms,
    resetActTerms,
    resetTransportTerms,
    selectedLegalEntityId,
    selectedGoodsWarrantyDefault,
    selectedTemplateId,
    templates,
    templatesLoading,
    transportTerms,
    voidDocument,
    voidReason,
    voidTarget,
  };
};
