<script setup lang="ts">
import { ref, watch, computed, onBeforeUnmount } from 'vue';
import { tenderWorkflowApi, tenderStageLabels, type TenderWorkflow, type TenderIdentity, type TenderStage } from '../../services/tender-workflow';
import { getApiErrorMessage } from '../../utils/api-errors';
const props = defineProps<{ orderId: number }>();
const emit = defineEmits<{ changed: [workflow: TenderWorkflow] }>();
const workflow = ref<TenderWorkflow | null>(null);
const stage = ref<TenderStage>('announced');
const deadline = ref('');
const search = ref('');
const candidates = ref<TenderIdentity[]>([]);
const searched = ref(false);
const busy = ref(false);
const error = ref('');
const loading = ref(false);
const loadFailed = ref(false);
const editor = ref(false);
const localDate = (value?: string | null) => value ? new Date(new Date(value).getTime() + 3 * 3600000).toISOString().slice(0, 16) : '';
const date = (value: string) => new Date(value).toLocaleString('ru-BY', { timeZone: 'Europe/Minsk', dateStyle: 'medium', timeStyle: 'short' });
const apply = (result: TenderWorkflow) => {
  workflow.value = result; stage.value = result.stage || 'announced'; deadline.value = localDate(result.deadline_at);
};
let loadVersion = 0;
const load = async () => {
  const version = ++loadVersion;
  const id = props.orderId;
  workflow.value = null; candidates.value = []; error.value = ''; editor.value = false; searched.value = false;
  search.value = ''; busy.value = false; loading.value = true; loadFailed.value = false;
  try {
    const result = await tenderWorkflowApi.get(id);
    if (version === loadVersion) apply(result);
  } catch (caught) {
    if (version === loadVersion) { error.value = getApiErrorMessage(caught); loadFailed.value = true; }
  } finally {
    if (version === loadVersion) loading.value = false;
  }
};
watch(() => props.orderId, load, { immediate: true });
onBeforeUnmount(() => { loadVersion += 1; });
const act = async (callback: (id: number, isCurrent: () => boolean) => Promise<TenderWorkflow | null>) => {
  if (busy.value || loading.value) return;
  const version = loadVersion;
  const id = props.orderId;
  const isCurrent = () => version === loadVersion;
  busy.value = true; error.value = '';
  try {
    const result = await callback(id, isCurrent);
    if (result && isCurrent()) { apply(result); emit('changed', result); candidates.value = []; searched.value = false; }
  } catch (caught) {
    if (isCurrent()) error.value = getApiErrorMessage(caught);
  } finally {
    if (isCurrent()) busy.value = false;
  }
};
const save = () => act(id => tenderWorkflowApi.update(id, { stage: stage.value, deadline_at: deadline.value ? new Date(`${deadline.value}+03:00`).toISOString() : null }));
const find = async () => {
  if (busy.value || loading.value) return;
  const version = loadVersion;
  const id = props.orderId;
  busy.value = true; error.value = '';
  try {
    const result = await tenderWorkflowApi.candidates(id, search.value.trim());
    if (version === loadVersion) { candidates.value = result; searched.value = true; }
  } catch (caught) {
    if (version === loadVersion) error.value = getApiErrorMessage(caught);
  } finally {
    if (version === loadVersion) busy.value = false;
  }
};
const link = (candidate: TenderIdentity) => act(async (id, isCurrent) => {
  // The manager explicitly chooses this record as the earlier price enquiry.
  if (!candidate.stage) await tenderWorkflowApi.update(candidate.order_id, { stage: 'price_request', deadline_at: candidate.deadline_at || null });
  if (!isCurrent()) return null;
  return tenderWorkflowApi.link(id, candidate.order_id);
});
const hasContext = computed(() => Boolean(workflow.value?.stage || workflow.value?.deadline_at || workflow.value?.price_enquiry || workflow.value?.publications?.length));
const canLink = computed(() => !workflow.value?.price_enquiry && !workflow.value?.publications?.length
  && !['price_request', 'price_sent'].includes(workflow.value?.stage || ''));
