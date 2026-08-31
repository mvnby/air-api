<script setup lang="ts">
import { computed } from 'vue';
import type { BusinessDocumentTerms, PaymentScheduleItem } from '../model/business-document-terms';

type PaymentMode = 'full_prepayment' | 'equipment_prepayment' | 'postpayment' | 'custom';

const props = defineProps<{ terms: BusinessDocumentTerms }>();
const emit = defineEmits<{ updateTerms: [terms: BusinessDocumentTerms] }>();

const modes: Array<{ value: PaymentMode; label: string; note: string }> = [
  { value: 'full_prepayment', label: '100% предоплата', note: 'Оплата до поставки или начала работ' },
  { value: 'equipment_prepayment', label: 'Аванс за оборудование', note: 'Остаток после выполнения работ' },
  { value: 'postpayment', label: 'Оплата после работ', note: 'Оплата в согласованный срок' },
  { value: 'custom', label: 'Свой график', note: 'Разбейте сумму на части ниже' },
];

const mode = computed<PaymentMode>(() => {
  const schedule = props.terms.payment_schedule;
  if (schedule.length === 1 && schedule[0]?.share_percent === 100 && schedule[0].due_event.startsWith('before_')) return 'full_prepayment';
  if (schedule.length === 2 && schedule[0]?.due_event === 'before_supply' && schedule[1]?.due_event === 'after_acceptance') return 'equipment_prepayment';
  if (schedule.length === 1 && ['after_supply', 'after_work', 'after_acceptance'].includes(schedule[0]?.due_event || '')) return 'postpayment';
  return 'custom';
});
const update = (paymentSchedule: PaymentScheduleItem[]) => emit('updateTerms', {
  ...props.terms,
  payment_schedule: paymentSchedule,
});
const setMode = (next: PaymentMode) => {
  const supplyScenario = ['supply', 'supply_installation'].includes(props.terms.contract_scenario || '');
  if (next === 'full_prepayment') update([{ share_percent: 100, due_event: supplyScenario ? 'before_supply' : 'before_work', due_days: null, due_day_kind: 'banking', note: null }]);
  if (next === 'equipment_prepayment') update([
    { share_percent: 50, due_event: 'before_supply', due_days: null, due_day_kind: 'banking', note: 'Предоплата за оборудование' },
    { share_percent: 50, due_event: 'after_acceptance', due_days: null, due_day_kind: 'banking', note: 'После подписания акта' },
  ]);
  if (next === 'postpayment') update([{ share_percent: 100, due_event: 'after_acceptance', due_days: 5, due_day_kind: 'banking', note: 'После подписания акта' }]);
  if (next === 'custom') update([
    { share_percent: 50, due_event: 'before_work', due_days: null, due_day_kind: 'banking', note: null },
    { share_percent: 50, due_event: 'after_acceptance', due_days: null, due_day_kind: 'banking', note: null },
  ]);
};
const updateItem = (index: number, changes: Partial<PaymentScheduleItem>) => {
  update(props.terms.payment_schedule.map((item, itemIndex) => (
    itemIndex === index ? { ...item, ...changes } : item
  )));
};
const updateNumber = (index: number, field: 'share_percent' | 'due_days', event: Event) => {
  const raw = (event.target as HTMLInputElement).value;
  const value = raw === '' ? null : Number(raw);
  if (field === 'share_percent') {
    if (value === null || !Number.isFinite(value)) return;
    updateItem(index, { share_percent: value });
    return;
  }
  updateItem(index, { due_days: Number.isFinite(value) ? value : null });
};
const addItem = () => update([
  ...props.terms.payment_schedule,
  { share_percent: 0, due_event: 'after_acceptance', due_days: null, due_day_kind: 'banking', note: null },
]);
const removeItem = (index: number) => update(
  props.terms.payment_schedule.filter((_, itemIndex) => itemIndex !== index),
);
</script>

