<script setup lang="ts">
import { amendmentChangeAmount } from '../model/contract-amendment';
import type { ContractAmendmentTerms_Input } from '../../../client';
const model = defineModel<ContractAmendmentTerms_Input>({ required: true });
</script>

<template>
  <div class="mt-4 space-y-3" data-testid="amendment-fields">
    <p class="text-sm text-slate-600">Укажите только дополнительные работы. Черновик не меняет согласованную сумму. Выпуск зарегистрирует согласованное изменение; подпись, оплата и выполнение отдельно не подтверждаются.</p>
    <label class="field">Оборудование / объект<input v-model="model.equipment" class="input" maxlength="2000" data-testid="amendment-equipment" /></label>
    <div v-for="(work, index) in model.works" :key="index" class="grid gap-2 rounded-xl border p-3 sm:grid-cols-4" data-testid="amendment-work">
      <label class="field sm:col-span-4">Дополнительная работа<input v-model="work.title" class="input" maxlength="1500" required data-testid="amendment-work-title" /></label>
      <label class="field">Количество<input v-model="work.quantity" type="number" class="input" min="0.001" max="1000000" step="0.001" required data-testid="amendment-work-quantity" /></label>
      <label class="field">Единица<input v-model="work.unit" class="input" maxlength="40" required /></label>
      <label class="field">Цена, BYN<input v-model="work.unit_price" type="number" class="input" min="0.01" step="0.01" required data-testid="amendment-work-price" /></label>
      <button v-if="model.works.length > 1" class="self-end text-sm text-rose-700" type="button" @click="model.works.splice(index, 1)">Убрать работу</button>
    </div>
    <button v-if="model.works.length < 100" class="text-sm font-semibold text-brand-700" type="button" @click="model.works.push({ title: '', quantity: '1', unit: 'компл.', unit_price: '' })">Добавить работу</button>
    <label class="field">Сдача и приёмка<textarea v-model="model.acceptance_terms" class="input" rows="2" maxlength="4000" required /></label>
    <label class="field">Оплата<textarea v-model="model.payment_terms" class="input" rows="2" maxlength="4000" required data-testid="amendment-payment-terms" /></label>
    <p class="text-xs text-slate-500">По умолчанию сохраняются условия исходного договора. Любое отличие, включая исключение предоплаты, укажите явно.</p>
    <label class="field">Юридическое вступление в силу<textarea v-model="model.effective_terms" class="input" rows="2" maxlength="4000" required /></label>
    <p class="text-sm font-semibold" data-testid="amendment-change-total">Дополнительные работы: {{ amendmentChangeAmount(model) ?? '—' }} BYN</p>
  </div>
</template>

<style scoped>
.field { @apply flex flex-col gap-1 text-xs font-semibold text-slate-600 dark:text-slate-300; }
.input { @apply w-full rounded-lg border border-slate-200 bg-white p-2 text-sm font-normal text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white; }
</style>
