<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { DOCUMENT_ROLE_OPTIONS, EXTERNAL_CONTRACT_FILE_ACCEPT } from '../model/document-constants';
import { ManagerDocsService, type ManagerOrderDetailResponse, type ManagerOrderDocumentItem } from '../../../client';
import DocumentSendModal from '../../../components/orders/DocumentSendModal.vue';
import { getOrderDocumentAccess } from '../../../components/orders/order-document-access';
import { MANAGER_CAPABILITY, hasManagerCapability } from '../../../manager-capabilities';
import { managerSession } from '../../../services/manager-session';
import { useManagedDocumentWorkspace } from '../composables/use-managed-document-workspace';
import ConsumerDocumentTermsPanel from './ConsumerDocumentTermsPanel.vue';
import B2BContractTermsPanel from './B2BContractTermsPanel.vue';
import ContractScenarioChooser from './ContractScenarioChooser.vue';
import ExternalContractForm from './ExternalContractForm.vue';
import DocumentList from './DocumentList.vue';
import FacsimilePdfEditor from './FacsimilePdfEditor.vue';
import { canEditDocumentFacsimile } from '../model/facsimile-placement';
import { useDocumentFileActions } from '../composables/use-document-file-actions';
import ActTermsPanel from './ActTermsPanel.vue';
import TransportTermsPanel from './TransportTermsPanel.vue';
import GoogleDocumentEditorActions from './GoogleDocumentEditorActions.vue';
import { useGoogleDocumentEditor } from '../composables/use-google-document-editor';
import type { GoogleDocumentEditTarget } from '../integrations/google-document-editor-api';
import { isConsumerDocumentType } from '../model/consumer-document-terms';
import { proposalLineTotalCents } from '../model/installation-two-stages';
import { isBusinessTermsDocumentType } from '../model/business-document-terms';
import { contractScenarioForWorkflow, withContractScenario, type ContractScenario } from '../model/business-document-terms';
import { getCustomerDocumentWarnings } from '../model/customer-document-readiness';
import {
  BUSINESS_NATIVE_DOCUMENT_TYPES,
  CONSUMER_NATIVE_DOCUMENT_TYPES,
  documentTypeName,
  managedDocumentStatus,
  managedDocumentStatusClass,
  officialDocumentTitle,
} from '../model/native-document-options';

const props = defineProps<{
  order: ManagerOrderDetailResponse;
  workflowType?: string | null;
  activeProposalId?: number | null;
  beforeGenerate?: (type: string) => BeforeGenerateResult | Promise<BeforeGenerateResult>;
}>();
const emit = defineEmits<{
  refresh: [];
  toast: [payload: { message: string; type?: 'success' | 'error' }];
}>();

const formRef = ref<HTMLElement | null>(null);
const sendOpen = ref(false);
const facsimileTarget = ref<{ id: number; title: string } | null>(null);
watch(() => props.order.id, () => { facsimileTarget.value = null; });
watch(() => props.order.status, () => { if (!getOrderDocumentAccess(props.order.status).canCreate) facsimileTarget.value = null; });
const preparingDraft = ref(false);
type BeforeGenerateResult = boolean | void | { proceed?: boolean; mutated?: boolean };
type DocumentAudience = 'business' | 'consumer';
const documentAudience = ref<DocumentAudience>('business');
const proposalId = computed(() => {
  if (props.activeProposalId) return props.activeProposalId;
  return props.order.proposals?.find((item) => item.is_selected && !item.is_archived)?.id
    || props.order.proposals?.find((item) => !item.is_archived)?.id
    || null;
});
const activeProposal = computed(() => props.order.proposals?.find((item) => item.id === proposalId.value) || null);
const activeProposalTotalCents = computed(() => proposalLineTotalCents(activeProposal.value));
const access = computed(() => getOrderDocumentAccess(props.order.status));
const contractSource = ref<'ours' | 'customer'>('ours');
const orderDocuments = ref<ManagerOrderDocumentItem[]>([]);
watch(() => props.order.documents, (documents) => { orderDocuments.value = documents || []; }, { immediate: true });
const canManageDocumentSettings = computed(() => (
  hasManagerCapability(managerSession.auth.value, MANAGER_CAPABILITY.documentsManage)
));
const canSendNativeEmail = computed(() => managerSession.auth.value?.is_system_tenant === true);
const workspace = useManagedDocumentWorkspace({
  customerContext: () => props.order.customer,
  orderId: () => props.order.id,
  workflowType: () => props.workflowType || props.order.workflow_type,
  proposalId: () => proposalId.value,
  proposalTotalCents: () => activeProposalTotalCents.value,
  notify: (message, type = 'success') => emit('toast', { message, type }),
  refresh: () => emit('refresh'),
});
const facsimileSaved = async () => {
  facsimileTarget.value = null;
  await workspace.loadDocuments();
  emit('refresh');
  emit('toast', { message: 'PDF с подписью и печатью сохранён.', type: 'success' });
};
const registeringCustomerContract = computed(() => workspace.documentType.value === 'contract' && contractSource.value === 'customer');
const sendableDocuments = computed(() => workspace.documents.value.filter((document) => (
  ['issued', 'sent', 'signed'].includes(document.status)
)));
const nativeDocumentIds = computed(() => new Set(workspace.documents.value.map((document) => document.id)));
const otherContracts = computed(() => orderDocuments.value.filter((document) => (
  document.doc_type === 'contract' && !nativeDocumentIds.value.has(document.id)
)));
const loadOrderDocuments = async () => {
  const orderId = props.order.id;
  const response = await ManagerDocsService.getManagerOrderDocuments(orderId);
  if (props.order.id === orderId) orderDocuments.value = response.items;
};
const processingContractId = ref<number | null>(null);
const contractFileActions = useDocumentFileActions({
  orderId: () => props.order.id,
  access,
  fileInput: ref(null),
  isUploading: ref(false),
  processingDocumentId: processingContractId,
  loadDocuments: loadOrderDocuments,
  refresh: () => emit('refresh'),
  notify: (message, type = 'success') => emit('toast', { message, type }),
});
const draftCount = computed(() => workspace.documents.value.filter((document) => document.status === 'draft').length);
const documentTypes = computed(() => documentAudience.value === 'business'
  ? BUSINESS_NATIVE_DOCUMENT_TYPES : CONSUMER_NATIVE_DOCUMENT_TYPES);
