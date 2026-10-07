<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue';
import { ApiError, ManagerMaintenanceObservationsService as api, ManagerDocumentSystemService,
  type DocumentLegalEntityItem, type MaintenanceDefectActItem, type MaintenanceActSelectedObservation,
  type PrepareMaintenanceDefectAct } from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
import { openNativeDocumentPreview } from '../../features/documents/integrations/native-document-preview';
import { managedDocumentStatus } from '../../features/documents/model/native-document-options';

const props = defineProps<{ orderId: number; selected: MaintenanceActSelectedObservation[] }>();
const emit = defineEmits<{ lock: [value: boolean]; refresh: [] }>();
const issuers = ref<DocumentLegalEntityItem[]>([]);
const issuerId = ref<number | null>(null);
const localDate = () => { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10); };
const issueDate = ref(localDate());
const replacementId = ref<number | null>(null);
const acts = ref<MaintenanceDefectActItem[]>([]);
const total = ref(0);
const loading = ref(false);
const busy = ref(false);
const pending = ref<PrepareMaintenanceDefectAct | null>(null);
const error = ref('');
const message = ref('');
let version = 0;
const formOwner = () => `maintenance-act-${props.orderId}`;
async function load(more = false) {
  const request = version;
  loading.value = true;
  try {
    const [list, entities] = await Promise.all([
      api.listManagerMaintenanceDefectActs(props.orderId, 50, more ? acts.value.length : 0),
      ManagerDocumentSystemService.listManagerDocumentLegalEntities(),
    ]);
    if (request !== version) return;
    acts.value = more ? [...acts.value, ...list.items] : list.items;
    total.value = list.total;
    issuers.value = entities.items.filter((item) => item.status === 'active');
    issuerId.value ??= issuers.value.find((item) => item.is_default)?.id ?? issuers.value[0]?.id ?? null;
  } catch (cause) { if (request === version) error.value = getApiErrorMessage(cause); }
  finally { if (request === version) loading.value = false; }
}
async function prepare() {
  if (busy.value || (!pending.value && (!issuerId.value || !props.selected.length || !issueDate.value))) return;
  const request = version;
  pending.value ||= { command_key: crypto.randomUUID(), legal_entity_id: issuerId.value!, issue_date: issueDate.value,
    observations: props.selected.map((item) => ({ ...item })), replaces_document_id: replacementId.value };
  busy.value = true; emit('lock', true); error.value = ''; message.value = '';
  try {
    const result = await api.prepareManagerMaintenanceDefectAct(props.orderId, pending.value);
    if (request !== version) return;
    pending.value = null;
    message.value = `Черновик дефектного акта #${result.document_id} подготовлен. Выпуск и отправка доступны в документах продолжения #${result.continuation_order_id}.`;
    replacementId.value = null;
    await load();
  } catch (cause) {
    if (request !== version) return;
    if (cause instanceof ApiError && cause.status >= 400 && cause.status < 500) pending.value = null;
    error.value = getApiErrorMessage(cause);
    if (pending.value) error.value += ' Повторите подготовку: команда сохранена, второй акт не появится.';
  } finally {
    if (request === version) { busy.value = false; emit('lock', Boolean(pending.value)); }
  }
}
async function preview(documentId: number) {
  try { await openNativeDocumentPreview(documentId); }
  catch (cause) { error.value = getApiErrorMessage(cause); }
}
function refresh() { if (!pending.value && !busy.value) { error.value = ''; emit('refresh'); void load(); } }
watch(() => props.orderId, () => {
  version++; acts.value = []; total.value = 0; error.value = ''; message.value = ''; pending.value = null;
  busy.value = false; replacementId.value = null; issuerId.value = null; emit('lock', false); void load();
}, { immediate: true });
onBeforeUnmount(() => { version++; emit('lock', false); });
</script>

