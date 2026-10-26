<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { ManagerDocumentSystemService, ManagerMailService } from '../../client';
import type { ManagerOrderDetailResponse } from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
import { listCertificates, type RegistrationCertificate } from '../../features/documents/registration-certificates';
import { mailApi, mailCommandKey, type MailAccount, type MailMessage } from '../../services/mail-workspace-api';
import MailDraftEditor from '../mail/MailDraftEditor.vue';

type SendableOrderDocument = {
  id: number;
  doc_type: string;
  date: string;
  number?: string | null;
  display_number?: string | null;
};

const props = defineProps<{
  modelValue: boolean;
  order: ManagerOrderDetailResponse;
  documents: SendableOrderDocument[];
  transport?: 'legacy' | 'native';
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  sent: [];
  settled: [];
}>();

const DOC_TYPE_LABELS: Record<string, string> = {
  offer: 'КП',
  contract: 'Договор',
  invoice: 'Счет',
  retail_receipt: 'Товарный чек',
  service_act: 'Заказ-акт',
  maintenance_service_act: 'Заказ-акт ТО',
  act: 'Акт',
  defect_act: 'Дефектный акт',
  tn2: 'ТН-2',
  ttn1: 'ТТН-1',
  uploaded_pdf: 'PDF',
};

const selectedDocumentIds = ref<number[]>([]);
const registrationCertificateId = ref('');
const certificateOptions = ref<Array<RegistrationCertificate & { issuerName: string }>>([]);
async function loadCertificateOptions() {
  const result = await ManagerDocumentSystemService.listManagerDocumentLegalEntities();
  const groups = await Promise.all((result.items || []).filter((entity) => entity.status === 'active').map(async (entity) =>
    (await listCertificates(entity.id)).filter((item) => item.is_current).map((item) => ({ ...item, issuerName: entity.display_name }))));
  certificateOptions.value = groups.flat();
}
const certificateIssuerId = computed(() => certificateOptions.value.find((item) => item.id === registrationCertificateId.value)?.legal_entity_id);

const toEmail = ref('');
const templateKey = ref('auto');
const templateOptions = ref<Array<{ key: string; label: string; requires_documents?: boolean }>>([
  { key: 'auto', label: 'Автоматически', requires_documents: true },
  { key: 'offer', label: 'Коммерческое предложение', requires_documents: true },
  { key: 'invoice', label: 'Счёт', requires_documents: true },
  { key: 'contract', label: 'Договор', requires_documents: true },
  { key: 'documents', label: 'Комплект документов', requires_documents: true },
  { key: 'act', label: 'Акт', requires_documents: true },
  { key: 'request_requisites', label: 'Запросить реквизиты', requires_documents: false },
  { key: 'request_signer', label: 'Запросить данные подписанта', requires_documents: false },
  { key: 'custom', label: 'Произвольное письмо', requires_documents: false },
]);
const missingRequisites = ref<Array<{ key: string; label: string }>>([]);
const error = ref('');
const sending = ref(false);
const creationUncertain = ref(false);
let createOrderId = props.order.id;
const mailDraft = ref<MailMessage | null>(null);
const mailAccounts = ref<MailAccount[]>([]);
const draftEditor = ref<{ save: () => Promise<boolean>; applySuggestion: (value: { version: number; subject: string; body_text: string }) => void } | null>(null);
let createKey = mailCommandKey();
let createPayload: Parameters<typeof mailApi.createOrderDraft>[1] | null = null;
const composing = ref(false);
let composeRequestId = 0;
let resettingSelection = false;
let templateExplicitlyChosen = false;

const activeTemplate = computed(() => (
  templateOptions.value.find((item) => item.key === templateKey.value) || templateOptions.value[0]
));
const documentsRequired = computed(() => activeTemplate.value?.requires_documents !== false);

const documentLabel = (doc: SendableOrderDocument) => {
  const typeLabel = DOC_TYPE_LABELS[doc.doc_type] || doc.doc_type || 'Документ';
  return `${typeLabel} ${doc.number || doc.display_number || `#${doc.id}`}`;
};

const templateAvailable = (key: string) => {
  if (['request_requisites', 'request_signer', 'custom'].includes(key)) return true;
  if (key === 'auto' || key === 'documents') return props.documents.length > 0 || !!registrationCertificateId.value;
  if (key === 'act') {
    const actTypes = new Set(['act', 'service_act', 'maintenance_service_act', 'defect_act', 'retail_receipt']);
    return props.documents.some((item) => actTypes.has(item.doc_type));
  }
  return props.documents.some((item) => item.doc_type === key);
};

const latestDefaultDocumentIds = () => {
  const advancedIds: number[] = [];
  for (const type of ['invoice', 'contract']) {
    const doc = props.documents.find((item) => item.doc_type === type);
    if (doc && !advancedIds.includes(doc.id)) advancedIds.push(doc.id);
  }
  if (advancedIds.length) return advancedIds;
  const offer = props.documents.find((item) => item.doc_type === 'offer');
  return offer ? [offer.id] : props.documents.slice(0, 1).map((doc) => doc.id);
};

