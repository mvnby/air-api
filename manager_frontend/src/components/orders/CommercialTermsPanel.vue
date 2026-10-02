<script setup lang="ts">
import { ref, watch } from 'vue';
import PaymentTermsPanel from '../../features/documents/components/PaymentTermsPanel.vue';
import { createDefaultBusinessDocumentTerms, businessTermsValidationError, type BusinessDocumentTerms } from '../../features/documents/model/business-document-terms';
import { commercialTermsApi, type CommercialTerms } from '../../services/commercial-terms-api';
import { serviceAttachmentsApi } from '../service-attachments/api';
import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{ orderId: number; workflowType?: string | null; attachmentIds?: number[]; emailSource?: boolean }>();
const emit = defineEmits<{ saved: [] }>();
const data = ref<CommercialTerms | null>(null);
const terms = ref<BusinessDocumentTerms>(createDefaultBusinessDocumentTerms(props.workflowType));
const editing = ref(false);
const busy = ref(false);
const message = ref('');
let sequence = 0;
watch(() => props.orderId, async (orderId) => {
  const current = ++sequence;
  data.value = null; editing.value = false; message.value = '';
  try {
    const response = await commercialTermsApi.read(orderId);
    if (current !== sequence) return;
    data.value = response;
  } catch (error) {
    if (current === sequence) message.value = getApiErrorMessage(error);
  }
}, { immediate: true });
const extractOriginals = async () => {
  const orderId = props.orderId;
  const current = sequence;
  busy.value = true;
  try {
    let attachmentIds = props.attachmentIds;
    if (!attachmentIds) {
      const attachments = await serviceAttachmentsApi.list(orderId);
      attachmentIds = attachments.items.filter((item) => item.source === 'email_lead_intake' && item.id != null && /\.(pdf|docx?)$/i.test(item.filename)).map((item) => item.id!);
    }
    if (!attachmentIds.length) { message.value = 'Поддерживаемые оригиналы PDF, DOCX или DOC не найдены'; return; }
    if (attachmentIds.length > 8) { message.value = 'Найдено больше восьми документов: выберите оригиналы для анализа'; return; }
    const response = await commercialTermsApi.extract(orderId, attachmentIds);
    if (current === sequence) { data.value = response; emit('saved'); }
  } catch (error) { if (current === sequence) message.value = getApiErrorMessage(error); }
  finally { busy.value = false; }
};
const edit = () => {
  const base = createDefaultBusinessDocumentTerms(props.workflowType);
  const seed = data.value?.proposed || data.value?.suggested;
  // Incomplete customer terms have no schedule suggestion: require manager selection.
  terms.value = { ...base, ...seed, contract_scenario: seed?.contract_scenario || base.contract_scenario,
    payment_schedule: (seed?.payment_schedule || []).map((item) => ({ ...item, share_percent: Number(item.share_percent) })),
  };
  editing.value = true;
};
const save = async (confirmed: boolean) => {
  const issue = businessTermsValidationError('offer', terms.value);
  if (issue) { message.value = issue; return; }
  const orderId = props.orderId;
  const current = sequence;
  busy.value = true;
  try {
    const response = await commercialTermsApi.update(orderId, data.value?.revision || 0, terms.value, confirmed);
    if (current !== sequence) return;
    data.value = response; editing.value = false; message.value = confirmed ? 'Условия подтверждены для документов' : 'Наш вариант сохранён'; emit('saved');
  } catch (error) {
    if (current === sequence) message.value = getApiErrorMessage(error);
  } finally { busy.value = false; }
};
</script>
<template>
  <section class="space-y-3 rounded-xl border border-slate-200 p-4 dark:border-slate-700" data-testid="commercial-terms-panel">
    <h4 class="font-semibold">Оплата и поставка</h4>
    <template v-if="data">
      <p class="text-xs text-slate-500">Условия заказчика из источника</p>
      <button v-if="attachmentIds?.length || emailSource" type="button" :disabled="busy" class="text-sm font-semibold text-brand-700" @click="extractOriginals">Извлечь условия из оригиналов</button>
      <div v-for="(term, index) in data.customer_requested" :key="index" class="text-sm">
        <p>{{ term.evidence }}</p><p class="text-xs text-slate-500">{{ term.source }}</p>
        <p v-for="issue in term.issues" :key="issue" class="text-xs text-amber-700">{{ issue }}</p>
      </div>
      <p v-if="!data.customer_requested.length" class="text-sm text-slate-500">В доступном тексте явные условия не найдены. Проверьте оригинал.</p>
      <p v-for="warning in data.warnings" :key="warning" class="text-xs text-amber-700">{{ warning }}</p>
      <p v-if="data.proposed" class="text-sm font-medium">Наш вариант: {{ data.confirmed ? 'подтверждён для документов' : 'требует согласования' }}</p>
      <button v-if="!editing" type="button" class="text-sm font-semibold text-brand-700" @click="edit">{{ data.proposed ? 'Изменить наш вариант' : 'Подготовить наш вариант' }}</button>
      <div v-if="editing" class="space-y-3">
        <PaymentTermsPanel :terms="terms" embedded @update-terms="terms = $event" />
        <label class="block text-sm">Срок поставки<input v-model="terms.delivery_deadline" type="date" class="ml-2 rounded-lg border border-slate-300 p-2" /></label>
        <label class="block text-sm">Дополнительные условия<textarea v-model="terms.additional_conditions" rows="2" class="mt-1 w-full rounded-lg border border-slate-300 p-2" /></label>
        <div class="flex flex-wrap gap-3 text-sm">
          <button type="button" :disabled="busy" class="rounded-lg border px-3 py-2" @click="save(false)">Сохранить наш вариант</button>
          <button type="button" :disabled="busy" class="rounded-lg bg-brand-600 px-3 py-2 text-white" @click="save(true)">Подтвердить для документов</button>
          <button type="button" :disabled="busy" @click="editing = false">Отмена</button>
        </div>
      </div>
    </template>
    <p v-if="message" class="text-sm" role="status">{{ message }}</p>
  </section>
</template>