<template>
  <section aria-label="Дефектные акты ТО" class="space-y-3 rounded-lg border border-gray-200 p-3 dark:border-slate-600">
    <h3 class="font-semibold text-gray-950 dark:text-white">Дефектный акт по выбранным замечаниям</h3>
    <p class="text-sm text-gray-600 dark:text-slate-300">Выберите замечания этого ТО. Подготовка сохраняет черновик и связанную карточку переговоров; работы и отправку клиенту запускают отдельными действиями.</p>
    <fieldset :disabled="busy || Boolean(pending)" class="grid min-w-0 gap-3 sm:grid-cols-2">
      <label class="block text-sm">Исполнитель<select :form="formOwner()" v-model="issuerId" data-testid="act-issuer" class="mt-1 w-full min-w-0 rounded-lg border border-gray-300 bg-white p-2 dark:border-slate-600 dark:bg-slate-900">
        <option :value="null">Выберите юридическое лицо</option><option v-for="issuer in issuers" :key="issuer.id" :value="issuer.id">{{ issuer.display_name }}</option>
      </select></label>
      <label class="block text-sm">Дата акта<input :form="formOwner()" v-model="issueDate" data-testid="act-date" type="date" class="mt-1 w-full min-w-0 rounded-lg border border-gray-300 bg-white p-2 dark:border-slate-600 dark:bg-slate-900" /></label>
      <label v-if="acts.some((act) => ['issued', 'sent', 'signed'].includes(act.status))" class="block text-sm sm:col-span-2">Версия документа<select :form="formOwner()" v-model="replacementId" data-testid="act-replacement" class="mt-1 w-full rounded-lg border border-gray-300 bg-white p-2 dark:border-slate-600 dark:bg-slate-900">
        <option :value="null">Новый документ</option><option v-for="act in acts.filter((item) => ['issued', 'sent', 'signed'].includes(item.status))" :key="act.document_id" :value="act.document_id">Новая версия вместо акта #{{ act.document_id }}</option>
      </select></label>
    </fieldset>
    <p v-if="!loading && !issuers.length" class="text-sm text-amber-700 dark:text-amber-300">Добавьте активное юридическое лицо в настройках документов.</p>
    <div class="flex flex-wrap gap-2">
      <button type="button" data-testid="prepare-act" class="act-button" :disabled="busy || loading || (!pending && (!selected.length || !issuerId || !issueDate))" @click="prepare">{{ busy ? 'Подготавливаем…' : pending ? 'Повторить подготовку' : `Подготовить акт (${selected.length})` }}</button>
      <button type="button" class="act-button" :disabled="busy || Boolean(pending)" @click="refresh">Обновить замечания и акты</button>
    </div>
    <p v-if="error" role="alert" class="break-words text-sm text-red-700 dark:text-red-300">{{ error }}</p>
    <p v-if="message" role="status" class="break-words text-sm text-green-700 dark:text-green-300">{{ message }}</p>
    <ul class="space-y-2">
      <li v-for="act in acts" :key="act.preparation_id" class="space-y-2 rounded-lg bg-gray-50 p-3 dark:bg-slate-900/40">
        <p class="text-sm font-medium">Дефектный акт #{{ act.document_id }} · {{ managedDocumentStatus(act.status) }}</p>
        <p class="break-words text-xs text-gray-500">{{ act.observations.map((item) => `Замечание #${item.observation_id} · версия ${item.expected_version}`).join('; ') }}</p>
        <div class="flex flex-wrap gap-2">
          <button v-if="act.status === 'draft'" type="button" class="act-button" @click="preview(act.document_id)">Предпросмотр черновика</button>
          <a :href="`/manager/orders/kanban?orderId=${act.continuation_order_id}`" target="_blank" rel="noopener" class="act-button">Документы продолжения #{{ act.continuation_order_id }}</a>
        </div>
      </li>
    </ul>
    <button v-if="acts.length < total" type="button" class="act-button" :disabled="loading" @click="load(true)">Показать ещё акты</button>
  </section>
</template>

<style scoped>
.act-button { @apply inline-flex items-center justify-center rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200; }
</style>
