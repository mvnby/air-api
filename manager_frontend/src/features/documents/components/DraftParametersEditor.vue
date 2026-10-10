<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue';
import { ManagerDocumentSystemService, type ManagedDocumentItem, type ManagedDocumentDraftParameters, type ManagedDocumentDraftParameterUpdate } from '../../../client';
import { getApiErrorMessage } from '../../../utils/api-errors';
import { confirmDialog } from '../../../services/ui-feedback';
import { createDefaultBusinessDocumentTerms, type BusinessDocumentTerms } from '../model/business-document-terms';
import { createDefaultConsumerDocumentTerms, type ConsumerDocumentTerms } from '../model/consumer-document-terms';
import { createDefaultActTerms, type ActTerms } from '../model/act-terms';
import { createDefaultTransportTerms, type TransportTerms } from '../model/transport-terms';
import B2BContractTermsPanel from './B2BContractTermsPanel.vue';
import ConsumerDocumentTermsPanel from './ConsumerDocumentTermsPanel.vue';
import ActTermsPanel from './ActTermsPanel.vue';
import TransportTermsPanel from './TransportTermsPanel.vue';

const props = defineProps<{ document: ManagedDocumentItem; disabled?: boolean }>();
const emit = defineEmits<{ close: []; saved: [rebuilt: boolean]; toast: [message: string, type: 'success' | 'error'] }>();
type Form = Omit<ManagedDocumentDraftParameters, 'business_terms' | 'consumer_terms' | 'act_terms' | 'transport_terms'> & {
  business_terms: BusinessDocumentTerms | null;
  consumer_terms: ConsumerDocumentTerms | null;
  act_terms: ActTerms | null;
  transport_terms: TransportTerms | null;
};
const form = ref<Form | null>(null);
const baseline = ref<Form | null>(null);
const loading = ref(true);
const saving = ref(false);
const error = ref('');
let active = true;
onBeforeUnmount(() => { active = false; });
const fields = ['issue_date', 'issue_city', 'business_terms', 'consumer_terms', 'act_terms', 'transport_terms', 'participant_statement'] as const;
const changes = computed(() => {
  const result: Record<string, unknown> = {};
  if (!form.value || !baseline.value) return result;
  for (const name of fields) {
    const value = name === 'issue_city' ? form.value.issue_city?.trim() || null : form.value[name];
    if (JSON.stringify(value) !== JSON.stringify(baseline.value[name])) result[name] = value;
  }
  return result;
});
const rebuilds = computed(() => Object.keys(changes.value).some((name) => name !== 'issue_date'));

const load = async () => {
  try {
    const response = await ManagerDocumentSystemService.getManagerManagedDocumentDraftParameters(props.document.id);
    if (!active) return;
    const business = response.business_terms;
    const loaded: Form = {
      ...response,
      business_terms: business ? {
        ...createDefaultBusinessDocumentTerms(), ...business,
        contract_scenario: business.contract_scenario as BusinessDocumentTerms['contract_scenario'],
        payment_schedule: (business.payment_schedule || []).map((item) => ({
          share_percent: Number(item.share_percent), due_event: item.due_event as BusinessDocumentTerms['payment_schedule'][number]['due_event'],
          due_days: item.due_days ?? null, due_day_kind: item.due_day_kind as BusinessDocumentTerms['payment_schedule'][number]['due_day_kind'], note: item.note ?? null,
        })),
      } : null,
      consumer_terms: response.consumer_terms ? { ...createDefaultConsumerDocumentTerms(), ...response.consumer_terms } : null,
      act_terms: response.act_terms ? { ...createDefaultActTerms(), ...response.act_terms, claims_status: response.act_terms.claims_status as ActTerms['claims_status'] } : null,
      transport_terms: response.transport_terms ? { ...createDefaultTransportTerms(), ...response.transport_terms } : null,
    };
    form.value = loaded;
    baseline.value = structuredClone(loaded);
  } catch (failure) {
    if (active) error.value = getApiErrorMessage(failure);
  } finally {
    if (active) loading.value = false;
  }
};
void load();