const refreshDefaults = () => {
  if (creationUncertain.value && createPayload && createOrderId === props.order.id) return;
  creationUncertain.value = false;
  mailDraft.value = null;
  createKey = mailCommandKey();
  createPayload = null;
  resettingSelection = true;
  selectedDocumentIds.value = latestDefaultDocumentIds();
  registrationCertificateId.value = '';
  certificateOptions.value = [];
  void loadCertificateOptions().catch((err) => { error.value = getApiErrorMessage(err); });
  toEmail.value = props.order.customer?.email || '';
  templateExplicitlyChosen = false;
  templateKey.value = props.documents.length ? 'auto' : 'request_requisites';
  missingRequisites.value = [];
  error.value = '';
  void nextTick(() => {
    resettingSelection = false;
    return applyTemplate();
  });
};

const applyTemplate = async () => {
  if (!props.modelValue || templateKey.value === 'custom') return;
  const requestId = ++composeRequestId;
  composing.value = true;
  try {
    const payload = {
      document_ids: [...selectedDocumentIds.value],
      registration_certificate_id: registrationCertificateId.value || null,
      legal_entity_id: certificateIssuerId.value || null,
      template_key: templateKey.value,
    };
    const result = props.transport === 'native'
      ? await ManagerDocumentSystemService.composeManagerNativeOrderEmail(props.order.id, payload)
      : await ManagerMailService.composeManagerOrderEmail(props.order.id, payload);
    if (requestId !== composeRequestId) return;
    templateOptions.value = result.template_options || templateOptions.value;
    missingRequisites.value = result.missing_requisites || [];
    error.value = '';
  } catch (err) {
    if (requestId !== composeRequestId) return;
    error.value = getApiErrorMessage(err);
  } finally {
    if (requestId === composeRequestId) composing.value = false;
  }
};

const changeTemplate = () => {
  createPayload = null;
  createKey = mailCommandKey();
  templateExplicitlyChosen = true;
  resettingSelection = true;
  if (templateKey.value === 'request_requisites' || templateKey.value === 'request_signer') {
    selectedDocumentIds.value = [];
  } else if (['offer', 'invoice', 'contract'].includes(templateKey.value)) {
    const document = props.documents.find((item) => item.doc_type === templateKey.value);
    if (document) selectedDocumentIds.value = [document.id];
  } else if (templateKey.value === 'act') {
    const actTypes = new Set(['act', 'service_act', 'maintenance_service_act', 'defect_act', 'retail_receipt']);
    const document = props.documents.find((item) => actTypes.has(item.doc_type));
    if (document) selectedDocumentIds.value = [document.id];
  }
  void nextTick(() => {
    resettingSelection = false;
    return applyTemplate();
  });
};

watch(
  () => props.modelValue,
  (open) => {
    if (open) refreshDefaults();
  },
  { immediate: true },
);

watch([selectedDocumentIds, registrationCertificateId], () => {
  if (!props.modelValue || resettingSelection || creationUncertain.value) return;
  createPayload = null;
  createKey = mailCommandKey();
  if (!props.documents.length && !templateExplicitlyChosen) {
    templateKey.value = registrationCertificateId.value ? 'auto' : 'request_requisites';
  }
  if (templateKey.value === 'custom') return;
  void applyTemplate();
});

const close = async () => {
  if (sending.value) return;
  if (draftEditor.value && !await draftEditor.value.save()) return;
  emit('update:modelValue', false);
};

const sendEmail = async () => {
  if (sending.value || mailDraft.value) return;
  error.value = '';
  if (documentsRequired.value && !selectedDocumentIds.value.length && !registrationCertificateId.value) {
    error.value = 'Выберите хотя бы один документ';
    return;
  }
  sending.value = true;
  let createStarted = false;
  try {
    const payload = createPayload || {
      to_email: toEmail.value.trim(),
      template_key: templateKey.value,
      subject: '',
      body_text: null,
      document_ids: [...selectedDocumentIds.value],
      registration_certificate_id: registrationCertificateId.value || null,
      legal_entity_id: certificateIssuerId.value || null,
    };
    createPayload = payload;
    createOrderId = props.order.id;
    mailAccounts.value = (await mailApi.accounts()).items;
    createStarted = true;
    mailDraft.value = await mailApi.createOrderDraft(props.order.id, payload, props.transport || 'legacy', createKey);
    creationUncertain.value = false;
    const initial = mailDraft.value;
    void mailApi.suggest(initial.id, initial.version).then(async suggestion => {
      await nextTick();
      if (props.modelValue && mailDraft.value?.id === initial.id) draftEditor.value?.applySuggestion(suggestion);
    }).catch(() => { /* The saved deterministic text remains ready to edit and send. */ });
  } catch (err) {
    const status = (err as { status?: number })?.status;
    if (creationUncertain.value || (createStarted && (!status || status >= 500))) {
      creationUncertain.value = true;
      error.value = 'Ответ о сохранении черновика не получен. Выбор зафиксирован: повторите подготовку, чтобы открыть тот же черновик. Письмо ещё не отправляется.';
    } else {
      createPayload = null;
      createKey = mailCommandKey();
      error.value = getApiErrorMessage(err);
    }
    emit('settled');
  } finally {
    sending.value = false;
  }
};
</script>