<template>
  <section class="business-section" data-testid="payment-terms-panel">
    <div>
      <h4 class="business-heading">Порядок оплаты</h4>
      <p class="business-help">Это согласованный график расчётов, а не факт поступивших платежей.</p>
    </div>
    <div class="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
      <button v-for="item in modes" :key="item.value" type="button" class="payment-mode" :class="mode === item.value ? 'payment-mode-active' : 'payment-mode-idle'" :aria-pressed="mode === item.value" @click="setMode(item.value)">
        <span class="block text-sm font-bold">{{ item.label }}</span><span class="mt-1 block text-xs font-normal opacity-80">{{ item.note }}</span>
      </button>
    </div>
    <div class="mt-3 space-y-2">
      <div v-for="(item, index) in terms.payment_schedule" :key="index" class="grid gap-2 rounded-xl bg-slate-50 p-3 sm:grid-cols-[90px_minmax(150px,1fr)_90px_130px_minmax(140px,1fr)_auto] dark:bg-slate-800">
        <label class="business-field"><span>Доля, %</span><input :value="item.share_percent" class="business-input" type="number" min="0.01" max="100" step="0.01" @input="updateNumber(index, 'share_percent', $event)" /></label>
        <label class="business-field"><span>От события</span><select :value="item.due_event" class="business-input" @change="updateItem(index, { due_event: ($event.target as HTMLSelectElement).value as PaymentScheduleItem['due_event'] })"><option value="before_supply">До поставки</option><option value="before_work">До начала работ</option><option value="after_supply">После поставки</option><option value="after_work">После выполнения работ</option><option value="after_acceptance">После приёмки</option></select></label>
        <label class="business-field"><span>Дней</span><input :value="item.due_days ?? ''" class="business-input" type="number" min="1" max="3650" placeholder="Сразу" @input="updateNumber(index, 'due_days', $event)" /></label>
        <label class="business-field"><span>Вид дней</span><select :value="item.due_day_kind" class="business-input" @change="updateItem(index, { due_day_kind: ($event.target as HTMLSelectElement).value as PaymentScheduleItem['due_day_kind'] })"><option value="banking">Банковские</option><option value="calendar">Календарные</option></select></label>
        <label class="business-field"><span>Пояснение</span><input :value="item.note || ''" class="business-input" placeholder="Необязательно" @input="updateItem(index, { note: ($event.target as HTMLInputElement).value.trim() || null })" /></label>
        <button class="payment-remove" type="button" :aria-label="`Удалить платёж ${index + 1}`" :disabled="terms.payment_schedule.length === 1" @click="removeItem(index)"><span class="material-icons-round text-[18px]">delete</span></button>
      </div>
    </div>
    <button class="mt-3 inline-flex h-9 items-center gap-1 rounded-lg border border-slate-200 px-3 text-xs font-bold text-slate-700 hover:border-teal-400 hover:text-teal-700 dark:border-slate-700 dark:text-slate-200" type="button" @click="addItem"><span class="material-icons-round text-[17px]">add</span>Добавить этап</button>
  </section>
</template>

<style scoped>
.business-section { @apply mt-4 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900/50; }
.business-heading { @apply text-sm font-bold text-slate-900 dark:text-white; }
.business-help { @apply mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400; }
.business-field { @apply flex min-w-0 flex-col gap-1.5 text-xs font-semibold text-slate-700 dark:text-slate-200; }
.business-input { @apply h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-normal text-slate-900 outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/15 dark:border-slate-700 dark:bg-slate-950 dark:text-white; }
.payment-mode { @apply min-h-20 rounded-xl border p-3 text-left transition; }
.payment-mode-active { @apply border-teal-600 bg-teal-600 text-white shadow-sm; }
.payment-mode-idle { @apply border-slate-200 bg-slate-50 text-slate-800 hover:border-teal-300 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100; }
.payment-remove { @apply mt-5 inline-flex h-10 w-10 items-center justify-center rounded-xl text-rose-600 hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-30 dark:hover:bg-rose-950/30; }
</style>
