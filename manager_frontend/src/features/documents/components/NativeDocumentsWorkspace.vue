<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { ManagerOrderDetailResponse } from '../../../client';
import { getOrderDocumentAccess } from '../../../components/orders/order-document-access';
import { MANAGER_CAPABILITY, hasManagerCapability } from '../../../manager-capabilities';
import { managerSession } from '../../../services/manager-session';
import { useManagedDocumentWorkspace } from '../composables/use-managed-document-workspace';
import ConsumerDocumentTermsPanel from './ConsumerDocumentTermsPanel.vue';
import B2BContractTermsPanel from './B2BContractTermsPanel.vue';
import ActTermsPanel from './ActTermsPanel.vue';
import { isConsumerDocumentType } from '../model/consumer-document-terms';
import { isBusinessTermsDocumentType } from '../model/business-document-terms';
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
  activeProposalId?: number | null;
}>();
const emit = defineEmits<{
  refresh: [];
  toast: [payload: { message: string; type?: 'success' | 'error' }];
}>();

const formRef = ref<HTMLElement | null>(null);
const proposalId = computed(() => {
  if (props.activeProposalId) return props.activeProposalId;
  return props.order.proposals?.find((item) => item.is_selected && !item.is_archived)?.id
    || props.order.proposals?.find((item) => !item.is_archived)?.id
    || null;
});
const access = computed(() => getOrderDocumentAccess(props.order.status));
const canManageDocumentSettings = computed(() => (
  hasManagerCapability(managerSession.auth.value, MANAGER_CAPABILITY.documentsManage)
));
const workspace = useManagedDocumentWorkspace({
  orderId: () => props.order.id,
  proposalId: () => proposalId.value,
  notify: (message, type = 'success') => emit('toast', { message, type }),
  refresh: () => emit('refresh'),
});

type BasisOption = {
  value: string;
  label: string;
  documentId: number | null;
  customerContractId: number | null;
};
const formatDate = (value: string | null | undefined) => value
  ? new Date(value.length === 10 ? `${value}T00:00:00` : value).toLocaleDateString('ru-RU')
  : '—';
const selectedBasisValue = ref('');
const basisRequired = computed(() => ['act', 'tn2', 'ttn1'].includes(workspace.documentType.value));
const isConsumerDocument = computed(() => isConsumerDocumentType(workspace.documentType.value));
const isBusinessTermsDocument = computed(() => isBusinessTermsDocumentType(workspace.documentType.value));
const basisOptions = computed<BasisOption[]>(() => {
  const result: BasisOption[] = [];
  const contract = props.order.customer_contract;
  if (contract?.status === 'active') {
    result.push({
      value: `customer-contract:${contract.id}`,
      label: `Договор № ${contract.number} от ${formatDate(contract.valid_from)}`,
      documentId: null,
      customerContractId: contract.id,
    });
  }

  const nativeBases = workspace.documents.value
    .filter((item) => ['issued', 'sent', 'signed'].includes(item.status))
    .filter((item) => item.doc_type === 'contract' || item.doc_type === 'offer' || (item.doc_type === 'invoice' && item.business_role === 'offer'))
    .sort((a, b) => (a.doc_type === 'contract' ? -1 : 0) - (b.doc_type === 'contract' ? -1 : 0));
  const nativeIds = new Set(nativeBases.map((item) => item.id));
  for (const document of nativeBases) {
    result.push({
      value: `document:${document.id}`,
      label: `${officialDocumentTitle(document)} от ${formatDate(document.official_date || document.date)}`,
      documentId: document.id,
      customerContractId: null,
    });
  }
  for (const document of props.order.documents || []) {
    if (nativeIds.has(document.id) || !['contract', 'offer'].includes(document.doc_type)) continue;
    result.push({
      value: `document:${document.id}`,
      label: `${documentTypeName(document.doc_type)} № ${document.number} от ${formatDate(document.date)}`,
      documentId: document.id,
      customerContractId: null,
    });
  }
  return result;
});

