<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { ManagerDocumentSystemService, ManagerMailService } from '../../client';
import type { ManagerOrderDetailResponse } from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';

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
const toEmail = ref('');
const subject = ref('');
const bodyText = ref('');
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
const composing = ref(false);
const subjectTouched = ref(false);
const bodyTouched = ref(false);
let composeRequestId = 0;
let resettingSelection = false;

const selectedDocuments = computed(() => {
  const selected = new Set(selectedDocumentIds.value);
  return props.documents.filter((doc) => selected.has(doc.id));
});

const hasOfferSelected = computed(() => selectedDocuments.value.some((doc) => doc.doc_type === 'offer'));
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
  if (key === 'auto' || key === 'documents') return props.documents.length > 0;
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

const buildSubject = () => (
  hasOfferSelected.value
    ? `Коммерческое предложение по заказу #${props.order.id}`
    : `Документы по заказу #${props.order.id}`
);

const buildBody = () => {
  const customerName = props.order.customer?.name || 'клиент';
  const lines = selectedDocuments.value.map((doc) => `- ${documentLabel(doc)}`);
  return [
    `Здравствуйте, ${customerName}!`,
    '',
    'Направляем документы по вашему заказу во вложении:',
    ...(lines.length ? lines : ['- документы по заказу']),
    '',
    'С уважением,',
    'Мастер Воздуха',
  ].join('\n');
};

const refreshDefaults = () => {
  resettingSelection = true;
  selectedDocumentIds.value = latestDefaultDocumentIds();
  toEmail.value = props.order.customer?.email || '';
  templateKey.value = props.documents.length ? 'auto' : 'request_requisites';
  subject.value = buildSubject();
  bodyText.value = buildBody();
  missingRequisites.value = [];
  error.value = '';
  subjectTouched.value = false;
  bodyTouched.value = false;
  void nextTick(() => {
    resettingSelection = false;
    return applyTemplate(true);
  });
};

const applyTemplate = async (force = false) => {
  if (!props.modelValue || templateKey.value === 'custom') return;
  const requestId = ++composeRequestId;
  composing.value = true;
  try {
    const payload = {
      document_ids: selectedDocumentIds.value,
      template_key: templateKey.value,
    };
    const result = props.transport === 'native'
      ? await ManagerDocumentSystemService.composeManagerNativeOrderEmail(props.order.id, payload)
      : await ManagerMailService.composeManagerOrderEmail(props.order.id, payload);
    if (requestId !== composeRequestId) return;
    templateOptions.value = result.template_options || templateOptions.value;
    missingRequisites.value = result.missing_requisites || [];
    if (force || !subjectTouched.value) subject.value = result.subject;
    if (force || !bodyTouched.value) bodyText.value = result.body_text;
    error.value = '';
  } catch (err) {
    if (requestId !== composeRequestId) return;
    error.value = getApiErrorMessage(err);
  } finally {
    if (requestId === composeRequestId) composing.value = false;
  }
};

const changeTemplate = () => {
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
  subjectTouched.value = false;
  bodyTouched.value = false;
  void nextTick(() => {
    resettingSelection = false;
    return applyTemplate(true);
  });
};

watch(
  () => props.modelValue,
  (open) => {
    if (open) refreshDefaults();
  },
);

watch(selectedDocumentIds, () => {
  if (!props.modelValue || resettingSelection) return;
  if (templateKey.value === 'custom') return;
  void applyTemplate(false);
});

const close = () => {
  if (sending.value) return;
  emit('update:modelValue', false);
};

const sendEmail = async () => {
  error.value = '';
  if (documentsRequired.value && !selectedDocumentIds.value.length) {
    error.value = 'Выберите хотя бы один документ';
    return;
  }
  if (!toEmail.value.trim()) {
    error.value = 'Укажите email получателя';
    return;
  }
  if (!subject.value.trim()) {
    error.value = 'Укажите тему письма';
    return;
  }
  if (!bodyText.value.trim()) {
    error.value = 'Укажите текст письма';
    return;
  }

  sending.value = true;
  try {
    const payload = {
      to_email: toEmail.value.trim(),
      subject: subject.value.trim(),
      body_text: bodyText.value.trim(),
      document_ids: selectedDocumentIds.value,
    };
    if (props.transport === 'native') {
      await ManagerDocumentSystemService.sendManagerNativeOrderEmail(props.order.id, payload);
    } else {
      await ManagerMailService.sendManagerOrderEmail(props.order.id, payload);
    }
    emit('settled');
    emit('sent');
    emit('update:modelValue', false);
  } catch (err) {
    error.value = getApiErrorMessage(err);
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
            <h3 class="text-lg font-semibold">Отправить документы</h3>
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

        <div class="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          <div>
            <label class="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Получатель</label>
            <input
              v-model="toEmail"
              type="email"
              class="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
              placeholder="client@example.com"
            />
          </div>

          <div>
            <div class="mb-1 flex items-center justify-between gap-3">
              <label class="block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Шаблон письма</label>
              <button
                v-if="subjectTouched || bodyTouched"
                type="button"
                class="text-xs font-semibold text-teal-700 hover:text-teal-800 dark:text-teal-300"
                :disabled="composing"
                @click="applyTemplate(true)"
              >
                Обновить по шаблону
              </button>
            </div>
            <select
              v-model="templateKey"
              class="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
              :disabled="composing"
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
                class="flex cursor-pointer items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm hover:border-teal-300 dark:border-slate-700 dark:bg-slate-800/70 dark:hover:border-teal-500/70"
              >
                <input
                  v-model="selectedDocumentIds"
                  type="checkbox"
                  :value="doc.id"
                  class="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
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

          <div
            v-if="missingRequisites.length"
            class="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100"
          >
            <p class="font-semibold">В карточке клиента не заполнено</p>
            <p class="mt-1">{{ missingRequisites.map((item) => item.label).join(', ') }}</p>
          </div>

          <div>
            <label class="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Тема</label>
            <input
              v-model="subject"
              type="text"
              class="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
              @input="subjectTouched = true"
            />
          </div>

          <div>
            <label class="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Текст</label>
            <textarea
              v-model="bodyText"
              rows="8"
              class="w-full resize-y rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm leading-6 outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
              @input="bodyTouched = true"
            />
          </div>

          <p v-if="error" class="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-500/40 dark:bg-red-950/30 dark:text-red-200">
            {{ error }}
          </p>
        </div>

        <footer class="flex flex-col-reverse gap-2 border-t border-slate-200 px-5 py-4 sm:flex-row sm:justify-end dark:border-slate-700">
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
            class="inline-flex items-center justify-center gap-2 rounded-xl bg-teal-600 px-4 py-2 text-sm font-semibold text-white shadow hover:bg-teal-700 disabled:opacity-50"
            :disabled="sending || composing || (documentsRequired && !selectedDocumentIds.length)"
            @click="sendEmail"
          >
            <span v-if="sending" class="material-icons-round animate-spin text-[18px]">loop</span>
            <span v-else-if="composing" class="material-icons-round animate-spin text-[18px]">loop</span>
            <span v-else class="material-icons-round text-[18px]">send</span>
            {{ sending ? 'Отправляем...' : composing ? 'Готовим...' : 'Отправить' }}
          </button>
        </footer>
      </div>
    </div>
  </teleport>
</template>
