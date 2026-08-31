<script setup lang="ts">
import type { BusinessDocumentTerms } from '../model/business-document-terms';

const props = defineProps<{ terms: BusinessDocumentTerms; showSupply: boolean; showWarranty: boolean; showValidUntil: boolean }>();
const emit = defineEmits<{ updateTerms: [terms: BusinessDocumentTerms] }>();

const update = (changes: Partial<BusinessDocumentTerms>) => emit('updateTerms', { ...props.terms, ...changes });
const updateNumber = (field: 'goods_warranty_months' | 'work_warranty_months', event: Event) => {
  const raw = (event.target as HTMLInputElement).value;
  const value = raw === '' ? null : Number(raw);
  update({ [field]: Number.isFinite(value) ? value : null } as Partial<BusinessDocumentTerms>);
};
const updateText = (field: 'subject' | 'goods_warranty_terms' | 'work_warranty_terms', event: Event) => {
  const value = (event.target as HTMLInputElement | HTMLTextAreaElement).value.trim();
  update({ [field]: value || null } as Partial<BusinessDocumentTerms>);
};
</script>

<template>
  <section class="business-section" data-testid="supply-warranty-terms-panel">
    <template v-if="showSupply">
      <div>
        <h4 class="business-heading">Предмет и сроки</h4>
        <p class="business-help">Оставьте пустым то, что уже однозначно описано в выбранном предложении или спецификации.</p>
      </div>
      <div class="mt-3 grid gap-3 sm:grid-cols-2">
        <label class="business-field sm:col-span-2"><span>Краткий предмет договора</span><input :value="terms.subject || ''" class="business-input" placeholder="Например: поставка и монтаж системы кондиционирования" @input="updateText('subject', $event)" /></label>
        <label class="business-field"><span>Срок поставки</span><input :value="terms.delivery_deadline || ''" class="business-input" type="date" @input="update({ delivery_deadline: ($event.target as HTMLInputElement).value || null })" /></label>
        <label class="business-field"><span>Срок выполнения работ</span><input :value="terms.performance_deadline || ''" class="business-input" type="date" @input="update({ performance_deadline: ($event.target as HTMLInputElement).value || null })" /></label>
        <label v-if="showValidUntil" class="business-field"><span>Действует до</span><input :value="terms.valid_until || ''" class="business-input" type="date" @input="update({ valid_until: ($event.target as HTMLInputElement).value || null })" /></label>
      </div>
    </template>
    <template v-if="showWarranty">
      <div :class="showSupply ? 'mt-5 border-t border-slate-200 pt-4 dark:border-slate-700' : ''"><h4 class="business-heading">Гарантия</h4><p class="business-help">Укажите согласованный срок отдельно для оборудования и выполненных работ. 0 — не указывать договорную гарантию.</p></div>
      <div class="mt-3 grid gap-3 sm:grid-cols-2"><label class="business-field"><span>На оборудование, мес.</span><input :value="terms.goods_warranty_months ?? ''" class="business-input" type="number" min="0" max="240" @input="updateNumber('goods_warranty_months', $event)" /></label><label class="business-field"><span>На работы, мес.</span><input :value="terms.work_warranty_months ?? ''" class="business-input" type="number" min="0" max="240" @input="updateNumber('work_warranty_months', $event)" /></label></div>
      <div class="mt-3 grid gap-3 sm:grid-cols-2"><label class="business-field"><span>Условия гарантии на оборудование</span><textarea :value="terms.goods_warranty_terms || ''" class="business-input min-h-20 py-2" placeholder="Например: по условиям изготовителя" @input="updateText('goods_warranty_terms', $event)" /></label><label class="business-field"><span>Условия гарантии на работы</span><textarea :value="terms.work_warranty_terms || ''" class="business-input min-h-20 py-2" placeholder="Например: при соблюдении правил эксплуатации" @input="updateText('work_warranty_terms', $event)" /></label></div>
    </template>
  </section>
</template>

<style scoped>
.business-section { @apply mt-4 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900/50; }
.business-heading { @apply text-sm font-bold text-slate-900 dark:text-white; }
.business-help { @apply mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400; }
.business-field { @apply flex min-w-0 flex-col gap-1.5 text-xs font-semibold text-slate-700 dark:text-slate-200; }
.business-input { @apply h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-normal text-slate-900 outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/15 dark:border-slate-700 dark:bg-slate-950 dark:text-white; }
</style>
