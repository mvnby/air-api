<script setup lang="ts">
import type { ActClaimsStatus, ActTerms } from '../model/act-terms';

const props = defineProps<{ terms: ActTerms }>();
const emit = defineEmits<{ updateTerms: [terms: ActTerms] }>();
const update = (changes: Partial<ActTerms>) => emit('updateTerms', { ...props.terms, ...changes });
const setClaimsStatus = (claimsStatus: ActClaimsStatus) => update({
  claims_status: claimsStatus,
  claims_text: claimsStatus === 'none' ? null : props.terms.claims_text,
});
const updateText = (field: 'result_text' | 'claims_text', event: Event) => {
  const value = (event.target as HTMLTextAreaElement).value.trim();
  update({ [field]: value || null });
};
</script>

<template>
  <section class="act-section" data-testid="act-terms-panel">
    <div>
      <h4 class="act-heading">Результат и приёмка</h4>
      <p class="act-help">Фраза «претензий не имеет» попадёт в акт только при выбранном варианте без замечаний.</p>
    </div>
    <label class="act-field mt-3"><span>Что выполнено и передано</span><textarea :value="terms.result_text || ''" class="act-input min-h-24 py-2" placeholder="Например: оборудование поставлено, монтаж и пусконаладка выполнены" @input="updateText('result_text', $event)" /></label>
    <label class="act-field mt-3 max-w-xs"><span>Срок приёмки до</span><input :value="terms.acceptance_deadline || ''" class="act-input" type="date" @input="update({ acceptance_deadline: ($event.target as HTMLInputElement).value || null })" /></label>
    <div class="mt-3">
      <span class="text-xs font-bold text-slate-600 dark:text-slate-300">Замечания</span>
      <div class="mt-1.5 inline-flex rounded-xl border border-slate-200 bg-white p-1 dark:border-slate-700 dark:bg-slate-900">
        <button type="button" class="claims-toggle" :class="terms.claims_status === 'none' ? 'claims-toggle-active' : 'claims-toggle-idle'" :aria-pressed="terms.claims_status === 'none'" data-testid="act-claims-none" @click="setClaimsStatus('none')">Без замечаний</button>
        <button type="button" class="claims-toggle" :class="terms.claims_status === 'present' ? 'claims-toggle-active' : 'claims-toggle-idle'" :aria-pressed="terms.claims_status === 'present'" data-testid="act-claims-present" @click="setClaimsStatus('present')">Есть замечания</button>
      </div>
    </div>
    <label v-if="terms.claims_status === 'present'" class="act-field mt-3"><span>Текст замечаний</span><textarea :value="terms.claims_text || ''" class="act-input min-h-24 py-2" data-testid="act-claims-text" placeholder="Опишите недостатки и порядок их устранения" @input="updateText('claims_text', $event)" /></label>
  </section>
</template>

<style scoped>
.act-section { @apply mt-4 rounded-xl border border-amber-200 bg-amber-50/60 p-4 dark:border-amber-900/70 dark:bg-amber-950/20; }
.act-heading { @apply text-sm font-bold text-amber-950 dark:text-amber-100; }
.act-help { @apply mt-1 text-xs leading-5 text-amber-900/75 dark:text-amber-200/75; }
.act-field { @apply flex min-w-0 flex-col gap-1.5 text-xs font-semibold text-slate-700 dark:text-slate-200; }
.act-input { @apply h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-normal text-slate-900 outline-none focus:border-amber-500 focus:ring-2 focus:ring-amber-500/15 dark:border-slate-700 dark:bg-slate-950 dark:text-white; }
.claims-toggle { @apply rounded-lg px-3 py-1.5 text-sm font-semibold transition; }
.claims-toggle-active { @apply bg-amber-600 text-white; }
.claims-toggle-idle { @apply text-slate-600 dark:text-slate-300; }
</style>
