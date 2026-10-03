<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { ManagerService, type ManagerCustomerContractItemResponse } from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
const props = defineProps<{ customerId: number; documentId: number; contracts: ManagerCustomerContractItemResponse[] }>();
const emit = defineEmits<{ close: []; confirmed: [] }>();
type Review = Awaited<ReturnType<typeof ManagerService.reviewManagerCustomerReconciliationLegacyDocument>>;
const data = ref<Review | null>(null);
const loading = ref(false);
const saving = ref(false);
const error = ref('');
const form = ref({ number: '', date: '', amount: '' as string | number, contract_id: null as number | null, evidence_excerpt: '' });
async function load() {
  loading.value = true; error.value = '';
  try {
    data.value = await ManagerService.reviewManagerCustomerReconciliationLegacyDocument(props.customerId, props.documentId);
    form.value = { number: data.value.proposed_number || '', date: data.value.proposed_date || '', amount: data.value.proposed_amount ?? '', contract_id: data.value.proposed_contract_id ?? null, evidence_excerpt: '' };
  } catch(e) { error.value = getApiErrorMessage(e); }
  finally { loading.value = false; }
}
async function confirmIdentity() {
  if (!data.value || saving.value) return;
  saving.value = true; error.value = '';
  try {
    await ManagerService.confirmManagerCustomerReconciliationLegacyDocument(props.customerId, props.documentId, { ...form.value, amount: Number(form.value.amount), source_hash: data.value.source_hash });
    emit('confirmed');
  } catch(e) { error.value = getApiErrorMessage(e); }
  finally { saving.value = false; }
}
function copySelection() { const selection = window.getSelection()?.toString().trim(); if (selection && data.value?.extracted_text.includes(selection)) form.value.evidence_excerpt = selection; }
onMounted(load);
</script>
<template>
  <section class="customer-panel my-4" aria-label="Проверка старого документа">
    <div class="panel-heading"><h2>Проверить по оригиналу</h2><button class="workspace-link" type="button" :disabled="saving" @click="emit('close')">Закрыть</button></div>
    <p v-if="loading" class="muted text-sm">Читаем исходный документ…</p><p v-if="error" class="request-error" role="alert">{{ error }} <button v-if="!data" type="button" class="workspace-link" @click="load">Повторить</button></p>
    <div v-if="data" class="review-grid"><div><span class="muted text-xs">Текст оригинала · выделите подтверждающий фрагмент</span><pre class="original-text" @mouseup="copySelection" @touchend="copySelection">{{ data.extracted_text }}</pre></div><form @submit.prevent="confirmIdentity"><div class="form-grid"><label class="field-label">Официальный номер<input v-model="form.number" class="field-input" required :disabled="saving" /></label><label class="field-label">Дата документа<input v-model="form.date" class="field-input" type="date" required :disabled="saving" /></label><label class="field-label">Сумма, BYN<input v-model="form.amount" class="field-input" type="number" min="0.01" step="0.01" required :disabled="saving" /></label><label class="field-label">Договор<select v-model="form.contract_id" class="field-input" :disabled="saving"><option :value="null">Не указан</option><option v-for="contract in contracts" :key="contract.id" :value="contract.id">{{ contract.number }}</option></select></label></div><label class="field-label mt-3">Фрагмент оригинала с реквизитами<textarea v-model="form.evidence_excerpt" minlength="8" maxlength="1000" class="field-input min-h-28" required :disabled="saving" placeholder="Скопируйте фрагмент текста, по которому проверили реквизиты" /></label><p class="muted text-xs mt-3">Сохранится подтверждённое сопоставление для сверки. Содержимое оригинального файла не изменяется.</p><div class="form-actions"><button type="submit" class="btn-mini" :disabled="saving">{{ saving ? 'Сохраняем…' : 'Подтвердить реквизиты' }}</button></div></form></div>
  </section>
</template>
<style scoped src="../../styles/customer-workspace.css"></style>
<style scoped>.review-grid { display:grid;grid-template-columns:1fr 1fr;gap:18px; }.review-grid>div { min-width:0; }.original-text { white-space:pre-wrap;overflow-wrap:anywhere;max-height:450px;overflow:auto;font-size:12px;line-height:1.65;padding:14px;background:var(--mv-bg);border-radius:8px;margin-top:6px; }@media(max-width:800px){.review-grid{grid-template-columns:1fr}.original-text{max-height:240px}}</style>