const orderUrl = (id: number) => `/manager/orders/kanban?orderId=${id}`;
</script>
<template>
  <section class="tender-workflow" :class="{ 'tender-workflow--compact': !hasContext && !editor }" aria-label="Этапы закупки" :aria-busy="loading || busy">
    <p v-if="loading" role="status">Загружаем этапы закупки…</p>
    <template v-else-if="workflow">
    <template v-if="hasContext">
    <h3>Этап закупки<span v-if="workflow?.stage">: {{ tenderStageLabels[workflow.stage] }}</span></h3>
    <p v-if="workflow?.deadline_at">Срок текущего этапа: {{ date(workflow.deadline_at) }} · Минск</p>
    <p v-else>Срок текущего этапа не указан</p>
    <template v-if="workflow?.price_enquiry">
      <p>Предыдущий запрос цены: <a :href="orderUrl(workflow.price_enquiry.order_id)">#{{ workflow.price_enquiry.order_id }} · {{ workflow.price_enquiry.title || 'Открыть обращение' }}</a><span v-if="workflow.price_enquiry.external_id"> · ID {{ workflow.price_enquiry.external_id }}</span><span v-if="workflow.price_enquiry.archived"> · в архиве</span></p>
      <button type="button" :disabled="busy" @click="act(id => tenderWorkflowApi.unlink(id))">Снять связь с запросом цены</button>
    </template>
    <p v-for="publication in workflow?.publications || []" :key="publication.order_id">Публикация: <a :href="orderUrl(publication.order_id)">#{{ publication.order_id }} · {{ publication.title || 'Открыть закупку' }}</a><span v-if="publication.external_id"> · ID {{ publication.external_id }}</span><span v-if="publication.stage"> · {{ tenderStageLabels[publication.stage] }}</span><span v-if="publication.deadline_at"> · до {{ date(publication.deadline_at) }} (Минск)</span><span v-if="publication.archived"> · в архиве</span></p>
    </template>
    <button type="button" :aria-expanded="editor" :aria-controls="`tender-editor-${orderId}`" @click="editor = !editor">{{ editor ? 'Скрыть этапы и связь' : hasContext ? 'Этапы и связь с запросом цены' : 'Настроить этапы закупки' }}</button>
    <div v-if="editor" :id="`tender-editor-${orderId}`">
      <form @submit.prevent="save">
        <label :for="`tender-stage-${orderId}`">Этап<select :id="`tender-stage-${orderId}`" v-model="stage" :disabled="busy" @change="deadline = ''"><option v-for="(label, value) in tenderStageLabels" :key="value" :value="value">{{ label }}</option></select></label>
        <label :for="`tender-deadline-${orderId}`">Срок этого этапа (Минск)<input :id="`tender-deadline-${orderId}`" v-model="deadline" type="datetime-local" :disabled="busy" /></label>
        <button type="submit" :disabled="busy">Сохранить этап и срок</button>
      </form>
      <form v-if="canLink" @submit.prevent="find">
        <label :for="`tender-search-${orderId}`">Найти предыдущий запрос цены<input :id="`tender-search-${orderId}`" v-model="search" placeholder="Номер, название или заказчик" :disabled="busy" maxlength="200" /></label><button type="submit" :disabled="busy">Найти</button>
        <p>Поиск включает принятые в работу и архивные обращения. Выбранное обращение будет отмечено как запрос цены; документы и предложения сохранятся в каждом обращении.</p>
        <p v-if="searched && !candidates.length">Подходящих обращений не найдено</p>
        <div v-for="candidate in candidates" :key="candidate.order_id" class="candidate"><a :href="orderUrl(candidate.order_id)">#{{ candidate.order_id }} · {{ candidate.title || 'Без названия' }}</a><span v-if="candidate.external_id"> · ID {{ candidate.external_id }}</span><span v-if="candidate.archived"> · в архиве</span><button type="button" :disabled="busy" @click="link(candidate)">Связать как запрос цены</button></div>
      </form>
      <details v-if="workflow.history?.length"><summary>История этапов и связей</summary><p v-for="event in workflow.history" :key="event.id">{{ date(event.created_at) }} · {{ event.actor }} · {{ event.note }}</p></details>
    </div>
    </template>
    <p v-if="error" role="alert" class="error">{{ loadFailed ? 'Не удалось загрузить этапы закупки. ' : '' }}{{ error }}</p>
    <button v-if="loadFailed" type="button" :disabled="loading" @click="load">Повторить загрузку</button>
  </section>
</template>
<style scoped>
.tender-workflow { margin-top: 14px; padding: 12px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 12px; }
.tender-workflow--compact { display: flex; align-items: center; flex-wrap: wrap; gap: 4px 10px; margin-top: 8px; padding: 0; border: 0; min-height: 32px; }
.tender-workflow--compact p { margin: 0; }
button:focus-visible, input:focus-visible, select:focus-visible, a:focus-visible { outline: 2px solid #0284c7; outline-offset: 2px; }
h3 { font-weight: 600; margin-bottom: 8px; }
p { margin: 6px 0; } a { text-decoration: underline; } button { padding: 7px; text-decoration: underline; } button:disabled { opacity: .5; }
form { display: flex; flex-wrap: wrap; align-items: end; gap: 10px; margin: 12px 0; } form p { width: 100%; }
label { display: grid; gap: 4px; } input,select { padding: 7px; border: 1px solid #94a3b8; border-radius: 5px; background: transparent; }
.candidate { width: 100%; } .error { color: #b91c1c; }
</style>