const documentTypeIcon = (type: string) => ({
  offer: 'request_quote', invoice: 'receipt_long', contract: 'handshake', act: 'fact_check',
  tn2: 'local_shipping', ttn1: 'local_shipping',
  b2c_supply_installation_act: 'home_repair_service',
  b2c_customer_equipment_installation_act: 'build',
  b2c_maintenance_repair_act: 'handyman', b2c_route_laying_act: 'route',
}[type] || 'description');
const setContractScenario = (scenario: ContractScenario) => {
  workspace.businessTerms.value = withContractScenario(
    workspace.businessTerms.value, scenario, workspace.selectedGoodsWarrantyDefault.value,
  );
};
const googleEditor = useGoogleDocumentEditor({
  notify: (message, type = 'success') => emit('toast', { message, type }),
  onSynced: async (target, _result, isCurrent = () => true) => {
    if (target.kind !== 'managed-document' || !isCurrent()) return;
    workspace.participantStatementConfirmations.value[target.documentId] = false;
    await workspace.loadDocuments(isCurrent);
    if (!isCurrent()) return;
    emit('refresh');
  },
});

type BasisOption = {
  value: string;
  label: string;
  documentId: number | null;
  customerContractId: number | null;
  isContract: boolean;
};
const formatDate = (value: string | null | undefined) => value
  ? new Date(value.length === 10 ? `${value}T00:00:00` : value).toLocaleDateString('ru-RU')
  : '—';
const selectedBasisValue = ref('');
const registeredBasisValue = ref('');
const basisRequired = computed(() => ['act', 'tn2', 'ttn1'].includes(workspace.documentType.value));
const basisSupported = computed(() => basisRequired.value || workspace.documentType.value === 'invoice');
const partyRolesSupported = computed(() => ['contract', 'invoice', 'act', 'offer'].includes(workspace.documentType.value));
const isConsumerDocument = computed(() => isConsumerDocumentType(workspace.documentType.value));
const isBusinessTermsDocument = computed(() => isBusinessTermsDocumentType(workspace.documentType.value));
const customerIsConsumer = computed(() => props.order.customer?.type === 'individual');
const customerTypeLabel = computed(() => {
  if (props.order.customer?.type === 'company') return 'юрлицо';
  if (props.order.customer?.type === 'individual_entrepreneur') return 'ИП';
  return 'физлицо';
});
const customerWarnings = computed(() => ['contract', 'invoice', 'act'].includes(workspace.documentType.value)
  ? (workspace.customerReadiness.value?.missing_fields || []).map((item) => item.label)
  : getCustomerDocumentWarnings(props.order.customer, workspace.documentType.value));
const incompleteDraft = (document: Parameters<typeof workspace.issue>[0]) => document.status === 'draft'
  && document.customer_readiness?.can_issue === false;
const criticalMissingLabels = (document: Parameters<typeof workspace.issue>[0]) => (document.customer_readiness?.missing_fields || [])
  .filter((item) => item.critical).map((item) => item.label).join(', ');
const audienceMismatchWarning = computed(() => (
  isConsumerDocument.value && !customerIsConsumer.value
    ? `Карточка клиента отмечена как ${customerTypeLabel.value}. Заказ-акт для физлица лучше не выпускать до проверки типа клиента.`
    : ''
));
const basisOptions = computed<BasisOption[]>(() => {
  const result: BasisOption[] = [];
  const contract = props.order.customer_contract;
  if (contract?.status === 'active') {
    result.push({
      value: `customer-contract:${contract.id}`,
      label: `Договор № ${contract.number} от ${formatDate(contract.valid_from)}`,
      documentId: null,
      customerContractId: contract.id,
      isContract: true,
    });
  }

  const nativeBases = workspace.documents.value
    .filter((item) => ['issued', 'sent', 'signed'].includes(item.status))
    .filter((item) => item.doc_type === 'contract' || item.doc_type === 'offer' || (item.doc_type === 'invoice' && item.business_role === 'offer'));
  for (const document of nativeBases) {
    result.push({
      value: `document:${document.id}`,
      label: `${officialDocumentTitle(document)} от ${formatDate(document.official_date || document.date)}`,
      documentId: document.id,
      customerContractId: null,
      isContract: document.doc_type === 'contract',
    });
  }
  for (const document of orderDocuments.value) {
    if (nativeDocumentIds.value.has(document.id) || !['contract', 'offer'].includes(document.doc_type)) continue;
    result.push({
      value: `document:${document.id}`,
      label: `${documentTypeName(document.doc_type)} № ${document.number} от ${formatDate(document.date)}`,
      documentId: document.id,
      customerContractId: null,
      isContract: document.doc_type === 'contract',
    });
  }
  const priority = (item: BasisOption) => item.customerContractId ? 0 : item.isContract ? 1 : 2;
  // Order document IDs follow registration order, including customer-prepared contracts.
  return result.sort((a, b) => priority(a) - priority(b) || (
    a.isContract && !a.customerContractId ? (b.documentId || 0) - (a.documentId || 0) : 0
  ));
});

