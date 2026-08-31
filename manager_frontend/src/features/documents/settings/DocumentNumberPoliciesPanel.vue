<script setup lang="ts">
import { reactive, watch } from 'vue';
import type { DocumentNumberPolicyItem, DocumentNumberPolicyPayload } from '../../../client';
import { NUMBER_PERIODS, NUMBER_POLICY_TYPES } from '../model/native-document-options';

const props = defineProps<{
  legalEntityId: number | null;
  items: DocumentNumberPolicyItem[];
  loading: boolean;
  savingType: string | null;
}>();

const emit = defineEmits<{
  save: [documentType: string, payload: DocumentNumberPolicyPayload];
}>();

const forms = reactive<Record<string, DocumentNumberPolicyPayload>>(Object.fromEntries(
  NUMBER_POLICY_TYPES.map((item) => [item.value, { series: '', period_mode: 'calendar_year', minimum_width: 3 }]),
));
watch(() => props.items, (items) => {
  for (const item of items) {
    forms[item.document_type] = {
      series: item.series,
      period_mode: item.period_mode,
      minimum_width: item.minimum_width,
    };
  }
}, { immediate: true, deep: true });

const preview = (payload: DocumentNumberPolicyPayload) => {
  const width = Math.min(12, Math.max(1, Number(payload.minimum_width) || 3));
  const sequence = String(1).padStart(width, '0');
  return payload.period_mode === 'calendar_year'
    ? `${payload.series || ''}${new Date().getFullYear()}-${sequence}`
    : `${payload.series || ''}${sequence}`;
};
const repeatsYear = (payload: DocumentNumberPolicyPayload) => (
  payload.period_mode === 'calendar_year' && /(?:19|20)\d{2}/.test(payload.series || '')
);
</script>

<template>
  <section class="settings-card">
    <h2 class="settings-title">Официальная нумерация</h2>
    <p class="settings-help">Внутренний CRM-ID остаётся техническим. В бухгалтерском документе появляются серия и номер из этих правил.</p>

    <div v-if="legalEntityId" class="mt-5 space-y-3">
      <div v-for="type in NUMBER_POLICY_TYPES" :key="type.value" class="grid items-end gap-3 rounded-xl border border-slate-200 p-3 dark:border-slate-700 md:grid-cols-[minmax(150px,1fr)_110px_210px_100px_auto]">
        <div class="pb-2 text-sm font-semibold text-slate-800 dark:text-slate-100">
          {{ type.label }}
          <p class="mt-1 text-xs font-normal text-slate-500">Пример: <span class="font-mono font-semibold">{{ preview(forms[type.value]!) }}</span></p>
        </div>
        <label class="settings-field"><span>Серия</span><input v-model="forms[type.value]!.series" class="settings-input" placeholder="А-" /></label>
        <label class="settings-field"><span>Период</span><select v-model="forms[type.value]!.period_mode" class="settings-input"><option v-for="period in NUMBER_PERIODS" :key="period.value" :value="period.value">{{ period.label }}</option></select></label>
        <label class="settings-field"><span>Цифр</span><input v-model.number="forms[type.value]!.minimum_width" class="settings-input" type="number" min="1" max="12" /></label>
        <button class="settings-button-secondary" type="button" :disabled="savingType === type.value" @click="emit('save', type.value, forms[type.value]!)">
          {{ savingType === type.value ? '…' : 'Сохранить' }}
        </button>
        <p v-if="repeatsYear(forms[type.value]!)" class="text-xs font-semibold text-amber-700 md:col-start-2 md:col-span-4 dark:text-amber-300">Год уже добавляется выбранным периодом. Уберите его из серии, иначе он повторится в номере.</p>
      </div>
    </div>
    <p v-else class="mt-5 text-sm text-slate-500">Сначала создайте или выберите юридическое лицо.</p>
    <div v-if="loading" class="mt-4 text-sm text-slate-500">Загружаем правила…</div>
  </section>
</template>
