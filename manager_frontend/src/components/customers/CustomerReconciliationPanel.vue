<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { ManagerService, ManagerContractsService, type ManagerCustomerReconciliationResponse, type ManagerCustomerContractItemResponse } from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
import MoneyAmount from '../money/MoneyAmount.vue';
import CustomerLegacyDocumentReview from './CustomerLegacyDocumentReview.vue';
const props = defineProps<{ customerId: number }>();
const toDate = (date: Date) => `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
const dateFrom = ref(toDate(new Date(new Date().getFullYear(),0,1)));
const dateTo = ref(toDate(new Date()));
const contractId = ref<number | null>(null);
const contracts = ref<ManagerCustomerContractItemResponse[]>([]);
const data = ref<ManagerCustomerReconciliationResponse | null>(null);
const loading = ref(false);
const creating = ref(false);
const error = ref('');
const contractError = ref('');
const documentUrl = ref('');
const reviewDocumentId = ref<number | null>(null);
const relationIds = ref<number[]>([]);
const relationReason = ref('');
const relationSaving = ref(false);
const loadedKey = ref('');
const filterKey = computed(() => `${dateFrom.value}/${dateTo.value}/${contractId.value ?? ''}`);
const stale = computed(() => loadedKey.value !== filterKey.value);
const money = (n: number | undefined) => Number(n ?? 0).toLocaleString('ru-RU',{minimumFractionDigits:2, maximumFractionDigits:2});
const day = (value: string) => new Date(value).toLocaleDateString('ru-RU');
const balanceLabel = computed(() => !data.value ? 'Остаток' : (data.value.closing_balance ?? 0) > 0 ? 'Клиент должен нам' : (data.value.closing_balance ?? 0) < 0 ? 'Переплата / аванс клиента' : 'Расчёты закрыты');
const movements = computed(() => {
  if (!data.value) return [];
  const docs = (data.value.documents || []).map(item => ({ key: `order-${item.order_id}-${item.date}-${item.basis}`, date: item.date, label: item.basis, debit: item.amount, credit: 0, documents: item.documents || [], orderId: item.order_id }));
  const payments = (data.value.payments || []).map(item => ({ key: `payment-${item.payment_id}`, date: item.date, label: item.payment_document_raw || (item.payment_document_number ? `Платёжное поручение № ${item.payment_document_number}` : `Оплата #${item.payment_id}`), debit: 0, credit: item.amount, documents: [], orderId: item.order_id }));
  let balance = Math.round((data.value.opening_balance ?? 0)*100);
  return [...docs,...payments].sort((a,b) => a.date.localeCompare(b.date) || a.key.localeCompare(b.key)).map(item => { balance += Math.round(item.debit*100)-Math.round(item.credit*100); return {...item,balance: balance/100}; });
});
async function load() {
  if (loading.value) return;
  if (!dateFrom.value || !dateTo.value || dateFrom.value > dateTo.value) { error.value = 'Укажите корректный период: начало не позже окончания'; return; }
  loading.value = true; error.value = ''; documentUrl.value = '';
  const key = filterKey.value;
  try { const result = await ManagerService.getManagerCustomerReconciliation(props.customerId,dateFrom.value,dateTo.value,contractId.value); if (key === filterKey.value) { data.value = result; loadedKey.value = key; } }
  catch (e) { error.value = getApiErrorMessage(e); data.value = null; }
  finally { loading.value = false; }
}
async function loadContracts() { try { contracts.value = (await ManagerContractsService.getManagerCustomerContracts(props.customerId)).items; } catch(e) { contractError.value = getApiErrorMessage(e); } }
async function create() {
  if (creating.value || stale.value || !data.value?.ready_for_generation) return;
  creating.value = true; error.value = '';
  try { const result = await ManagerService.createManagerCustomerReconciliationDocument(props.customerId,dateFrom.value,dateTo.value,contractId.value); documentUrl.value = result.edit_url; }
  catch(e) {
    error.value = getApiErrorMessage(e);
    const warnings = (e as { body?: { detail?: { warnings?: ManagerCustomerReconciliationResponse['warnings'] } } }).body?.detail?.warnings;
    if (Array.isArray(warnings) && data.value) data.value = { ...data.value, ready_for_generation: false, warnings };
  }
  finally { creating.value = false; }
}
async function confirmRelation(relation: 'same' | 'separate') {
  if (relationSaving.value || !relationReason.value.trim()) return;
  relationSaving.value = true; error.value = '';
  try {
    await ManagerService.confirmManagerCustomerReconciliationEventRelation(props.customerId, { document_ids: relationIds.value, relation, reason: relationReason.value.trim() });
    relationIds.value = []; relationReason.value = '';
    await load();
  } catch (e) { error.value = getApiErrorMessage(e); }
  finally { relationSaving.value = false; }
}
function reviewed() { reviewDocumentId.value = null; void load(); }
onMounted(() => { void load(); void loadContracts(); });
</script>
<template>
  <section class="customer-section">
    <div class="reconciliation-toolbar"><h2 class="text-base font-bold">Взаиморасчёты</h2><div class="period"><label class="field-label">С<input v-model="dateFrom" class="field-input" type="date" :disabled="loading || creating" /></label><label class="field-label">По<input v-model="dateTo" class="field-input" type="date" :disabled="loading || creating" /></label><label class="field-label">Договор<select v-model="contractId" class="field-input" :disabled="loading || creating"><option :value="null">Все договоры</option><option v-for="contract in contracts" :key="contract.id" :value="contract.id">{{ contract.number }}</option></select></label><button class="btn-mini-outline" type="button" :disabled="loading || creating" @click="load">{{ loading ? 'Загрузка…' : 'Показать' }}</button></div></div>
    <p v-if="contractError" class="request-error">Не удалось загрузить договоры: {{ contractError }} <button class="workspace-link" type="button" @click="loadContracts">Повторить</button></p>
    <p v-if="error" class="request-error" role="alert">{{ error }}</p><p v-if="loading && !data" class="empty">Собираем движения…</p>
    <template v-if="data">
      <p v-if="stale" class="review-warning">Период или договор изменены. Нажмите «Показать», чтобы обновить расчёт.</p>
      <div class="balance-grid" :class="{'opacity-50': stale}"><div><span>На начало</span><strong><MoneyAmount :value="data.opening_balance" :formatted-value="money(data.opening_balance)" /></strong></div><div><span>Начислено</span><strong><MoneyAmount :value="data.documents_total" :formatted-value="money(data.documents_total)" /></strong></div><div><span>Оплачено</span><strong><MoneyAmount :value="data.payments_total" :formatted-value="money(data.payments_total)" /></strong></div><div><span>{{ balanceLabel }}</span><strong><MoneyAmount :value="data.closing_balance == null ? data.closing_balance : Math.abs(data.closing_balance)" :formatted-value="money(Math.abs(data.closing_balance ?? 0))" /></strong></div></div>
      <div v-if="data.warnings?.length" class="review-warning"><strong>Расчёт требует проверки</strong><ul><li v-for="(warning,index) in data.warnings" :key="`${warning.code}-${index}`">{{ warning.message }} <button v-if="warning.document_id && warning.can_review_legacy" type="button" class="workspace-link" @click="reviewDocumentId = warning.document_id">Проверить оригинал</button><button v-if="warning.related_document_ids?.length" type="button" class="workspace-link" @click="relationIds = warning.related_document_ids; relationReason = ''">Одна поставка или разные?</button><a v-else-if="!warning.can_review_legacy && warning.order_id" :href="`/manager/orders/kanban?orderId=${warning.order_id}`" class="workspace-link">Открыть заказ</a></li></ul></div>
      <div v-if="relationIds.length" class="review-warning">
        <strong>Документы {{ relationIds.map(id => `#${id}`).join(', ') }}</strong>
        <p class="my-2">Сверьте оригиналы по ссылкам в таблице: описывают ли они одну поставку? При выборе разных поставок обе суммы войдут в расчёт.</p>
        <label class="field-label">Основание решения<input v-model="relationReason" class="field-input" maxlength="500" :disabled="relationSaving" placeholder="Что подтверждает связь или различие документов" /></label>
        <div class="flex flex-wrap gap-3 mt-3"><button class="btn-mini" type="button" :disabled="relationSaving || relationReason.trim().length < 8" @click="confirmRelation('same')">Одна поставка</button><button class="btn-mini-outline" type="button" :disabled="relationSaving || relationReason.trim().length < 8" @click="confirmRelation('separate')">Разные поставки</button><button class="workspace-link" type="button" :disabled="relationSaving" @click="relationIds = []">Отмена</button></div>
      </div>
      <CustomerLegacyDocumentReview v-if="reviewDocumentId" :key="reviewDocumentId" :customer-id="customerId" :document-id="reviewDocumentId" :contracts="contracts" @close="reviewDocumentId = null" @confirmed="reviewed" />
      <div class="ledger-wrap"><table class="ledger"><thead><tr><th>Дата</th><th>Основание</th><th class="number">Начислено</th><th class="number">Оплачено</th><th class="number">Остаток</th></tr></thead><tbody><tr v-for="row in movements" :key="row.key"><td class="whitespace-nowrap">{{ day(row.date) }}</td><td><div>{{ row.label }}</div><div class="flex flex-wrap gap-2 mt-1"><a :href="`/manager/orders/kanban?orderId=${row.orderId}`" class="workspace-link text-xs">Заказ #{{ row.orderId }}</a><template v-for="doc in row.documents" :key="doc.id"><a v-if="doc.edit_url" :href="doc.edit_url" target="_blank" rel="noopener noreferrer" class="workspace-link text-xs">Оригинал № {{ doc.number }} ↗</a></template></div></td><td class="number"><MoneyAmount v-if="row.debit" :value="row.debit" :formatted-value="money(row.debit)" /><template v-else>—</template></td><td class="number"><MoneyAmount v-if="row.credit" :value="row.credit" :formatted-value="money(row.credit)" /><template v-else>—</template></td><td class="number"><MoneyAmount :value="row.balance" :formatted-value="money(row.balance)" /></td></tr><tr v-if="!movements.length"><td colspan="5" class="empty">В этом периоде движений нет.</td></tr></tbody></table></div>
      <div class="flex flex-wrap justify-between gap-3 items-center mt-4"><p class="muted text-xs">{{ data.ready_for_generation ? 'Проверьте движения перед созданием акта.' : 'Финальный акт доступен после устранения указанных расхождений.' }}</p><div class="flex gap-3 items-center"><a v-if="documentUrl && !stale" class="workspace-link" :href="documentUrl" target="_blank" rel="noopener noreferrer">Открыть акт ↗</a><button class="btn-mini" type="button" :disabled="loading || creating || stale || !data.ready_for_generation" @click="create">{{ creating ? 'Создаём…' : 'Создать акт сверки' }}</button></div></div>
    </template>
  </section>