const save = async () => {
  if (!form.value || saving.value || props.disabled || !Object.keys(changes.value).length) return;
  const rebuilt = rebuilds.value;
  const reset = rebuilt && form.value.has_editable_copy;
  const payload = { ...changes.value, expected_revision: form.value.revision, reset_editable_copy: reset } as ManagedDocumentDraftParameterUpdate;
  saving.value = true;
  error.value = '';
  try {
    if (reset && !await confirmDialog({
      title: 'Пересобрать рабочую копию?',
      description: 'Параметры сохранятся в этом черновике. Рабочий файл будет собран заново; ручные текстовые правки в него не перенесутся. Прежняя копия останется в Google Drive. Изменение только даты сохраняет ручные правки.',
      confirmText: 'Сохранить и пересобрать', variant: 'danger',
    })) return;
    if (!active) return;
    await ManagerDocumentSystemService.updateManagerManagedDocumentDraftParameters(props.document.id, payload);
    if (!active) return;
    emit('toast', 'Параметры черновика сохранены.', 'success');
    emit('saved', rebuilt);
  } catch (failure) {
    if (active) error.value = getApiErrorMessage(failure);
  } finally {
    if (active) saving.value = false;
  }
};
</script>

<template>
  <form class="mt-4 rounded-xl border border-brand-200 bg-slate-50 p-4 dark:border-brand-900 dark:bg-slate-900" data-testid="draft-parameters-editor" @submit.prevent="save">
    <h5 class="text-sm font-bold">Параметры черновика</h5>
    <p class="mt-1 text-xs text-slate-500">Изменения сохраняются в этот документ. Дата в готовом файле будет взята отсюда; её изменение сохраняет ручные правки.</p>
    <p v-if="loading" class="mt-3 text-sm">Загружаем параметры…</p>
    <fieldset v-if="form" :disabled="saving || disabled" class="mt-3">
      <div class="grid gap-3 sm:grid-cols-2">
        <label class="native-field"><span>Дата документа</span><input v-model="form.issue_date" type="date" class="native-input" data-testid="draft-issue-date" required /></label>
        <label class="native-field"><span>Город документа</span><input v-model="form.issue_city" class="native-input" data-testid="draft-issue-city" maxlength="160" /></label>
      </div>
      <B2BContractTermsPanel v-if="form.business_terms" :document-type="document.doc_type" :terms="form.business_terms" :order-conditions="form.order_conditions" @update-terms="form.business_terms = $event" />
      <ConsumerDocumentTermsPanel v-if="form.consumer_terms" :document-type="document.doc_type" :terms="form.consumer_terms" :proposal-total-cents="Math.round(Number(form.total_amount) * 100)" @update-terms="form.consumer_terms = $event" />
      <ActTermsPanel v-if="form.act_terms" :terms="form.act_terms" @update-terms="form.act_terms = $event" />
      <TransportTermsPanel v-if="form.transport_terms" :document-type="document.doc_type" :terms="form.transport_terms" @update-terms="form.transport_terms = $event" />
      <div v-if="form.participant_statement" class="mt-3 space-y-3">
        <label class="native-field"><span>Процедура: номер / ссылка</span><input v-model="form.participant_statement.procedure_reference" class="native-input" maxlength="1000" /></label>
        <label class="native-field"><span>Лот</span><input v-model="form.participant_statement.lot" class="native-input" maxlength="500" /></label>
        <label class="native-field"><span>Заказчик закупки</span><input v-model="form.participant_statement.buyer_name" class="native-input" maxlength="500" /></label>
        <label class="native-field"><span>Текст заявления</span><textarea v-model="form.participant_statement.declaration_text" class="native-input" rows="6" maxlength="20000" /></label>
      </div>
    </fieldset>
    <p v-if="error" class="mt-3 text-sm text-rose-700" role="alert">{{ error }}</p>
    <div class="mt-4 flex flex-wrap gap-2">
      <button v-if="form" class="native-action-primary" type="submit" data-testid="save-draft-parameters" :disabled="saving || disabled || !Object.keys(changes).length">{{ saving ? 'Сохраняем…' : 'Сохранить параметры' }}</button>
      <button class="native-action" type="button" :disabled="saving" @click="emit('close')">Отмена</button>
    </div>
  </form>
</template>

<style scoped>
.native-field { @apply flex min-w-0 flex-col gap-1.5 text-xs font-semibold text-slate-600 dark:text-slate-300; }
.native-input { @apply h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-normal text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/15 dark:border-slate-700 dark:bg-slate-900 dark:text-white; }
textarea.native-input { @apply h-auto py-2; }
.native-action { @apply inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200; }
.native-action-primary { @apply inline-flex items-center justify-center rounded-lg bg-brand-600 px-3 py-2 text-xs font-bold text-white disabled:opacity-50; }
</style>
