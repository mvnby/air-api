<script setup lang="ts">
import type { BusinessDocumentTerms } from '../model/business-document-terms';

type Preset = { id: string; label: string; text: string };
const presets: Preset[] = [
  { id: 'access', label: 'Доступ к оборудованию', text: 'Заказчик обеспечивает свободный и безопасный доступ к оборудованию и месту проведения работ.' },
  { id: 'extra-works', label: 'Дополнительные работы', text: 'Работы и материалы вне согласованного объёма выполняются по дополнительному согласованию и оплачиваются отдельно.' },
  { id: 'hidden-utilities', label: 'Скрытые коммуникации', text: 'Исполнитель не отвечает за скрытые коммуникации, не обозначенные Заказчиком до начала работ.' },
  { id: 'customer-equipment', label: 'Оборудование заказчика', text: 'Гарантия Исполнителя распространяется на выполненные работы, но не на качество и комплектность оборудования Заказчика.' },
  { id: 'email-approval', label: 'Согласование по переписке', text: 'Дополнительные работы, материалы и сроки могут согласовываться сторонами по электронной переписке.' },
  { id: 'hidden-defects', label: 'Скрытые дефекты', text: 'В процессе диагностики или ремонта могут выявиться скрытые дефекты, не определяемые при первоначальном осмотре.' },
];

const props = defineProps<{ terms: BusinessDocumentTerms }>();
const emit = defineEmits<{ updateTerms: [terms: BusinessDocumentTerms] }>();
const normalized = (value: string) => value.replace(/\s+/g, ' ').trim();
const lines = () => (props.terms.additional_conditions || '').split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
const selected = (preset: Preset) => lines().some((line) => normalized(line) === normalized(preset.text));
const update = (nextLines: string[]) => emit('updateTerms', {
  ...props.terms,
  additional_conditions: nextLines.length ? nextLines.join('\n') : null,
  additional_conditions_overridden: true,
});
const toggle = (preset: Preset) => {
  const current = lines();
  update(selected(preset) ? current.filter((line) => normalized(line) !== normalized(preset.text)) : [...current, preset.text]);
};
const updateText = (event: Event) => {
  const value = (event.target as HTMLTextAreaElement).value.trim();
  emit('updateTerms', {
    ...props.terms,
    additional_conditions: value || null,
    additional_conditions_overridden: true,
  });
};
</script>

<template>
  <section class="business-section" data-testid="additional-conditions-panel">
    <div><h4 class="business-heading">Дополнительные условия</h4><p class="business-help">Можно оставить условия заказа или заменить их только для этого документа.</p></div>
    <div class="mt-3 inline-flex rounded-xl border border-slate-200 bg-slate-50 p-1 dark:border-slate-700 dark:bg-slate-800" data-testid="additional-conditions-source-toggle"><button type="button" class="rounded-lg px-3 py-1.5 text-sm font-semibold transition" :class="!terms.additional_conditions_overridden ? 'bg-teal-600 text-white' : 'text-slate-600 dark:text-slate-300'" :aria-pressed="!terms.additional_conditions_overridden" @click="emit('updateTerms', { ...terms, additional_conditions: null, additional_conditions_overridden: false })">Из заказа</button><button type="button" class="rounded-lg px-3 py-1.5 text-sm font-semibold transition" :class="terms.additional_conditions_overridden ? 'bg-teal-600 text-white' : 'text-slate-600 dark:text-slate-300'" :aria-pressed="terms.additional_conditions_overridden" @click="emit('updateTerms', { ...terms, additional_conditions_overridden: true })">Свой текст</button></div>
    <div v-if="terms.additional_conditions_overridden" class="mt-3 flex flex-wrap gap-2">
      <button v-for="preset in presets" :key="preset.id" type="button" class="condition-chip" :class="selected(preset) ? 'condition-chip-active' : 'condition-chip-idle'" :aria-pressed="selected(preset)" @click="toggle(preset)">{{ preset.label }}</button>
    </div>
    <label v-if="terms.additional_conditions_overridden" class="business-field mt-3"><span>Текст условий</span><textarea :value="terms.additional_conditions || ''" class="business-input min-h-28 py-2" placeholder="Каждое условие — с новой строки" @input="updateText" /></label>
  </section>
</template>

<style scoped>
.business-section { @apply mt-4 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900/50; }
.business-heading { @apply text-sm font-bold text-slate-900 dark:text-white; }
.business-help { @apply mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400; }
.business-field { @apply flex min-w-0 flex-col gap-1.5 text-xs font-semibold text-slate-700 dark:text-slate-200; }
.business-input { @apply h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-normal text-slate-900 outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/15 dark:border-slate-700 dark:bg-slate-950 dark:text-white; }
.condition-chip { @apply rounded-lg border px-3 py-2 text-xs font-semibold transition; }
.condition-chip-active { @apply border-teal-600 bg-teal-600 text-white; }
.condition-chip-idle { @apply border-slate-200 bg-slate-50 text-slate-700 hover:border-teal-300 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200; }
</style>