<template>
  <teleport to="body">
    <div
      v-if="modelValue"
      class="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/50 px-4 py-6 backdrop-blur-sm"
    >
      <div class="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white text-slate-900 shadow-2xl dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100">
        <header class="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-700">
          <div>
            <h3 class="text-lg font-semibold">Письмо по заказу</h3>
            <p class="text-sm text-slate-500 dark:text-slate-400">Заказ #{{ order.id }}</p>
          </div>
          <button
            type="button"
            class="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
            :disabled="sending"
            title="Закрыть"
            @click="close"
          >
            <span class="material-icons-round text-[20px]">close</span>
          </button>
        </header>

        <div v-if="mailDraft" class="flex-1 overflow-y-auto p-4"><MailDraftEditor :key="mailDraft.id" ref="draftEditor" :initial="mailDraft" :accounts="mailAccounts" @saved="mailDraft = $event" @close="close" @deleted="mailDraft = null; close()" @sent="emit('settled'); emit('sent')" /></div>
        <div v-else class="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          <p class="text-sm text-slate-600 dark:text-slate-300">Выберите документы. Письмо откроется с сохранёнными файлами; адреса, текст и подпись можно будет изменить перед отправкой.</p>

          <div>
            <div class="mb-1 flex items-center justify-between gap-3">
              <label class="block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Шаблон письма</label>

            </div>
            <select
              v-model="templateKey"
              class="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
              :disabled="composing || sending || creationUncertain"
              @change="changeTemplate"
            >
              <option
                v-for="option in templateOptions"
                :key="option.key"
                :value="option.key"
                :disabled="!templateAvailable(option.key)"
              >
                {{ option.label }}
              </option>
            </select>
          </div>

          <div>
            <label class="mb-2 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Документы</label>
            <div v-if="documents.length" class="space-y-2">
              <label
                v-for="doc in documents"
                :key="doc.id"
                class="flex cursor-pointer items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm hover:border-brand-300 dark:border-slate-700 dark:bg-slate-800/70 dark:hover:border-brand-500/70"
              >
                <input
                  v-model="selectedDocumentIds"
                  type="checkbox"
                  :disabled="sending || creationUncertain"
                  :value="doc.id"
                  class="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                />
                <span class="min-w-0 flex-1">
                  <span class="block font-medium text-slate-900 dark:text-white">{{ documentLabel(doc) }}</span>
                  <span class="block text-xs text-slate-500 dark:text-slate-400">{{ new Date(doc.date).toLocaleDateString('ru-RU') }}</span>
                </span>
              </label>
            </div>
            <div v-else class="rounded-xl border border-dashed border-slate-300 py-5 text-center text-sm text-slate-500 dark:border-slate-700">
              Нет сформированных документов
            </div>
            <p v-if="!documentsRequired" class="mt-2 text-xs text-slate-500 dark:text-slate-400">
              Для этого шаблона вложения не обязательны.
            </p>
          </div>

          <div>
            <label class="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Свидетельство о регистрации</label>
            <select v-model="registrationCertificateId" class="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800" :disabled="sending || creationUncertain">
              <option value="">Не прикладывать</option>
              <option v-for="item in certificateOptions" :key="item.id" :value="item.id">{{ item.issuerName }} — {{ item.filename }}</option>
            </select>
            <p class="mt-1 text-xs text-slate-500">Можно отправить отдельно. Для комплекта организация должна совпадать с отправителем документов.</p>
          </div>

          <div
            v-if="missingRequisites.length"
            class="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100"
          >
            <p class="font-semibold">В карточке клиента не заполнено</p>
            <p class="mt-1">{{ missingRequisites.map((item) => item.label).join(', ') }}</p>
          </div>


          <p v-if="error" role="alert" class="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-500/40 dark:bg-red-950/30 dark:text-red-200">
            {{ error }}
          </p>
        </div>

        <footer v-if="!mailDraft" class="flex flex-col-reverse gap-2 border-t border-slate-200 px-5 py-4 sm:flex-row sm:justify-end dark:border-slate-700">
          <button
            type="button"
            class="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
            :disabled="sending"
            @click="close"
          >
            Отмена
          </button>
          <button
            type="button"
            class="inline-flex items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white shadow hover:bg-brand-700 disabled:opacity-50"
            :disabled="sending || composing || (documentsRequired && !selectedDocumentIds.length && !registrationCertificateId)"
            @click="sendEmail"
          >
            <span v-if="sending" class="material-icons-round animate-spin text-[18px]">loop</span>
            <span v-else-if="composing" class="material-icons-round animate-spin text-[18px]">loop</span>
            <span v-else class="material-icons-round text-[18px]">send</span>
            {{ sending ? 'Сохраняем...' : composing ? 'Готовим...' : 'Подготовить письмо' }}
          </button>
        </footer>
      </div>
    </div>
  </teleport>
</template>
