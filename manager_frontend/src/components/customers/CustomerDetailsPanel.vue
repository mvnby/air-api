<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { ManagerCatalogCustomerItemResponse } from '../../client';
import { api } from '../../api';
import CustomerLegalDetails from './CustomerLegalDetails.vue';
import AddressSuggestInput from '../ui/AddressSuggestInput.vue';
import { buildCustomerPatchPayload, defaultSigningMode, normalizeCustomerPartyType, normalizeCustomerSigningMode, validateCustomerProfileForm, customerPartyLabel, type CustomerForm, type CustomerPartyType } from './customer-profile-form';
import { useB2BLookup } from '../../composables/useB2BLookup';
import { normalizeIban, normalizeUnp } from '../../utils/legal-requisites';
import { getApiErrorMessage, parseApiFieldErrors } from '../../utils/api-errors';
import { notify } from '../../services/ui-feedback';

const props = defineProps<{ customer: ManagerCatalogCustomerItemResponse }>();
const emit = defineEmits<{ updated: [customer: ManagerCatalogCustomerItemResponse]; dirty: [value: boolean] }>();
function toForm(item: ManagerCatalogCustomerItemResponse): CustomerForm {
  const type = normalizeCustomerPartyType(item.type);
  return { name: item.name || '', phone: item.phone || '', email: item.email || '', type, city: item.city || '', inn: item.inn || '', kpp: item.kpp || '', full_legal_name: item.full_legal_name || '', legal_address: item.legal_address || '', actual_address: item.actual_address || '', bank_name: item.bank_name || '', bic: item.bic || '', iban: item.iban || '', signer_position: item.signer_position || '', signer_name: item.signer_name || '', acting_basis: item.acting_basis || '', signing_mode: normalizeCustomerSigningMode(type, item.signing_mode) };
}
const form = ref(toForm(props.customer));
const baseline = ref(toForm(props.customer));
const editing = ref(false);
const saving = ref(false);
const error = ref('');
const serverErrors = ref<Record<string, string>>({});
const ibanError = ref('');
const { lookupCompany, lookupBank, isEgrLoading, isBankLoading } = useB2BLookup();
const diff = computed(() => Object.fromEntries((Object.keys(form.value) as (keyof CustomerForm)[]).map((key) => [key, form.value[key] !== baseline.value[key]])) as Record<keyof CustomerForm, boolean>);
const dirty = computed(() => editing.value && Object.values(diff.value).some(Boolean));
watch(dirty, value => emit('dirty', value));
watch(() => props.customer, item => { if (!editing.value) { form.value = toForm(item); baseline.value = toForm(item); } });
function beginEdit() { baseline.value = toForm(props.customer); form.value = { ...baseline.value }; editing.value = true; error.value = ''; serverErrors.value = {}; }
function cancel() { form.value = toForm(props.customer); editing.value = false; error.value = ''; serverErrors.value = {}; }
function setType(type: CustomerPartyType) { form.value.type = type; form.value.signing_mode = defaultSigningMode(type); }
const fieldClass = (key: keyof CustomerForm) => ({ 'field-input': true, changed: diff.value[key], 'border-red-500': Boolean(serverErrors.value[key]) });
async function onInnBlur() {
  form.value.inn = normalizeUnp(form.value.inn);
  if (form.value.inn.length !== 9) return;
  const company = await lookupCompany(form.value.inn);
  if (company) { form.value.full_legal_name ||= company.fullLegalName || ''; form.value.legal_address ||= company.legalAddress || ''; }
}
async function onIbanBlur() {
  form.value.iban = normalizeIban(form.value.iban);
  if (form.value.iban.length < 15) return;
  const bank = await lookupBank(form.value.iban);
  if (bank) { form.value.bank_name ||= bank.bankName || ''; form.value.bic ||= bank.bic || ''; }
}
async function save() {
  if (saving.value || !dirty.value) return;
  error.value = '';
  // Contact validation belongs to the independently editable contact form.
  const validation = validateCustomerProfileForm({ ...form.value, phone: '', email: '' }, true);
  serverErrors.value = { ...validation.fieldErrors };
  ibanError.value = validation.ibanError;
  if (!validation.valid) { error.value = validation.issues.join('; '); return; }
  saving.value = true;
  try {
    const updated = await api.patchManagerCustomer(props.customer.id, buildCustomerPatchPayload(form.value, diff.value));
    editing.value = false; form.value = toForm(updated); baseline.value = toForm(updated);
    emit('updated', updated); emit('dirty', false); notify('Реквизиты сохранены', 'success');
  } catch (e) { error.value = getApiErrorMessage(e); serverErrors.value = parseApiFieldErrors(e, Object.keys(form.value)).fieldErrors; }
  finally { saving.value = false; }
}
</script>
<template>
  <section class="customer-panel customer-details">
    <div class="panel-heading"><h2>Реквизиты</h2><button v-if="!editing" class="workspace-link" type="button" @click="beginEdit">Изменить</button><span v-else class="badge">Редактирование</span></div>
    <p v-if="error" class="request-error" role="alert">{{ error }}</p>
    <form @submit.prevent="save">
      <div v-if="editing" class="space-y-3 mb-4">
        <label class="field-label">Название или ФИО<input v-model="form.name" :class="fieldClass('name')" required /></label>
        <div class="flex gap-1 rounded-lg bg-[var(--mv-bg)] p-1" aria-label="Тип клиента"><button v-for="type in (['individual', 'individual_entrepreneur', 'company'] as const)" :key="type" type="button" class="flex-1 rounded px-2 py-1.5 text-xs" :class="form.type === type ? 'bg-[var(--mv-surface)] text-brand-600 font-semibold' : 'muted'" :aria-pressed="form.type === type" @click="setType(type)">{{ customerPartyLabel(type) }}</button></div>
        <label v-if="form.type !== 'individual'" class="field-label">УНП<input v-model="form.inn" :class="fieldClass('inn')" inputmode="numeric" maxlength="9" @blur="onInnBlur" /><span v-if="isEgrLoading">Проверяем УНП…</span></label>
        <label v-if="form.type !== 'individual' && form.kpp" class="field-label">КПП<input v-model="form.kpp" :class="fieldClass('kpp')" /></label>
        <AddressSuggestInput v-if="form.type === 'individual'" v-model="form.actual_address" placeholder="Адрес объекта / доставки" :input-class="fieldClass('actual_address')" :error="serverErrors.actual_address" />
      </div>
      <dl v-else class="identity"><div><dt>Название</dt><dd>{{ customer.name }}</dd></div><div v-if="customer.inn"><dt>УНП</dt><dd>{{ customer.inn }}</dd></div><div v-if="customer.type === 'individual'"><dt>Адрес</dt><dd>{{ customer.actual_address || customer.last_delivery_address || '—' }}</dd></div></dl>
      <CustomerLegalDetails :customer="form" :editing="editing" :field-class="fieldClass" :iban-error="ibanError" :is-bank-loading="isBankLoading" :server-errors="serverErrors" :last-delivery-address="customer.last_delivery_address || ''" @update:customer="form = $event" @iban-blur="onIbanBlur" />
      <div v-if="editing" class="form-actions"><button type="button" class="btn-mini-outline" :disabled="saving" @click="cancel">Отмена</button><button type="submit" class="btn-mini" :disabled="saving || !dirty">{{ saving ? 'Сохраняем…' : 'Сохранить' }}</button></div>
    </form>
  </section>
</template>
<style scoped src="../../styles/customer-workspace.css"></style>
<style scoped>
.identity { font-size: 13px; margin-bottom: 12px; }.identity div { display: grid; grid-template-columns: 86px minmax(0,1fr); gap: 10px; margin: 7px 0; }.identity dt { color: var(--mv-text-muted); }.identity dd { overflow-wrap: anywhere; }
.customer-details :deep(article) { border: 0; padding: 0; box-shadow: none; border-radius: 0; }.customer-details :deep(article h2) { font-size: 12px; letter-spacing: 0; text-transform: none; margin-top: 14px; }.customer-details :deep(.detail-value) { display: grid; grid-template-columns: 110px minmax(0,1fr); gap: 10px; font-size: 13px; }.customer-details :deep(.detail-value span) { color: var(--mv-text-muted); }.customer-details :deep(.detail-value strong) { font-weight: 500; overflow-wrap: anywhere; }
</style>
