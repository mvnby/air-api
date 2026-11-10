import { newAmendmentTerms, amendmentTermsError } from '../model/contract-amendment';
import type { AmendmentBasisItem } from '../../../client';
import { computed, onScopeDispose, ref, watch } from 'vue';
import { commercialTermsApi, mergeCommercialDocumentDefaults } from '../../../services/commercial-terms-api';
import type { DocumentRoleType } from '../model/document-types';
import {
  ManagerDocumentSystemService,
  OpenAPI,
  type CancelablePromise,
  type DocumentLegalEntityItem,
  type DocumentPdfRuntimeStatus,
  type ManagedDocumentItem,
  type ManagerOrderDetailResponse,
  type ManagedDocumentDraftPayload,
  type DocumentCustomerReadiness,
  type NativeDocumentTemplateItem,
  type NativeTemplateVersionItem,
} from '../../../client';
import { getApiErrorMessage } from '../../../utils/api-errors';
import { toLocalDateTimeInput } from '../../../utils/datetime';
import { confirmDialog } from '../../../services/ui-feedback';
import { checksCustomerTemplate, customerFieldsAllowIssue } from '../model/customer-document-readiness';
import { previousContractAct, type ContractActConfirmation, type PreviousContractAct } from '../model/contract-act-number';
import {
  createDefaultConsumerDocumentTerms,
  isConsumerDocumentType,
  isSupplyInstallationDocumentType,
  isStagedInstallationDocumentType,
  type ConsumerDocumentTerms,
} from '../model/consumer-document-terms';
import {
  installationTermsError,
  serializeInstallationTerms,
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
import { newRepairDefectForm, repairDefectPayload } from '../model/repair-defect';
import { isCustomerEquipmentWorkAct } from '../model/consumer-document-terms';
import { hasInitialDocumentForm } from '../model/native-document-options';
import { openNativeDocumentPreview } from '../integrations/native-document-preview';

type ManagedWorkspaceInput = {
  orderId: () => number;
  customerContext?: () => unknown;
  repairOrder?: () => ManagerOrderDetailResponse;
  waybillSelection?: () => ManagedDocumentDraftPayload['waybill_composition'];
  actScope?: () => Pick<ManagedDocumentDraftPayload,
    'scope_customer_branch_id' | 'scope_title' | 'scope_address' | 'scope_service_line_ids' | 'scope_service_line_quantities'>;
  workflowType: () => string | null | undefined;
  proposalId: () => number | null;
  proposalTotalCents: (type: string) => number | null;
  selectedMaterialIds: () => number[] | null;
  notify: (message: string, type?: 'success' | 'error') => void;
  refresh: () => void;
};

type IssueAction = {
  isCurrent: () => boolean;
  canIssue: () => boolean;
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
  const customerReadiness = ref<DocumentCustomerReadiness | null>(null);
  const legalEntities = ref<DocumentLegalEntityItem[]>([]);
  const templates = ref<NativeDocumentTemplateItem[]>([]);
  const templateVersions = ref<NativeTemplateVersionItem[]>([]);
  const pdfRuntime = ref<DocumentPdfRuntimeStatus | null>(null);
  const selectedLegalEntityId = ref<number | null>(null);
  const selectedTemplateId = ref<number | null>(null);
  const documentType = ref('offer');
  const businessRole = ref<'payment_request' | 'offer'>('payment_request');
  const documentRoleType = ref<DocumentRoleType | null>(null);
  const issueDate = ref(toLocalDateTimeInput(new Date().toISOString()).slice(0, 10));
  const issueCity = ref('');
  const replacesDocumentId = ref<number | null>(null);
  const baseDocumentId = ref<number | null>(null);
  const baseCustomerContractId = ref<number | null>(null);
  const consumerTerms = ref<ConsumerDocumentTerms>(createDefaultConsumerDocumentTerms());
  const replacementConsumerBaseline = ref<ConsumerDocumentTerms | null>(null);
  const replacementTotalCents = ref<number | null>(null);
  const replacementProposalId = ref<number | null>(null);
  const consumerProposalTotalCents = computed(() => replacesDocumentId.value && replacementTotalCents.value !== null
    ? replacementTotalCents.value : input.proposalTotalCents(documentType.value));
  const businessTerms = ref<BusinessDocumentTerms>(createDefaultBusinessDocumentTerms());
  const actTerms = ref<ActTerms>(createDefaultActTerms());
  const transportTerms = ref<TransportTerms>(createDefaultTransportTerms());
  const repairDefect = ref(newRepairDefectForm(input.repairOrder?.()));
  const receiptNote = ref('');
  const warrantyEquipmentId = ref<number | null>(null);
  watch([() => input.orderId(), () => input.proposalId(), documentType], () => {
    receiptNote.value = '';
    warrantyEquipmentId.value = null;
  }, { flush: 'sync' });
  const amendmentTerms = ref(newAmendmentTerms());
  const amendmentBases = ref<AmendmentBasisItem[]>([]);
  const amendmentBasisId = ref<number | null>(null);
  const selectedAmendmentBasis = computed(() => amendmentBases.value.find(b => b.document_id === amendmentBasisId.value));
  const amendmentBasisError = ref('');
  const loadAmendmentBases = async () => {
    const orderId = input.orderId();
    amendmentBasisError.value = '';
    try {
      const response = await ManagerDocumentSystemService.listManagerContractAmendmentBases(orderId);
      if (input.orderId() === orderId) amendmentBases.value = response.items;
    } catch (error) {
      if (input.orderId() === orderId) amendmentBasisError.value = getApiErrorMessage(error);
    }
  };
  watch([documentType, () => input.orderId()], () => {
    amendmentBasisId.value = null;
    amendmentBases.value = [];
    if (documentType.value === 'contract_amendment') void loadAmendmentBases();
  }, { flush: 'sync' });
  watch(selectedAmendmentBasis, basis => {
    if (basis) selectedLegalEntityId.value = basis.legal_entity_id;
  }, { flush: 'sync' });
  const participantStatement = ref({ procedure_reference: '', lot: '', buyer_name: '', declaration_text: '' });
  const contractActPrompt = ref<{ documentId: number; previous: PreviousContractAct } | null>(null);
  const participantStatementConfirmations = ref<Record<number, boolean>>({});
  watch([() => input.orderId(), () => input.repairOrder?.().customer?.id], () => {
    repairDefect.value = newRepairDefectForm(input.repairOrder?.());
  }, { flush: 'sync' });
  watch(() => input.orderId(), () => {
    participantStatement.value = { procedure_reference: '', lot: '', buyer_name: '', declaration_text: '' };
    participantStatementConfirmations.value = {};
    contractActPrompt.value = null;
  }, { flush: 'sync' });
  const consumerDefaultsLoading = ref(false);
  const consumerDefaultsLoaded = ref(false);
  const busy = ref(false);
  const loading = ref(false);
  const templatesLoading = ref(false);
  const templateVersionsLoading = ref(false);
  const templateLoadError = ref('');
  const versionLoadError = ref('');
  const voidTarget = ref<ManagedDocumentItem | null>(null);
  const voidReason = ref('');
  let workspaceActive = true;
  let workspaceGeneration = 0;
  const pendingMutations = new Set<{ cancel: () => void; isCurrent: () => boolean }>();
  const cancelStaleMutations = () => {
    for (const pending of pendingMutations) if (!pending.isCurrent()) pending.cancel();
  };
  const awaitMutation = async <T>(request: CancelablePromise<T>, isCurrent: () => boolean) => {
    const pending = { cancel: () => request.cancel(), isCurrent };
    pendingMutations.add(pending);
    if (!isCurrent()) pending.cancel();
    try {
      return await request;
    } finally {
      pendingMutations.delete(pending);
    }
  };
  let issueActionGeneration = 0;
  let requestId = 0;
  watch(() => input.orderId(), () => {
    workspaceGeneration += 1;
    issueActionGeneration += 1;
    cancelStaleMutations();
    requestId += 1;
    busy.value = false;
  }, { flush: 'sync' });
  onScopeDispose(() => {
    workspaceActive = false;
    workspaceGeneration += 1;
    issueActionGeneration += 1;
    cancelStaleMutations();
    requestId += 1;
  });

  const beginIssueAction = (document: ManagedDocumentItem): IssueAction => {
    const orderId = input.orderId();
    const generation = ++issueActionGeneration;
    cancelStaleMutations();
    const isCurrent = () => workspaceActive && generation === issueActionGeneration
      && input.orderId() === orderId;
    const canIssue = () => {
      if (!isCurrent() || document.order_id !== orderId) return false;
      const current = documents.value.find((item) => item.id === document.id);
      return current?.order_id === orderId && current.status === 'draft'
        && current.doc_type === document.doc_type
        && current.document_template_id === document.document_template_id
        && current.template_version_id === document.template_version_id;
    };
    return { isCurrent, canIssue };
  };
  let templateRequestId = 0;
  let versionRequestId = 0;
  let commercialDefaultsRequestId = 0;
  let loadedWorkspaceOrderId: number | null = null;
  let commercialDefaultsBaseline = createDefaultBusinessDocumentTerms(input.workflowType());
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
  const suggestedDocumentRole = (): DocumentRoleType => input.workflowType() === 'sales_installation' || !input.workflowType()
    ? 'seller_buyer' : 'executor_customer';

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
      equipment_id: null,
      equipment_brand: null,
      equipment_model: null,
      equipment_serial: null,
      goods_warranty_months: 36,
      goods_warranty_terms: null,
      installation_two_stages: false,
      installation_outdoor_unit_in_first_stage: true,
      installation_first_stage_amount: null,
      installation_remaining_amount: null,
      installation_unit_count: 1,
      installation_first_stage_works: null,
      installation_second_stage_works: null,
      installation_second_stage_due: null,
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
  const loadCommercialDefaults = async () => {
    const orderId = input.orderId();
    const currentRequest = ++commercialDefaultsRequestId;
    const proposalId = input.proposalId();
    const type = documentType.value;
    const replacementId = replacesDocumentId.value;
    if (!isBusinessTermsDocumentType(type) || replacementId !== null) return;
    const baseline = commercialDefaultsBaseline;
    try {
      const response = await commercialTermsApi.defaults(orderId);
      if (currentRequest !== commercialDefaultsRequestId || input.orderId() !== orderId
        || input.proposalId() !== proposalId || documentType.value !== type
        || replacesDocumentId.value !== replacementId || !response.business_terms) return;
      businessTerms.value = mergeCommercialDocumentDefaults(businessTerms.value, baseline, response.business_terms);
    } catch (error) {
      if (currentRequest === commercialDefaultsRequestId && input.orderId() === orderId) {
        input.notify(`Не удалось подставить согласованные условия: ${getApiErrorMessage(error)}`, 'error');
      }
    }
  };
  const resetBusinessTerms = () => {
    commercialDefaultsRequestId += 1;
    businessTerms.value = createDefaultBusinessDocumentTerms(input.workflowType());
    commercialDefaultsBaseline = JSON.parse(JSON.stringify(businessTerms.value)) as BusinessDocumentTerms;
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
  const installationTwoStagesError = computed(() => {
    if (!isStagedInstallationDocumentType(documentType.value) || !consumerTerms.value.installation_two_stages) {
      return '';
    }
    return installationTermsError(
      consumerTerms.value,
      consumerProposalTotalCents.value,
    );
  });

  const draftBlockedReason = computed(() => {
    if (templatesLoading.value || templateVersionsLoading.value) return 'Загружаем подходящий шаблон…';
    if (isSupplyInstallationDocumentType(documentType.value) && consumerDefaultsLoading.value) {
      return 'Подставляем данные оборудования…';
    }
    if (!selectedLegalEntityId.value) return 'Нет юридического лица';
    if (documentType.value === 'contract_amendment') {
      if (amendmentBasisError.value) return amendmentBasisError.value;
      if (!replacesDocumentId.value && !selectedAmendmentBasis.value) return 'Выберите исходный договор';
      if (!replacesDocumentId.value && selectedAmendmentBasis.value?.legal_entity_id !== selectedLegalEntityId.value) return 'Выберите юридическое лицо исходного договора';
      const error = amendmentTermsError(amendmentTerms.value);
      if (error) return error;
    }
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
    if (isConsumerDocumentType(documentType.value) || documentType.value === 'retail_receipt') {
      const requisites = legalEntities.value.find(
        (item) => item.id === selectedLegalEntityId.value,
      )?.requisites;
      if (!requisites?.offer_url || !requisites.offer_version || !requisites.offer_published_on) {
        return 'Для документа физлицу заполните ссылку, версию и дату публичной оферты';
      }
    }
    if (installationTwoStagesError.value) return installationTwoStagesError.value;
    if (documentType.value === 'participant_statement') {
      const statement = participantStatement.value;
      if (!statement.procedure_reference.trim() || !statement.lot.trim()
        || !statement.buyer_name.trim() || !statement.declaration_text.trim()) {
        return 'Заполните процедуру, лот, заказчика и текст заявления';
      }
    }
    if (hasInitialDocumentForm(documentType.value) && !selectedTemplateId.value) return '';
    if (!selectedTemplateId.value) return 'Нет шаблона для этого типа';
    if (!selectedTemplateHasActiveVersion.value) return 'У шаблона нет активной DOCX-версии';
    if (['act', 'tn2', 'ttn1'].includes(documentType.value) && !baseDocumentId.value && !baseCustomerContractId.value) {
      return 'Нет подходящего документа-основания';
    }
    return '';
  });

  const loadDocuments = async (isCurrent = () => true) => {
    if (!workspaceActive || !isCurrent()) return;
    const orderId = input.orderId();
    const currentRequest = ++requestId;
    try {
      const response = await ManagerDocumentSystemService.listManagerManagedOrderDocuments(orderId);
      if (workspaceActive && isCurrent() && currentRequest === requestId && input.orderId() === orderId) {
        documents.value = response.items.filter((item) => item.provider === 'native');
      }
    } catch (error) {
      if (workspaceActive && isCurrent() && currentRequest === requestId && input.orderId() === orderId) {
        input.notify(`Не удалось загрузить CRM-документы: ${getApiErrorMessage(error)}`, 'error');
      }
    }
  };

  const loadTemplateVersions = async () => {
    const legalEntityId = selectedLegalEntityId.value;
    const templateId = selectedTemplateId.value;
    const currentRequest = ++versionRequestId;
    versionLoadError.value = '';
    if (templateVersions.value.some((version) => version.template_id !== templateId)) templateVersions.value = [];
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
    } catch (error) {
      if (currentRequest === versionRequestId) {
        templateVersions.value = [];
        versionLoadError.value = getApiErrorMessage(error);
      }
    } finally {
      if (currentRequest === versionRequestId) templateVersionsLoading.value = false;
    }
  };

  const loadTemplates = async () => {
    const legalEntityId = selectedLegalEntityId.value;
    const type = documentType.value;
    const currentRequest = ++templateRequestId;
    templateLoadError.value = '';
    versionLoadError.value = '';
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
      const exactTemplates = documentType.value === 'contract'
        ? templates.value.filter((item) => item.contract_scenario === templateUseCaseKey.value)
        : documentType.value === 'invoice'
          ? templates.value.filter((item) => item.business_role === templateUseCaseKey.value)
          : [];
      selectedTemplateId.value = preferred?.id
        || exactTemplates.find((item) => item.is_default)?.id
        || exactTemplates[0]?.id
        || templates.value.find((item) => item.is_default)?.id
        || templates.value[0]?.id
        || null;
      preferredTemplateId = null;
    } catch (error) {
      if (currentRequest === templateRequestId) {
        templates.value = [];
        selectedTemplateId.value = null;
        templateLoadError.value = getApiErrorMessage(error);
        input.notify(`Не удалось загрузить шаблоны: ${templateLoadError.value}`, 'error');
      }
    } finally {
      if (currentRequest === templateRequestId) templatesLoading.value = false;
    }
  };

  const loadWorkspace = async () => {
    loading.value = true;
    replacesDocumentId.value = null;
    documentRoleType.value = ['contract', 'offer', 'invoice'].includes(documentType.value)
      ? suggestedDocumentRole() : null;
    if (loadedWorkspaceOrderId !== input.orderId()) {
      loadedWorkspaceOrderId = input.orderId();
      resetConsumerTerms();
      resetBusinessTerms();
      resetActTerms();
      resetTransportTerms();
    }
    void loadCommercialDefaults();
    try {
      const [entitiesResponse, runtimeResponse] = await Promise.all([
        ManagerDocumentSystemService.listManagerDocumentLegalEntities(),
        ManagerDocumentSystemService.getManagerDocumentPdfRuntime(),
        loadDocuments(),
      ]);
      legalEntities.value = entitiesResponse.items.filter((item) => item.status === 'active');
      pdfRuntime.value = runtimeResponse;
      selectedLegalEntityId.value = legalEntities.value.find((item) => item.is_default)?.id || legalEntities.value[0]?.id || null;
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
  watch([documentType, () => input.proposalId(), replacesDocumentId], () => {
    commercialDefaultsRequestId += 1;
    if (loadedWorkspaceOrderId === input.orderId()) void loadCommercialDefaults();
  }, { flush: 'sync' });
  watch(documentType, (type) => {
    documentRoleType.value = ['contract', 'offer', 'invoice'].includes(type) ? suggestedDocumentRole() : null;
  }, { flush: 'sync' });
  watch(documentType, (nextType, previousType) => {
    if (replacesDocumentId.value) return;
    if (isConsumerDocumentType(nextType) && !isConsumerDocumentType(previousType)) {
      resetConsumerTerms();
    }
    if (nextType === 'ttn1' && previousType !== 'ttn1') {
      resetTransportTerms();
    }
    if (
      isStagedInstallationDocumentType(previousType)
      && nextType !== previousType
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
      if (replacesDocumentId.value) {
        consumerDefaultsLoading.value = false;
        return;
      }
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

  const draftPayload = computed(() => ({
    waybill_composition: ['tn2', 'ttn1'].includes(documentType.value) ? input.waybillSelection?.() : undefined,
    ...(documentType.value === 'act' ? input.actScope?.() : {}),
    scope_product_line_ids: isCustomerEquipmentWorkAct(documentType.value) ? input.selectedMaterialIds() ?? undefined : undefined,
    legal_entity_id: selectedLegalEntityId.value,
    repair_defect: documentType.value === 'repair_defect_act' ? repairDefectPayload(repairDefect.value) : undefined,
    receipt_note: documentType.value === 'retail_receipt' ? receiptNote.value.trim() || null : undefined,
    warranty_equipment_id: documentType.value === 'warranty_certificate' ? warrantyEquipmentId.value : undefined,
    participant_statement: documentType.value === 'participant_statement'
      ? { ...participantStatement.value } : undefined,
    document_type: documentType.value,
    issue_date: issueDate.value,
    issue_city: issueCity.value.trim() || null,
    template_id: selectedTemplateId.value,
    proposal_id: replacesDocumentId.value && isConsumerDocumentType(documentType.value)
      ? replacementProposalId.value : input.proposalId() || null,
    business_role: documentType.value === 'invoice' ? businessRole.value : null,
    document_role_type: ['contract', 'invoice', 'act', 'offer'].includes(documentType.value) ? documentRoleType.value : null,
    amendment_terms: documentType.value === 'contract_amendment' ? amendmentTerms.value : undefined,
    amendment_basis_revision: documentType.value === 'contract_amendment' ? selectedAmendmentBasis.value?.revision : undefined,
    base_document_id: documentType.value === 'contract_amendment' ? amendmentBasisId.value : baseDocumentId.value,
    base_customer_contract_id: baseCustomerContractId.value,
    replaces_document_id: replacesDocumentId.value,
    consumer_term_overrides: replacesDocumentId.value && replacementConsumerBaseline.value
      ? [...new Set([
        ...(Object.keys(consumerTerms.value) as (keyof ConsumerDocumentTerms)[])
          .filter(key => consumerTerms.value[key] !== replacementConsumerBaseline.value?.[key]),
        ...(consumerTerms.value.equipment_id !== replacementConsumerBaseline.value.equipment_id
          ? ['equipment_brand', 'equipment_model', 'equipment_serial'] : []),
      ])] : [],
    consumer_terms: isConsumerDocumentType(documentType.value)
      ? {
        ...serializeInstallationTerms(consumerTerms.value),
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
      }
      : undefined,
    business_terms: isBusinessTermsDocumentType(documentType.value)
      ? serializeBusinessTerms(documentType.value, businessTerms.value)
      : undefined,
    act_terms: documentType.value === 'act' ? actTerms.value : undefined,
    transport_terms: documentType.value === 'ttn1'
      ? serializeTransportTerms(transportTerms.value)
      : undefined,
  }));

  const customerContextKey = computed(() => JSON.stringify(input.customerContext?.() || null));
  watch([draftPayload, customerContextKey, () => input.orderId()], () => { customerReadiness.value = null; }, { deep: true, flush: 'sync' });

  const createDraft = async () => {
    if (!workspaceActive || draftBlockedReason.value || !selectedLegalEntityId.value) return;
    const generation = workspaceGeneration;
    const orderId = input.orderId();
    const isCurrent = () => workspaceActive && generation === workspaceGeneration && input.orderId() === orderId;
    busy.value = true;
    try {
      const payload = { ...JSON.parse(JSON.stringify(draftPayload.value)) as typeof draftPayload.value,
        legal_entity_id: selectedLegalEntityId.value };
      const contextKey = JSON.stringify({ payload, customer: customerContextKey.value });
      let allowIncompleteCustomer = false;
      if (checksCustomerTemplate(payload.document_type)) {
        const readiness = await ManagerDocumentSystemService.checkManagerManagedDocumentReadiness(orderId, payload);
        if (!isCurrent()) return;
        if (contextKey !== JSON.stringify({ payload: draftPayload.value, customer: customerContextKey.value })) {
          input.notify('Выбор документа изменился. Проверьте выбранный шаблон ещё раз.', 'error');
          return;
        }
        customerReadiness.value = readiness;
        if (payload.document_type !== 'contract_amendment' && !customerFieldsAllowIssue(readiness)) throw new Error('Не удалось подтвердить готовность документа');
        allowIncompleteCustomer = !readiness.can_issue;
      }
      if (!isCurrent()) return;
      const created = await awaitMutation(ManagerDocumentSystemService.createManagerManagedDocumentDraft(orderId, {
        ...payload, allow_incomplete_customer: allowIncompleteCustomer,
      }), isCurrent);
      if (!isCurrent()) return;
      customerReadiness.value = null;
      replacesDocumentId.value = null;
      resetConsumerTerms();
      if (isSupplyInstallationDocumentType(documentType.value)) {
        consumerDefaultsContext = '';
        void loadConsumerDefaults();
      }
      resetBusinessTerms();
      resetActTerms();
      resetTransportTerms();
      if (documentType.value === 'repair_defect_act') {
        repairDefect.value = newRepairDefectForm(input.repairOrder?.());
      }
      if (documentType.value === 'participant_statement') {
        participantStatement.value.declaration_text = '';
      }
      if (hasInitialDocumentForm(documentType.value)) void loadTemplates();
      receiptNote.value = '';
      warrantyEquipmentId.value = null;
      await loadDocuments(isCurrent);
      if (!isCurrent()) return;
      input.refresh();
      if (documentType.value === 'contract_amendment') { amendmentTerms.value = newAmendmentTerms(); void loadAmendmentBases(); }
      input.notify('Черновик создан');
      return created;
    } catch (error) {
      if (isCurrent()) input.notify(`Не удалось создать черновик: ${getApiErrorMessage(error)}`, 'error');
    } finally {
      if (isCurrent()) busy.value = false;
    }
  };

  const checkDocumentReadiness = async (document: ManagedDocumentItem, action = beginIssueAction(document)) => {
    if (!action.canIssue()) return false;
    if (document.status !== 'draft' || !checksCustomerTemplate(document.doc_type)) return true;
    busy.value = true;
    try {
      const readiness = await ManagerDocumentSystemService.getManagerManagedDocumentReadiness(document.id);
      if (!action.canIssue()) return false;
      documents.value = documents.value.map((item) => item.id === document.id
        ? { ...item, customer_readiness: readiness } : item);
      if (!customerFieldsAllowIssue(readiness)) throw new Error('Не удалось подтвердить готовность документа');
      return true;
    } catch (error) {
      if (action.canIssue()) input.notify(`Не удалось проверить реквизиты: ${getApiErrorMessage(error)}`, 'error');
      return false;
    } finally {
      if (action.isCurrent()) busy.value = false;
    }
  };

  const issue = async (document: ManagedDocumentItem, action = beginIssueAction(document), confirmation?: ContractActConfirmation) => {
    if (!action.canIssue() || issueBlockedReason.value) return;
    if (document.doc_type === 'participant_statement' && !participantStatementConfirmations.value[document.id]) {
      input.notify('Подтвердите проверку текста и фактов заявления перед выпуском.', 'error');
      return;
    }
    if (document.doc_type === 'contract_amendment' && !await confirmDialog({
      title: 'Зарегистрировать согласованное изменение?',
      description: `Дополнительные работы: ${document.amendment_change_amount} BYN. Расчётный итог: ${document.amendment_new_total} BYN. Выпуск включает изменение в согласованный объём; подпись, оплату и выполнение он не подтверждает.`,
      confirmText: 'Выпустить соглашение',
    })) return;
    if (!action.canIssue()) return;
    busy.value = true;
    try {
      let request;
      if (confirmation && document.doc_type === 'act') {
        request = ManagerDocumentSystemService.issueManagerManagedDocument(
          document.id, false, confirmation.previousNumber, confirmation.previousActId,
        );
      } else if (document.doc_type === 'participant_statement') {
        request = ManagerDocumentSystemService.issueManagerManagedDocument(document.id, true);
      } else {
        request = ManagerDocumentSystemService.issueManagerManagedDocument(document.id);
      }
      await awaitMutation(request, action.isCurrent);
      if (!action.isCurrent()) return;
      await loadDocuments();
      if (!action.isCurrent()) return;
      input.refresh();
      if (contractActPrompt.value?.documentId === document.id) contractActPrompt.value = null;
      if (document.doc_type === 'contract_amendment') void loadAmendmentBases();
      input.notify('Документ выпущен');
    } catch (error) {
      if (!action.isCurrent()) return;
      const previous = document.doc_type === 'act' ? previousContractAct(error) : null;
      if (previous) {
        contractActPrompt.value = { documentId: document.id, previous };
        return;
      }
      input.notify(`Выпуск не завершён: ${getApiErrorMessage(error)}`, 'error');
      await loadDocuments();
    } finally {
      if (action.isCurrent()) busy.value = false;
    }
  };

  const deleteDraft = async (document: ManagedDocumentItem) => {
    if (document.status !== 'draft') return;
    if (!await confirmDialog({
      title: 'Удалить черновик?',
      description: 'Черновик и его рабочие файлы будут удалены из CRM. Официальная нумерация не изменится. Если вы открывали его в Google, копия останется в Google Drive.',
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

  const cancelReplacement = () => {
    if (!replacesDocumentId.value) return;
    replacesDocumentId.value = null;
    replacementTotalCents.value = null;
    replacementProposalId.value = null;
    replacementConsumerBaseline.value = null;
    receiptNote.value = '';
    warrantyEquipmentId.value = null;
    repairDefect.value = newRepairDefectForm(input.repairOrder?.());
  };

  const prepareReplacement = (document: ManagedDocumentItem) => {
    const preservesConsumerTerms = (
      isConsumerDocumentType(documentType.value)
      && documentType.value === document.doc_type
    );
    if (!preservesConsumerTerms) resetConsumerTerms();
    resetBusinessTerms();
    resetActTerms();
    resetTransportTerms();
    if (document.doc_type === 'participant_statement' && document.participant_statement) {
      participantStatement.value = { ...document.participant_statement };
    }
    if (document.doc_type === 'repair_defect_act') {
      repairDefect.value = document.repair_defect ? { ...document.repair_defect } : newRepairDefectForm();
    }
    preferredTemplateId = document.document_template_id || null;
    documentType.value = document.doc_type;
    receiptNote.value = document.receipt_note || '';
    warrantyEquipmentId.value = document.warranty_equipment_id || null;
    selectedLegalEntityId.value = document.legal_entity_id || selectedLegalEntityId.value;
    businessRole.value = document.business_role === 'offer' ? 'offer' : 'payment_request';
    documentRoleType.value = document.document_role_type || null;
    issueDate.value = (document.official_date || document.date).slice(0, 10);
    issueCity.value = isConsumerDocumentType(document.doc_type) ? document.issue_city || '' : document.issue_city
      || String(legalEntities.value.find((item) => item.id === selectedLegalEntityId.value)?.requisites.city || '').trim();
    replacesDocumentId.value = document.id;
    replacementProposalId.value = document.proposal_id || null;
    replacementTotalCents.value = document.snapshot_total_amount == null ? null : Math.round(Number(document.snapshot_total_amount) * 100);
    if (isConsumerDocumentType(document.doc_type) && document.consumer_terms) {
      ++consumerDefaultsRequestId;
      consumerDefaultsLoading.value = false;
      consumerDefaultsLoaded.value = true;
      consumerTerms.value = { ...createDefaultConsumerDocumentTerms(), ...document.consumer_terms };
      replacementConsumerBaseline.value = { ...consumerTerms.value };
      for (const field of consumerDefaultFields) manuallyEditedConsumerDefaultFields.add(field);
    }
    if (document.doc_type === 'contract_amendment' && document.amendment_terms) {
      amendmentTerms.value = JSON.parse(JSON.stringify(document.amendment_terms));
      amendmentBasisId.value = document.base_document_id || null;
    }
  };

  const downloadArtifact = async (artifactId: string, filename: string) => {
    let objectUrl: string | null = null;
    try {
      const access = await ManagerDocumentSystemService.getManagerDocumentArtifactAccess(artifactId);
      const downloadUrl = new URL(access.url, window.location.origin).toString();
      const parsedUrl = new URL(downloadUrl);
      const isManagerDownload = parsedUrl.origin === window.location.origin
        && parsedUrl.pathname.startsWith('/api/manager/document-system/artifacts/')
        && parsedUrl.pathname.endsWith('/download');
      if (isManagerDownload) {
        const apiPath = `${parsedUrl.pathname}${parsedUrl.search}`;
        const token = typeof OpenAPI.TOKEN === 'function'
          ? await OpenAPI.TOKEN({ method: 'GET', url: apiPath })
          : OpenAPI.TOKEN;
        const response = await fetch(downloadUrl, {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          credentials: OpenAPI.WITH_CREDENTIALS ? OpenAPI.CREDENTIALS : 'same-origin',
        });
        if (!response.ok) throw new Error(`Ошибка скачивания файла (${response.status})`);
        objectUrl = URL.createObjectURL(await response.blob());
        const link = document.createElement('a');
        link.href = objectUrl;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
      } else {
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = filename;
        link.rel = 'noopener noreferrer';
        document.body.appendChild(link);
        link.click();
        link.remove();
      }
    } catch (error) {
      input.notify(`Не удалось скачать файл: ${getApiErrorMessage(error)}`, 'error');
    } finally {
      if (objectUrl) window.setTimeout(() => URL.revokeObjectURL(objectUrl!), 60_000);
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
    amendmentTerms, amendmentBases, amendmentBasisId, selectedAmendmentBasis, loadAmendmentBases,
    actTerms,
    contractActPrompt,
    baseCustomerContractId,
    baseDocumentId,
    businessRole,
    documentRoleType,
    businessTerms,
    busy,
    consumerTerms,
    consumerProposalTotalCents,
    customerReadiness,
    checkDocumentReadiness,
    beginIssueAction,
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
    hasInstallationTwoStagesError: computed(() => Boolean(installationTwoStagesError.value)),
    loading,
    loadDocuments,
    loadWorkspace,
    loadTemplateVersions,
    activeTemplateVersionId: computed(() => templateVersions.value.find((item) => item.status === 'active')?.id || null),
    pdfRuntime,
    prepareReplacement,
    cancelReplacement,
    replacesDocumentId,
    requestVoid,
    resetConsumerTerms,
    resetBusinessTerms,
    resetActTerms,
    resetTransportTerms,
    selectedLegalEntityId,
    selectedGoodsWarrantyDefault,
    selectedTemplateId,
    receiptNote, warrantyEquipmentId,
    participantStatement,
    participantStatementConfirmations,
    repairDefect,
    templates,
    templatesLoading,
    templateVersionsLoading,
    templateLoadError,
    versionLoadError,
    loadTemplates,
    transportTerms,
    voidDocument,
    voidReason,
    voidTarget,
  };
};