const syncBasis = () => {
  if (!basisSupported.value) {
    selectedBasisValue.value = '';
    workspace.baseDocumentId.value = null;
    workspace.baseCustomerContractId.value = null;
    return;
  }
  if (!basisOptions.value.some((item) => item.value === selectedBasisValue.value)) {
    selectedBasisValue.value = basisOptions.value.find((item) => item.value === registeredBasisValue.value)?.value
      || basisOptions.value[0]?.value || '';
  }
  const selected = basisOptions.value.find((item) => item.value === selectedBasisValue.value);
  workspace.baseDocumentId.value = selected?.documentId || null;
  workspace.baseCustomerContractId.value = selected?.customerContractId || null;
};

watch([basisSupported, basisOptions, selectedBasisValue], syncBasis, { immediate: true });
watch(workspace.documentType, (type) => {
  documentAudience.value = isConsumerDocumentType(type) ? 'consumer' : 'business';
});

const setAudience = (audience: DocumentAudience) => {
  documentAudience.value = audience;
  workspace.documentType.value = audience === 'consumer'
    ? CONSUMER_NATIVE_DOCUMENT_TYPES[0].value
    : BUSINESS_NATIVE_DOCUMENT_TYPES[0].value;
};

watch(() => props.order.id, () => {
  contractSource.value = 'ours';
  selectedBasisValue.value = '';
  registeredBasisValue.value = '';
  const audience: DocumentAudience = customerIsConsumer.value ? 'consumer' : 'business';
  documentAudience.value = audience;
  workspace.documentType.value = audience === 'consumer'
    ? CONSUMER_NATIVE_DOCUMENT_TYPES[0].value
    : 'offer';
  void workspace.loadWorkspace();
}, { immediate: true });
const onExternalContractRegistered = (document: ManagerOrderDocumentItem) => {
  orderDocuments.value = [...orderDocuments.value.filter((item) => item.id !== document.id), document];
  registeredBasisValue.value = `document:${document.id}`;
  contractSource.value = 'ours';
  emit('refresh');
};
watch(() => props.workflowType, (next, previous) => {
  if (!previous || !next || next === previous) return;
  if (workspace.businessTerms.value.contract_scenario === contractScenarioForWorkflow(previous)) {
    setContractScenario(contractScenarioForWorkflow(next));
  }
  const roleFor = (workflow: string) => workflow === 'sales_installation' ? 'seller_buyer' : 'executor_customer';
  if (workspace.documentRoleType.value === roleFor(previous)) {
    workspace.documentRoleType.value = roleFor(next);
  }
});