const syncBasis = () => {
  if (!basisRequired.value) {
    selectedBasisValue.value = '';
    workspace.baseDocumentId.value = null;
    workspace.baseCustomerContractId.value = null;
    return;
  }
  if (!basisOptions.value.some((item) => item.value === selectedBasisValue.value)) {
    selectedBasisValue.value = basisOptions.value[0]?.value || '';
  }
  const selected = basisOptions.value.find((item) => item.value === selectedBasisValue.value);
  workspace.baseDocumentId.value = selected?.documentId || null;
  workspace.baseCustomerContractId.value = selected?.customerContractId || null;
};

watch([basisRequired, basisOptions, selectedBasisValue], syncBasis, { immediate: true });

watch(() => props.order.id, () => void workspace.loadWorkspace(), { immediate: true });

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
const artifactName = (kind: string) => kind === 'pdf' ? 'PDF' : kind === 'rendered_docx' ? 'DOCX' : kind;
</script>

<template>
  <section class="rounded-2xl border border-teal-200 bg-white p-4 shadow-sm dark:border-teal-900/70 dark:bg-slate-900/60 sm:p-5" data-testid="native-documents-workspace">
    <div class="flex flex-col gap-3 border-b border-slate-100 pb-4 dark:border-slate-800 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <div class="flex flex-wrap items-center gap-2">
          <h3 class="font-['Space_Grotesk'] text-lg font-bold text-slate-900 dark:text-white">Документы CRM</h3>
          <span class="rounded-full bg-teal-100 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-teal-800 dark:bg-teal-950/60 dark:text-teal-300">DOCX + PDF</span>
        </div>
        <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">Черновик фиксирует данные. Официальный номер выдаётся только при явном выпуске.</p>
      </div>
      <button v-if="canManageDocumentSettings" class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-200 px-3 text-xs font-semibold text-slate-600 hover:border-teal-400 hover:text-teal-700 dark:border-slate-700 dark:text-slate-300" type="button" @click="openSettings">
        <span class="material-icons-round text-[17px]">settings</span>Юрлица и шаблоны
      </button>
    </div>

    <div v-if="workspace.loading.value" class="flex items-center justify-center gap-2 py-10 text-sm text-slate-500">
      <span class="material-icons-round animate-spin text-[20px]">progress_activity</span>Загружаем документный контур…
    </div>

    <template v-else>
      <div v-if="!workspace.legalEntities.value.length" class="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        <strong>Нужно один раз заполнить реквизиты.</strong>
        <button v-if="canManageDocumentSettings" class="ml-2 underline underline-offset-2" type="button" @click="openSettings">Открыть настройки</button>
        <span v-else class="ml-1">Обратитесь к владельцу аккаунта.</span>
      </div>

      <div v-if="access.canCreate && workspace.legalEntities.value.length" ref="formRef" class="mt-4 rounded-xl bg-slate-50 p-4 dark:bg-slate-800/60">
        <div v-if="workspace.replacesDocumentId.value" class="mb-4 flex items-center justify-between gap-3 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-900">
          <span>Готовим замену для документа CRM #{{ workspace.replacesDocumentId.value }}</span>
          <button class="font-bold" type="button" @click="workspace.replacesDocumentId.value = null">Отменить</button>
        </div>

        <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-[150px_minmax(160px,.8fr)_minmax(220px,1.2fr)_140px_160px_auto] xl:items-end">
          <label class="native-field">
            <span>Тип</span>
            <select v-model="workspace.documentType.value" class="native-input" data-testid="native-document-type">
              <optgroup label="Для организаций">
                <option v-for="type in BUSINESS_NATIVE_DOCUMENT_TYPES" :key="type.value" :value="type.value">{{ type.label }}</option>
              </optgroup>
              <optgroup label="Для физлиц">
                <option v-for="type in CONSUMER_NATIVE_DOCUMENT_TYPES" :key="type.value" :value="type.value">{{ type.label }}</option>
              </optgroup>
            </select>
          </label>
          <label class="native-field">
            <span>Юрлицо</span>
            <select v-model="workspace.selectedLegalEntityId.value" class="native-input" data-testid="native-legal-entity">
              <option v-for="entity in workspace.legalEntities.value" :key="entity.id" :value="entity.id">{{ entity.display_name }}</option>
            </select>
          </label>
          <label class="native-field">
            <span>Шаблон</span>
            <select v-model="workspace.selectedTemplateId.value" class="native-input">
              <option v-for="template in workspace.templates.value" :key="template.id" :value="template.id">{{ template.name }}</option>
            </select>
          </label>
          <label class="native-field">
            <span>Дата документа</span>
            <input v-model="workspace.issueDate.value" class="native-input" type="date" />
          </label>
          <label class="native-field">
            <span>Город документа</span>
            <input v-model="workspace.issueCity.value" class="native-input" data-testid="native-document-issue-city" placeholder="Витебск" />
          </label>
          <button class="inline-flex h-10 items-center justify-center rounded-xl bg-teal-600 px-4 text-sm font-bold text-white hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-50" type="button" data-testid="create-native-draft" :disabled="workspace.busy.value || Boolean(workspace.draftBlockedReason.value)" :title="workspace.draftBlockedReason.value" @click="workspace.createDraft">
            Создать черновик
          </button>
        </div>

        <label v-if="basisRequired" class="native-field mt-4">
          <span>Документ-основание</span>
          <select v-model="selectedBasisValue" class="native-input" data-testid="native-document-basis">
            <option value="" disabled>Выберите договор, счёт-оферту или КП</option>
            <option v-for="basis in basisOptions" :key="basis.value" :value="basis.value">{{ basis.label }}</option>
          </select>
          <span class="font-normal text-slate-500">Первым предлагается договор. Обычный счёт на оплату основанием не считается.</span>
        </label>

        <div v-if="workspace.documentType.value === 'invoice'" class="mt-4">
          <span class="text-xs font-bold text-slate-500">Роль счёта</span>
          <div class="mt-1.5 inline-flex rounded-xl border border-slate-200 bg-white p-1 dark:border-slate-700 dark:bg-slate-900" data-testid="invoice-role-toggle">
            <button type="button" class="rounded-lg px-3 py-1.5 text-sm font-semibold transition" :class="workspace.businessRole.value === 'payment_request' ? 'bg-teal-600 text-white' : 'text-slate-600 dark:text-slate-300'" @click="workspace.businessRole.value = 'payment_request'">Документ для оплаты</button>
            <button type="button" class="rounded-lg px-3 py-1.5 text-sm font-semibold transition" :class="workspace.businessRole.value === 'offer' ? 'bg-teal-600 text-white' : 'text-slate-600 dark:text-slate-300'" @click="workspace.businessRole.value = 'offer'">Счёт-оферта</button>
          </div>
          <p class="mt-1.5 text-xs text-slate-500">{{ workspace.businessRole.value === 'payment_request' ? 'После появления договора закрывающие документы будут ссылаться на договор.' : 'Оферта может сама стать основанием сделки.' }}</p>
        </div>
        <ConsumerDocumentTermsPanel
          v-if="isConsumerDocument"
          :document-type="workspace.documentType.value"
          :terms="workspace.consumerTerms.value"
          @update-terms="workspace.consumerTerms.value = $event"
        />
        <B2BContractTermsPanel
          v-if="isBusinessTermsDocument"
          :document-type="workspace.documentType.value"
          :default-goods-warranty-months="workspace.selectedGoodsWarrantyDefault.value"
          :terms="workspace.businessTerms.value"
          @update-terms="workspace.businessTerms.value = $event"
        />
        <ActTermsPanel
          v-if="workspace.documentType.value === 'act'"
          :terms="workspace.actTerms.value"
          @update-terms="workspace.actTerms.value = $event"
        />
        <p v-if="workspace.draftBlockedReason.value" class="mt-3 text-xs font-semibold text-amber-700 dark:text-amber-300">{{ workspace.draftBlockedReason.value }}. <button v-if="canManageDocumentSettings" class="underline" type="button" @click="openSettings">Исправить в настройках</button></p>
      </div>

      <p v-else-if="!access.canCreate" class="mt-4 rounded-xl bg-slate-50 p-3 text-sm text-slate-500 dark:bg-slate-800">{{ access.summary }}</p>

      <div v-if="workspace.issueBlockedReason.value" class="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900" data-testid="pdf-runtime-warning">
        <strong>Выпуск временно недоступен:</strong> {{ workspace.issueBlockedReason.value }}. Черновики создавать можно; официальный номер не будет занят до успешного выпуска.
      </div>

      <div class="mt-4 space-y-3">
        <article v-for="document in workspace.documents.value" :key="document.id" class="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <h4 class="font-bold text-slate-900 dark:text-white">{{ document.status === 'draft' ? `${documentTypeName(document.doc_type)} · номер ещё не присвоен` : officialDocumentTitle(document) }}</h4>
                <span class="rounded-full px-2 py-0.5 text-[11px] font-bold" :class="managedDocumentStatusClass(document.status)">{{ managedDocumentStatus(document.status) }}</span>
                <span v-if="document.business_role === 'offer'" class="rounded-full bg-violet-100 px-2 py-0.5 text-[11px] font-bold text-violet-800">Счёт-оферта</span>
              </div>
              <p class="mt-1 text-xs text-slate-500">от {{ formatDate(document.official_date || document.date) }} · CRM: <span class="font-mono">{{ document.internal_reference || `#${document.id}` }}</span></p>
              <p v-if="document.replaces_document_id" class="mt-1 text-xs font-semibold text-blue-600">Заменяет CRM-документ #{{ document.replaces_document_id }}</p>
              <p v-if="document.void_reason" class="mt-1 text-xs text-rose-600">Причина: {{ document.void_reason }}</p>
            </div>

            <div class="flex flex-wrap gap-2 sm:justify-end">
              <button v-for="artifact in document.artifacts" :key="artifact.id" class="native-action" type="button" @click="workspace.downloadArtifact(artifact.id)">
                <span class="material-icons-round text-[17px]">download</span>{{ artifactName(artifact.kind) }}
              </button>
              <button v-if="document.status === 'draft' && access.canCreate" class="native-action-primary" type="button" :disabled="workspace.busy.value || Boolean(workspace.issueBlockedReason.value)" :title="workspace.issueBlockedReason.value" @click="workspace.issue(document)">Выпустить</button>
              <button v-if="['issued', 'sent', 'signed'].includes(document.status) && access.canReplace" class="native-action" type="button" @click="prepareReplacement(document)">Заменить</button>
              <button v-if="['issued', 'sent', 'signed'].includes(document.status) && access.canReplace" class="native-action-danger" type="button" @click="workspace.requestVoid(document)">Аннулировать</button>
            </div>
          </div>

          <form v-if="workspace.voidTarget.value?.id === document.id" class="mt-3 flex flex-col gap-2 rounded-lg bg-rose-50 p-3 sm:flex-row sm:items-end" @submit.prevent="workspace.voidDocument">
            <label class="native-field flex-1"><span>Причина аннулирования</span><input v-model="workspace.voidReason.value" class="native-input" placeholder="Ошибка в реквизитах" /></label>
            <button class="native-action-danger h-10" type="submit" :disabled="workspace.busy.value || !workspace.voidReason.value.trim()">Подтвердить</button>
            <button class="native-action h-10" type="button" @click="workspace.voidTarget.value = null">Отмена</button>
          </form>
        </article>

        <div v-if="!workspace.documents.value.length" class="rounded-xl border border-dashed border-slate-300 p-8 text-center dark:border-slate-700">
          <span class="material-icons-round text-4xl text-slate-300">description</span>
          <p class="mt-2 text-sm font-semibold text-slate-600 dark:text-slate-300">Внутренних документов пока нет</p>
          <p class="mt-1 text-xs text-slate-500">Google-документы находятся на соседней вкладке.</p>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.native-field { @apply flex min-w-0 flex-col gap-1.5 text-xs font-semibold text-slate-600 dark:text-slate-300; }
.native-input { @apply h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-normal text-slate-900 outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/15 dark:border-slate-700 dark:bg-slate-900 dark:text-white; }
.native-action { @apply inline-flex h-9 items-center justify-center gap-1 rounded-lg border border-slate-200 px-3 text-xs font-semibold text-slate-600 hover:border-teal-400 hover:text-teal-700 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300; }
.native-action-primary { @apply inline-flex h-9 items-center justify-center rounded-lg bg-teal-600 px-3 text-xs font-bold text-white hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-50; }
.native-action-danger { @apply inline-flex h-9 items-center justify-center rounded-lg border border-rose-200 px-3 text-xs font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-50; }
</style>