</template>
<style scoped src="../../styles/customer-workspace.css"></style>
<style scoped>
.reconciliation-toolbar { display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap; }.period { display:flex; align-items:end; gap:8px; flex-wrap:wrap; }.period label { flex:1; min-width:125px; }.balance-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); border:1px solid var(--mv-border); border-radius:10px; background:var(--mv-surface); margin:16px 0; }.balance-grid>div { padding:14px; border-right:1px solid var(--mv-border); }.balance-grid>div:last-child { border:0; }.balance-grid>div>span { display:block; font-size:11px; color:var(--mv-text-muted); }.balance-grid strong { display:block; font-size:20px; margin-top:5px; font-variant-numeric:tabular-nums; }.review-warning { padding:12px; margin:12px 0; border:1px solid #d5a65b; border-radius:8px; color:var(--mv-text); background:var(--mv-surface); font-size:13px; }.review-warning li { margin-top:7px; }.ledger-wrap { overflow:auto; border:1px solid var(--mv-border); border-radius:10px; background:var(--mv-surface); }.ledger { width:100%; min-width:650px; border-collapse:collapse; font-size:13px; }.ledger th { color:var(--mv-text-muted); font-size:11px; font-weight:500; text-align:left; }.ledger td,.ledger th { padding:12px; border-bottom:1px solid var(--mv-border); }.ledger .number { text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }@media(max-width:700px) {.balance-grid{grid-template-columns:1fr 1fr}.balance-grid>div{padding:10px}.balance-grid strong{font-size:18px}.period{width:100%}}
@media(max-width:420px) {.balance-grid{grid-template-columns:1fr}.balance-grid>div{border-right:0;border-bottom:1px solid var(--mv-border)}}
</style>