const openCustomerProfile = () => {
  if (!props.order.customer?.id) return;
  const returnTo = `${window.location.pathname}${window.location.search}`;
  window.history.pushState({}, '', `/manager/customers/profile?customerId=${props.order.customer.id}&returnTo=${encodeURIComponent(returnTo)}`);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

const openSettings = () => {
  if (!canManageDocumentSettings.value) return;
  window.history.pushState({}, '', '/manager/settings/documents');
  window.dispatchEvent(new PopStateEvent('popstate'));
};
const prepareReplacement = (document: Parameters<typeof workspace.prepareReplacement>[0]) => {
  workspace.prepareReplacement(document);
  selectedBasisValue.value = document.base_document_id
    ? `document:${document.base_document_id}`
    : document.base_customer_contract_id
      ? `customer-contract:${document.base_customer_contract_id}`
      : '';
  syncBasis();
  requestAnimationFrame(() => formRef.value?.scrollIntoView({ behavior: 'smooth', block: 'center' }));
};
const artifactName = (kind: string) => ({
  pdf: 'PDF', rendered_docx: 'DOCX', source_docx: 'Исходный DOCX', signed_pdf: 'PDF с подписью и печатью',
}[kind] || kind);
const googleTarget = (documentId: number): GoogleDocumentEditTarget => ({
  kind: 'managed-document',
  documentId,
});
const loadGoogleDocumentSessions = () => {
  if (!googleEditor.connected.value) return;
  for (const document of workspace.documents.value) {
    if (document.status === 'draft') void googleEditor.loadSession(googleTarget(document.id));
  }
};
watch([googleEditor.connected, workspace.documents], ([connected]) => {
  if (connected) loadGoogleDocumentSessions();
});
const syncGoogleDocument = async (documentId: number) => {
  await googleEditor.sync(googleTarget(documentId));
};
const googleDraftBusy = (documentId: number) => {
  const target = googleTarget(documentId);
  const session = googleEditor.getSession(target);
  return googleEditor.isBusy(target) || session?.status === 'syncing';
};
const issueDocument = async (document: Parameters<typeof workspace.issue>[0]) => {
  const action = workspace.beginIssueAction(document);
  if (!await workspace.checkDocumentReadiness(document, action) || !action.canIssue()) return;
  const target = googleTarget(document.id);
  if (googleEditor.connected.value) {
    await googleEditor.loadSession(target);
    if (!action.canIssue()) return;
    const session = googleEditor.getSession(target);
    if (session?.status === 'changed' && session.can_edit) {
      const synced = await googleEditor.sync(target, action.isCurrent);
      if (!synced || !action.canIssue()) return;
      if (document.doc_type === 'participant_statement') {
        workspace.participantStatementConfirmations.value[document.id] = false;
        emit('toast', { message: 'Текст заявления обновлён из Google Docs. Проверьте предпросмотр и подтвердите актуальные факты перед выпуском.', type: 'success' });
        return;
      }
    } else if (session && session.status !== 'ready') {
      emit('toast', {
        message: 'Черновик ещё не синхронизирован с Google Docs',
        type: 'error',
      });
      return;
    }
  }
  await workspace.issue(document, action);
};
const handleEmailSent = async () => {
  await workspace.loadDocuments();
  emit('refresh');
  emit('toast', { message: 'Письмо с документами отправлено', type: 'success' });
};

const createDraft = async (allowIncomplete = false) => {
  if (preparingDraft.value || workspace.busy.value || workspace.draftBlockedReason.value) return;
  preparingDraft.value = true;
  try {
    const result = await props.beforeGenerate?.(workspace.documentType.value);
    if (result === false || (result && typeof result === 'object' && result.proceed === false)) {
      emit('toast', { message: 'Сначала сохраните изменения заказа перед созданием черновика.', type: 'error' });
      return;
    }
    // The save callback may replace the order in the parent; let its new props reach this workspace.
    await nextTick();
    await workspace.createDraft(allowIncomplete);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Не удалось сохранить изменения заказа.';
    emit('toast', { message, type: 'error' });
  } finally {
    preparingDraft.value = false;
  }
};
defineExpose({
  openCreate: () => formRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
  openSend: () => { if (access.value.canSend && canSendNativeEmail.value) sendOpen.value = true; },
});
</script>

<template>
  <section class="rounded-2xl border border-brand-200 bg-white p-4 shadow-sm dark:border-brand-900/70 dark:bg-slate-900/60 sm:p-5" data-testid="native-documents-workspace">
    <DocumentSendModal
      v-model="sendOpen"
      transport="native"
      :order="order"
      :documents="sendableDocuments"
      @sent="handleEmailSent"
    />
    <div class="flex flex-col gap-3 border-b border-slate-100 pb-4 dark:border-slate-800 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <div class="flex flex-wrap items-center gap-2">
          <h3 class="font-['Space_Grotesk'] text-lg font-bold text-slate-900 dark:text-white">Документы CRM</h3>
          <span class="rounded-full bg-brand-100 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-brand-800 dark:bg-brand-950/60 dark:text-brand-300">DOCX + PDF</span>
        </div>
        <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">Выберите тип → создайте черновик → проверьте PDF → выпустите документ → отправьте клиенту.</p>
        <p v-if="googleEditor.connectionState.value === 'connected'" class="mt-1 text-xs font-semibold text-emerald-700 dark:text-emerald-300" data-testid="document-google-connected">
          Google подключён<span v-if="googleEditor.accountLabel.value">: {{ googleEditor.accountLabel.value }}</span>. Черновики можно править онлайн; изменения сохраняются в CRM после возвращения во вкладку.
        </p>
        <p v-else-if="googleEditor.connectionState.value === 'disconnected'" class="mt-1 text-xs text-slate-500" data-testid="document-google-disconnected">
          <template v-if="googleEditor.canConnect.value">Для онлайн-редактирования <button class="font-semibold text-brand-700 underline underline-offset-2" type="button" @click="googleEditor.connect">подключите Google</button>.</template>
          <template v-else>Для онлайн-редактирования обратитесь к владельцу аккаунта.</template>
        </p>
      </div>
    </div>

    <div v-if="workspace.loading.value" class="flex items-center justify-center gap-2 py-10 text-sm text-slate-500">
      <span class="material-icons-round animate-spin text-[20px]">progress_activity</span>Загружаем документный контур…
    </div>

    <template v-else>
      <div v-if="workspace.issueBlockedReason.value && !registeringCustomerContract" class="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900" data-testid="pdf-runtime-warning">
        <strong>Выпуск временно недоступен:</strong> {{ workspace.issueBlockedReason.value }}. Черновики создавать можно; официальный номер не будет занят до успешного выпуска.
      </div>
      <p v-if="sendableDocuments.length && !canSendNativeEmail" class="mt-4 text-xs text-slate-500" data-testid="native-email-unavailable">
        Отправка из CRM появится после подключения почты вашей организации. PDF уже можно скачать и отправить вручную.
      </p>

      <h4 v-if="workspace.documents.value.length" class="mt-5 text-sm font-bold text-slate-800 dark:text-white">{{ draftCount ? 'Проверьте черновик и выпустите' : 'Готовые документы' }}</h4>
      <div class="mt-3 space-y-3">
        <article v-for="document in workspace.documents.value" :key="document.id" class="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <h4 class="font-bold text-slate-900 dark:text-white">{{ document.status === 'draft' ? `${documentTypeName(document.doc_type)} · номер ещё не присвоен` : officialDocumentTitle(document) }}</h4>
                <span class="rounded-full px-2 py-0.5 text-[11px] font-bold" :class="managedDocumentStatusClass(document.status)">{{ managedDocumentStatus(document.status) }}</span>
                <span v-if="incompleteDraft(document)" class="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-bold text-amber-900" data-testid="incomplete-native-draft">Не заполнены поля</span>
                <span v-if="document.business_role === 'offer'" class="rounded-full bg-violet-100 px-2 py-0.5 text-[11px] font-bold text-violet-800">Счёт-оферта</span>
              </div>
              <p class="mt-1 text-xs text-slate-500">от {{ formatDate(document.official_date || document.date) }} · CRM: <span class="font-mono">{{ document.internal_reference || `#${document.id}` }}</span></p>
              <div v-if="incompleteDraft(document)" class="mt-2 text-xs text-amber-800" data-testid="native-draft-missing-fields">
                <p>Не заполнены поля клиента: {{ criticalMissingLabels(document) }}.</p>
                <p>Заполните карточку и создайте новый черновик. Данные этого черновика сохранятся.</p>
                <button type="button" class="mt-1 font-semibold underline" @click="openCustomerProfile">Заполнить карточку</button>
              </div>
              <p v-if="document.replaces_document_id" class="mt-1 text-xs font-semibold text-blue-600">Заменяет CRM-документ #{{ document.replaces_document_id }}</p>
              <p v-if="document.void_reason" class="mt-1 text-xs text-rose-600">Причина: {{ document.void_reason }}</p>
            </div>

            <div class="flex flex-wrap gap-2 sm:justify-end">
              <label v-if="document.status === 'draft' && document.doc_type === 'participant_statement'" class="flex w-full items-start gap-2 text-sm text-slate-700 dark:text-slate-200">
                <input v-model="workspace.participantStatementConfirmations.value[document.id]" type="checkbox" :data-testid="`participant-statement-confirm-${document.id}`" />
                <span>Проверил(а) текущий текст заявления, достоверность фактов и требования этой закупки.</span>
              </label>
              <button v-if="document.status === 'draft'" class="native-action" type="button" :disabled="workspace.busy.value || googleDraftBusy(document.id) || Boolean(workspace.issueBlockedReason.value)" @click="workspace.previewDraft(document)">
                <span class="material-icons-round text-[17px]">visibility</span>Предпросмотр
              </button>
              <button v-for="artifact in document.artifacts" :key="artifact.id" class="native-action" type="button" @click="workspace.downloadArtifact(artifact.id, artifact.filename)">
                <span class="material-icons-round text-[17px]">download</span>{{ artifactName(artifact.kind) }}
              </button>
              <button v-if="access.canCreate && canEditDocumentFacsimile(document)" class="native-action" type="button" :disabled="workspace.busy.value" @click="facsimileTarget = { id: document.id, title: officialDocumentTitle(document) }">
                <span class="material-icons-round text-[17px]">draw</span>{{ document.artifacts?.some((item) => item.kind === 'signed_pdf') ? 'Изменить размещение' : 'Подготовить PDF с подписью и печатью' }}
              </button>
              <GoogleDocumentEditorActions
                v-if="document.status === 'draft' && access.canCreate && googleEditor.connected.value"
                :session="googleEditor.getSession(googleTarget(document.id))"
                :busy="googleEditor.isBusy(googleTarget(document.id))"
                @open="googleEditor.open(googleTarget(document.id))"
                @sync="syncGoogleDocument(document.id)"
              />
              <button v-if="document.status === 'draft' && access.canCreate" class="native-action-primary" type="button" :disabled="workspace.busy.value || googleDraftBusy(document.id) || Boolean(workspace.issueBlockedReason.value) || incompleteDraft(document) || (document.doc_type === 'participant_statement' && !workspace.participantStatementConfirmations.value[document.id])" :title="incompleteDraft(document) ? `Не заполнены поля: ${criticalMissingLabels(document)}` : workspace.issueBlockedReason.value" @click="issueDocument(document)">Выпустить</button>
              <button v-if="document.status === 'draft' && !document.maintenance_source_order_id && !document.official_number && !document.artifacts?.length && access.canCreate" class="native-action-danger" type="button" :disabled="workspace.busy.value || googleDraftBusy(document.id)" @click="workspace.deleteDraft(document)">Удалить черновик</button>
              <button v-if="['issued', 'sent', 'signed'].includes(document.status) && !document.maintenance_source_order_id && access.canReplace" class="native-action" type="button" @click="prepareReplacement(document)">Создать исправленную редакцию</button>
              <a v-if="document.maintenance_source_order_id" :href="`/manager/orders/kanban?orderId=${document.maintenance_source_order_id}`" target="_blank" rel="noopener" class="native-action">Исходное ТО #{{ document.maintenance_source_order_id }} · замечания и новые версии</a>
              <button v-if="['issued', 'sent', 'signed'].includes(document.status) && access.canReplace" class="native-action-danger" type="button" @click="workspace.requestVoid(document)">Аннулировать</button>
            </div>
          </div>

          <form v-if="workspace.voidTarget.value?.id === document.id" class="mt-3 flex flex-col gap-2 rounded-lg bg-rose-50 p-3 sm:flex-row sm:items-end" @submit.prevent="workspace.voidDocument">
            <label class="native-field flex-1"><span>Причина аннулирования</span><input v-model="workspace.voidReason.value" class="native-input" placeholder="Ошибка в реквизитах" /></label>
            <button class="native-action-danger h-10" type="submit" :disabled="workspace.busy.value || !workspace.voidReason.value.trim()">Подтвердить</button>
            <button class="native-action h-10" type="button" @click="workspace.voidTarget.value = null">Отмена</button>
          </form>
          <p v-if="document.status === 'void'" class="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400">
            Аннулированный номер и сформированные файлы сохранены в истории. Повторно этот номер не используется.
          </p>
        </article>

        <div v-if="!workspace.documents.value.length" class="rounded-xl border border-dashed border-slate-300 p-8 text-center dark:border-slate-700">
          <span class="material-icons-round text-4xl text-slate-300">description</span>
          <p class="mt-2 text-sm font-semibold text-slate-600 dark:text-slate-300">Внутренних документов пока нет</p>
          <p class="mt-1 text-xs text-slate-500">Начните с коммерческого предложения или счёта. Договор можно выбрать отдельно.</p>
        </div>
      </div>
      <div v-if="access.canSend && canSendNativeEmail" class="mt-4 flex justify-end border-t border-slate-100 pt-4 dark:border-slate-800">
        <button class="inline-flex h-10 items-center gap-2 rounded-xl bg-brand-600 px-5 text-sm font-bold text-white hover:bg-brand-700" type="button" data-testid="native-document-email" @click="sendOpen = true"><span class="material-icons-round text-[18px]">send</span>{{ sendableDocuments.length ? 'Отправить письмо с документом' : 'Отправить письмо' }}</button>
      </div>
      <div v-if="otherContracts.length" class="mt-5" data-testid="saved-order-contracts">
        <DocumentList
          title="Сохранённые договоры"
          :documents="otherContracts"
          :can-create="false"
          :can-replace="access.canReplace"
          :can-delete="access.canDelete"
          :access-summary="access.summary"
          :processing-document-id="processingContractId"
          :file-accept="EXTERNAL_CONTRACT_FILE_ACCEPT"
          @download="contractFileActions.downloadDocument"
          @attach="contractFileActions.handleAttachDocumentFile"
          @delete="contractFileActions.deleteDocument"
        />
      </div>

      <div v-if="!workspace.legalEntities.value.length && !registeringCustomerContract" class="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        <strong>Нужно один раз заполнить реквизиты.</strong>
        <button v-if="canManageDocumentSettings" class="ml-2 underline underline-offset-2" type="button" @click="openSettings">Открыть настройки</button>
        <span v-else class="ml-1">Обратитесь к владельцу аккаунта.</span>
      </div>

      <div v-if="access.canCreate" ref="formRef" class="mt-4 rounded-xl bg-slate-50 p-4 dark:bg-slate-800/60">
        <div v-if="workspace.replacesDocumentId.value" class="mb-4 flex items-center justify-between gap-3 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-900">
          <span>Готовим замену для документа CRM #{{ workspace.replacesDocumentId.value }}</span>
          <button class="font-bold" type="button" @click="workspace.replacesDocumentId.value = null">Отменить</button>
        </div>

        <div class="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div class="inline-flex w-fit rounded-xl border border-slate-200 bg-white p-1 dark:border-slate-700 dark:bg-slate-900" data-testid="native-document-audience-toggle">
            <button type="button" class="rounded-lg px-3 py-1.5 text-sm font-semibold transition" :class="documentAudience === 'business' ? 'bg-brand-600 text-white' : 'text-slate-600 dark:text-slate-300'" data-testid="native-audience-business" @click="setAudience('business')">Для организаций и ИП</button>
            <button type="button" class="rounded-lg px-3 py-1.5 text-sm font-semibold transition" :class="documentAudience === 'consumer' ? 'bg-brand-600 text-white' : 'text-slate-600 dark:text-slate-300'" data-testid="native-audience-consumer" @click="setAudience('consumer')">Для физлиц</button>
          </div>
          <span class="text-xs font-semibold text-slate-500">В карточке клиента: {{ customerTypeLabel }}</span>
        </div>

        <div class="flex items-center justify-between gap-3">
          <h4 class="text-sm font-bold text-slate-800 dark:text-white">Выберите документ</h4>
          <details class="relative" data-testid="native-document-more">
            <summary class="flex h-9 w-9 cursor-pointer list-none items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 hover:text-brand-700 dark:border-slate-700 dark:bg-slate-900" aria-label="Дополнительные настройки документов"><span class="material-icons-round">more_horiz</span></summary>
            <div class="absolute right-0 z-20 mt-1 w-64 rounded-xl border border-slate-200 bg-white p-3 shadow-lg dark:border-slate-700 dark:bg-slate-900">
              <label class="native-field"><span>Наше юрлицо</span><select v-model="workspace.selectedLegalEntityId.value" class="native-input" data-testid="native-legal-entity"><option v-for="entity in workspace.legalEntities.value" :key="entity.id" :value="entity.id">{{ entity.display_name }}</option></select></label>
              <button v-if="canManageDocumentSettings" class="mt-3 text-xs font-semibold text-brand-700 underline" type="button" @click="openSettings">Юрлица и шаблоны</button>
            </div>
          </details>
        </div>
        <div class="mt-3 flex gap-2 overflow-x-auto pb-2" data-testid="native-document-type">
          <button v-for="type in documentTypes" :key="type.value" type="button" class="flex min-h-20 min-w-28 max-w-36 flex-1 flex-col items-center justify-center gap-1 rounded-xl border px-2 py-2 text-center text-xs font-bold transition" :class="workspace.documentType.value === type.value ? 'border-brand-600 bg-brand-600 text-white' : 'border-slate-200 bg-white text-slate-700 hover:border-brand-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200'" :aria-pressed="workspace.documentType.value === type.value" :data-testid="`native-document-type-${type.value}`" @click="workspace.documentType.value = type.value">
            <span class="material-icons-round text-[23px]">{{ documentTypeIcon(type.value) }}</span>{{ type.label }}
          </button>
        </div>
        <button v-if="registeringCustomerContract" type="button" class="mt-3 text-xs font-semibold text-brand-700 hover:underline dark:text-brand-300" data-testid="cancel-external-contract" @click="contractSource = 'ours'">← К нашему договору</button>
        <button v-else-if="workspace.documentType.value === 'contract' && !workspace.legalEntities.value.length" type="button" class="mt-3 text-xs font-semibold text-brand-700 hover:underline" data-testid="attach-customer-contract" @click="contractSource = 'customer'">Прикрепить договор</button>
        <ExternalContractForm
          v-if="registeringCustomerContract"
          :key="order.id"
          :order-id="order.id"
          :can-create="access.canCreate"
          :access-summary="access.summary"
          @registered="onExternalContractRegistered"
          @toast="emit('toast', $event)"
        />
        <template v-else-if="workspace.legalEntities.value.length">
          <ContractScenarioChooser v-if="workspace.documentType.value === 'contract'" :model-value="workspace.businessTerms.value.contract_scenario" @update:model-value="setContractScenario" @attach-contract="contractSource = 'customer'" />
          <details class="mt-3 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900" data-testid="native-document-options">
            <summary class="cursor-pointer text-sm font-semibold text-slate-700 dark:text-slate-200">Шаблон и реквизиты <span class="font-normal text-slate-500">· {{ workspace.templates.value.find((item) => item.id === workspace.selectedTemplateId.value)?.name || (workspace.documentType.value === 'participant_statement' ? 'Начальная редактируемая форма' : 'не выбран') }}</span></summary>
            <div class="mt-3 grid gap-3 sm:grid-cols-3">
              <label class="native-field"><span>Шаблон</span><select v-model="workspace.selectedTemplateId.value" class="native-input" data-testid="native-document-template"><option v-if="workspace.documentType.value === 'participant_statement' && !workspace.templates.value.length" :value="null">Начальная редактируемая форма</option><option v-for="template in workspace.templates.value" :key="template.id" :value="template.id">{{ template.name }}</option></select></label>
              <label class="native-field"><span>Дата документа</span><input v-model="workspace.issueDate.value" class="native-input" data-testid="native-document-issue-date" type="date" /></label>
              <label class="native-field"><span>Город документа</span><input v-model="workspace.issueCity.value" class="native-input" data-testid="native-document-issue-city" placeholder="Витебск" /></label>
            </div>
          </details>

          <div v-if="customerWarnings.length || audienceMismatchWarning" class="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900" data-testid="native-customer-readiness-warning">
            <p v-if="audienceMismatchWarning">{{ audienceMismatchWarning }}</p>
            <p v-if="customerWarnings.length">Не заполнены поля для выбранного документа: {{ customerWarnings.join(', ') }}.</p>
            <div class="mt-2 flex flex-wrap gap-3">
              <button class="font-semibold underline underline-offset-2" type="button" @click="openCustomerProfile">Заполнить карточку</button>
              <button v-if="workspace.customerReadiness.value?.can_issue === false" class="native-action" type="button" data-testid="create-incomplete-native-draft" :disabled="preparingDraft || workspace.busy.value" @click="createDraft(true)">Создать черновик с пустыми полями</button>
            </div>
            <p v-if="workspace.customerReadiness.value?.can_issue === false" class="mt-2 text-xs">В черновике будут линии для заполнения и пометка на страницах. Для выпуска заполните карточку и создайте новый черновик.</p>
          </div>

          <label v-if="basisSupported" class="native-field mt-4">
            <span>Документ-основание</span>
            <select v-model="selectedBasisValue" class="native-input" data-testid="native-document-basis">
              <option value="" :disabled="basisRequired">{{ basisRequired ? 'Выберите договор, счёт-оферту или КП' : 'Автоматически' }}</option>
              <option v-for="basis in basisOptions" :key="basis.value" :value="basis.value">{{ basis.label }}</option>
            </select>
            <span class="font-normal text-slate-500">Первым предлагается договор. Обычный счёт на оплату основанием не считается.</span>
          </label>

          <label v-if="partyRolesSupported" class="native-field mt-4">
            <span>Названия сторон</span>
            <select v-model="workspace.documentRoleType.value" class="native-input" data-testid="native-document-party-roles">
              <option :value="null">{{ ['act', 'invoice'].includes(workspace.documentType.value) ? 'Как в договоре (по умолчанию)' : 'По шаблону / настройкам заказа' }}</option>
              <option v-for="option in DOCUMENT_ROLE_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
            <span class="font-normal text-slate-500">Названия заменяются во всём документе с сохранением падежей. Для акта и счёта берутся из выбранного основания; без него — из настроек заказа или шаблона.</span>
          </label>

          <div v-if="workspace.documentType.value === 'invoice'" class="mt-4">
            <span class="text-xs font-bold text-slate-500">Роль счёта</span>
            <div class="mt-1.5 inline-flex rounded-xl border border-slate-200 bg-white p-1 dark:border-slate-700 dark:bg-slate-900" data-testid="invoice-role-toggle">
              <button type="button" class="rounded-lg px-3 py-1.5 text-sm font-semibold transition" :class="workspace.businessRole.value === 'payment_request' ? 'bg-brand-600 text-white' : 'text-slate-600 dark:text-slate-300'" @click="workspace.businessRole.value = 'payment_request'">Документ для оплаты</button>
              <button type="button" class="rounded-lg px-3 py-1.5 text-sm font-semibold transition" :class="workspace.businessRole.value === 'offer' ? 'bg-brand-600 text-white' : 'text-slate-600 dark:text-slate-300'" @click="workspace.businessRole.value = 'offer'">Счёт-оферта</button>
            </div>
            <p class="mt-1.5 text-xs text-slate-500">{{ workspace.businessRole.value === 'payment_request' ? 'После появления договора закрывающие документы будут ссылаться на договор.' : 'Оферта может сама стать основанием сделки.' }}</p>
          </div>
          <div v-if="workspace.documentType.value === 'participant_statement'" class="mt-4 space-y-3" data-testid="participant-statement-fields">
            <p class="text-sm text-slate-600 dark:text-slate-300">Сверьте форму с требованиями конкретной закупки. Укажите только проверенные факты; сведения о задолженности, судимости и другие заверения автоматически не добавляются.</p>
            <div class="grid gap-3 sm:grid-cols-2">
              <label class="native-field"><span>Процедура: номер / ссылка</span><input v-model="workspace.participantStatement.value.procedure_reference" class="native-input" maxlength="1000" data-testid="participant-statement-procedure" /></label>
              <label class="native-field"><span>Лот</span><input v-model="workspace.participantStatement.value.lot" class="native-input" maxlength="500" data-testid="participant-statement-lot" placeholder="Номер / наименование или «Все лоты»" /></label>
            </div>
            <label class="native-field"><span>Заказчик закупки</span><input v-model="workspace.participantStatement.value.buyer_name" class="native-input" maxlength="500" data-testid="participant-statement-buyer" /></label>
            <label class="native-field"><span>Текст заявления о соответствии</span><textarea v-model="workspace.participantStatement.value.declaration_text" class="native-input participant-statement-text" rows="8" maxlength="20000" data-testid="participant-statement-text" placeholder="Введите подтверждаемые сведения согласно требованиям закупки" /></label>
            <p class="text-xs text-slate-500">Участник и подписант берутся из выбранного нашего юрлица или ИП. Дата — в реквизитах выше. После создания черновика проверьте предпросмотр; текст можно отредактировать до выпуска.</p>
          </div>
          <ConsumerDocumentTermsPanel
            v-if="isConsumerDocument"
            :document-type="workspace.documentType.value"
            :terms="workspace.consumerTerms.value"
            :proposal-total-cents="activeProposalTotalCents"
            @update-terms="workspace.updateConsumerTerms"
          />
          <B2BContractTermsPanel
            v-if="isBusinessTermsDocument"
            :document-type="workspace.documentType.value"
            :terms="workspace.businessTerms.value"
            :order-conditions="order.additional_conditions"
            @update-terms="workspace.businessTerms.value = $event"
          />
          <ActTermsPanel
            v-if="workspace.documentType.value === 'act'"
            :terms="workspace.actTerms.value"
            @update-terms="workspace.actTerms.value = $event"
          />
          <TransportTermsPanel
            v-if="['tn2', 'ttn1'].includes(workspace.documentType.value)"
            :document-type="workspace.documentType.value"
            :terms="workspace.transportTerms.value"
            @update-terms="workspace.transportTerms.value = $event"
          />
          <p v-if="workspace.draftBlockedReason.value && !workspace.hasInstallationTwoStagesError.value" class="mt-3 text-xs font-semibold text-amber-700 dark:text-amber-300" data-testid="native-draft-blocked-reason">{{ workspace.draftBlockedReason.value }}. <button v-if="canManageDocumentSettings" class="underline" type="button" @click="openSettings">Исправить в настройках</button></p>
          <div class="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-4 dark:border-slate-700">
            <span class="text-xs text-slate-500">Черновик можно проверить до присвоения номера.</span>
            <button class="inline-flex h-10 items-center justify-center rounded-xl bg-brand-600 px-5 text-sm font-bold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50" type="button" data-testid="create-native-draft" data-order-usage="document_create" :disabled="preparingDraft || workspace.busy.value || Boolean(workspace.draftBlockedReason.value)" :title="workspace.draftBlockedReason.value" @click="createDraft(false)">Создать черновик</button>
          </div>
        </template>
      </div>

      <p v-else-if="!access.canCreate" class="mt-4 rounded-xl bg-slate-50 p-3 text-sm text-slate-500 dark:bg-slate-800">{{ access.summary }}</p>

    </template>
    <FacsimilePdfEditor v-if="facsimileTarget" :document-id="facsimileTarget.id" :title="facsimileTarget.title" @close="facsimileTarget = null" @saved="facsimileSaved" />
  </section>
</template>

<style scoped>
.native-field { @apply flex min-w-0 flex-col gap-1.5 text-xs font-semibold text-slate-600 dark:text-slate-300; }
.native-input { @apply h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-normal text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/15 dark:border-slate-700 dark:bg-slate-900 dark:text-white; }
.participant-statement-text { height: auto; min-height: 10rem; padding-top: 0.5rem; padding-bottom: 0.5rem; }
.native-action { @apply inline-flex h-9 items-center justify-center gap-1 rounded-lg border border-slate-200 px-3 text-xs font-semibold text-slate-600 hover:border-brand-400 hover:text-brand-700 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300; }
.native-action-primary { @apply inline-flex h-9 items-center justify-center rounded-lg bg-brand-600 px-3 text-xs font-bold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50; }
.native-action-danger { @apply inline-flex h-9 items-center justify-center rounded-lg border border-rose-200 px-3 text-xs font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-50; }
</style>
