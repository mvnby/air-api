<script setup lang="ts">
import { computed, watch } from 'vue';
import MoneyAmount from '../../../components/money/MoneyAmount.vue';
import BynSymbol from '../../../components/money/BynSymbol.vue';
import type { ConsumerDocumentTerms } from '../model/consumer-document-terms';
import {
  calculateInstallationTwoStages,
  formatBynAmount,
  centsToAmount,
  moneyToCents,
  installationStageDefaults,
  installationRemainingDefault,
  installationTermsError,
} from '../model/installation-two-stages';

const props = defineProps<{
  terms: ConsumerDocumentTerms;
  proposalTotalCents: number | null;
}>();

const emit = defineEmits<{
  updateTerms: [terms: ConsumerDocumentTerms];
}>();

const calculation = computed(() => calculateInstallationTwoStages(
  props.terms.installation_first_stage_amount,
  props.proposalTotalCents,
  props.terms.installation_remaining_amount,
));
const error = computed(() => installationTermsError(props.terms, props.proposalTotalCents));
const stageDefaults = computed(() => installationStageDefaults(props.terms.installation_outdoor_unit_in_first_stage));

const update = (changes: Partial<ConsumerDocumentTerms>) => {
  emit('updateTerms', { ...props.terms, ...changes });
};

const presetChanges = (outdoor: boolean, count: number, previousTotal = props.proposalTotalCents) => {
  const old = props.terms;
  const defaults = installationStageDefaults(outdoor);
  const previousDefaults = installationStageDefaults(old.installation_outdoor_unit_in_first_stage);
  const changes: Partial<ConsumerDocumentTerms> = {
    installation_outdoor_unit_in_first_stage: outdoor,
    installation_unit_count: count,
  };
  for (const [field, key] of [
    ['installation_first_stage_works', 'first'],
    ['installation_second_stage_works', 'second'],
    ['installation_second_stage_due', 'due'],
  ] as const) {
    if (old[field] === null || old[field] === previousDefaults[key]) changes[field] = defaults[key];
  }
  const previousRemaining = installationRemainingDefault(old.installation_outdoor_unit_in_first_stage, old.installation_unit_count);
  const untouched = old.installation_first_stage_amount === null && old.installation_remaining_amount === null;
  const matchesDefault = previousTotal !== null
    && moneyToCents(old.installation_first_stage_amount) === previousTotal - previousRemaining
    && (old.installation_remaining_amount === null || moneyToCents(old.installation_remaining_amount) === previousRemaining);
  if ((untouched || matchesDefault) && props.proposalTotalCents !== null && Number.isInteger(count) && count >= 1 && count <= 1000) {
    const remaining = installationRemainingDefault(outdoor, count);
    changes.installation_remaining_amount = centsToAmount(remaining);
    changes.installation_first_stage_amount = props.proposalTotalCents > remaining
      ? centsToAmount(props.proposalTotalCents - remaining) : null;
  }
  return changes;
};

const toggle = () => update({
  ...(props.terms.installation_two_stages ? {} : presetChanges(props.terms.installation_outdoor_unit_in_first_stage, props.terms.installation_unit_count)),
  installation_two_stages: !props.terms.installation_two_stages,
});
const chooseVariant = (outdoor: boolean) => update(presetChanges(outdoor, props.terms.installation_unit_count));
const updateCount = (event: Event) => update(presetChanges(
  props.terms.installation_outdoor_unit_in_first_stage, Number((event.target as HTMLInputElement).value),
));
const updateFirstStageAmount = (event: Event) => {
  const value = (event.target as HTMLInputElement).value.trim();
  const cents = moneyToCents(value);
  update({
    installation_first_stage_amount: value || null,
    installation_remaining_amount: cents !== null && props.proposalTotalCents !== null && cents <= props.proposalTotalCents
      ? centsToAmount(props.proposalTotalCents - cents) : null,
  });
};
const updateSecondStageAmount = (event: Event) => {
  const value = (event.target as HTMLInputElement).value.trim();
  const cents = moneyToCents(value);
  update({
    installation_remaining_amount: value || null,
    installation_first_stage_amount: cents !== null && props.proposalTotalCents !== null && cents < props.proposalTotalCents
      ? centsToAmount(props.proposalTotalCents - cents) : null,
  });
};
const updateText = (field: 'installation_first_stage_works' | 'installation_second_stage_works' | 'installation_second_stage_due', event: Event) => (
  update({ [field]: (event.target as HTMLTextAreaElement).value })
);
watch(() => props.proposalTotalCents, (_total, oldTotal) => {
  if (props.terms.installation_two_stages) update(presetChanges(
    props.terms.installation_outdoor_unit_in_first_stage, props.terms.installation_unit_count, oldTotal,
  ));
});

</script>

<template>
  <section class="mt-5 border-t border-brand-200 pt-4 dark:border-brand-900/70" data-testid="installation-two-stages">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h5 class="text-sm font-bold text-brand-950 dark:text-brand-100">Монтаж</h5>
      </div>
      <button
        type="button"
        class="consumer-toggle"
        :class="terms.installation_two_stages ? 'consumer-toggle-active' : 'consumer-toggle-idle'"
        :aria-pressed="terms.installation_two_stages"
        data-testid="installation-two-stages-toggle"
        @click="toggle"
      >
        Монтаж в два этапа
      </button>
    </div>

    <div v-if="terms.installation_two_stages" class="mt-4 grid gap-3 sm:grid-cols-2">
      <p class="sm:col-span-2 text-xs leading-5 text-brand-900/75 dark:text-brand-200/75" data-testid="installation-two-stages-description">
        Сумма выбранного предложения: <MoneyAmount :value="proposalTotalCents === null ? null : proposalTotalCents / 100" :formatted-value="formatBynAmount(proposalTotalCents)" />. Состав работ и суммы этапов попадут в договор.
      </p>
      <div class="sm:col-span-2">
        <span class="text-xs font-semibold text-brand-950/80 dark:text-brand-100/80">Первый этап</span>
        <div class="mt-1.5 flex flex-wrap gap-1 rounded-xl border border-brand-200 bg-white p-1 dark:border-brand-900 dark:bg-slate-900" aria-label="Состав первого этапа">
          <button
            type="button"
            class="installation-stage-choice"
            :class="terms.installation_outdoor_unit_in_first_stage ? 'installation-stage-choice-active' : 'installation-stage-choice-idle'"
            :aria-pressed="terms.installation_outdoor_unit_in_first_stage"
            data-testid="installation-outdoor-first-stage"
            @click="chooseVariant(true)"
          >
            Трасса и наружный блок
          </button>
          <button
            type="button"
            class="installation-stage-choice"
            :class="!terms.installation_outdoor_unit_in_first_stage ? 'installation-stage-choice-active' : 'installation-stage-choice-idle'"
            :aria-pressed="!terms.installation_outdoor_unit_in_first_stage"
            data-testid="installation-outdoor-second-stage"
            @click="chooseVariant(false)"
          >
            Только трасса
          </button>
        </div>
      </div>
      <label class="consumer-field sm:col-span-2">
        <span>Количество кондиционеров</span>
        <input :value="terms.installation_unit_count" type="number" min="1" max="1000" step="1" class="consumer-input" data-testid="installation-unit-count" @input="updateCount" />
        <span class="font-normal text-slate-500">По умолчанию на второй этап: {{ terms.installation_outdoor_unit_in_first_stage ? 100 : 200 }} BYN за кондиционер. Укажите согласованную сумму, если она отличается.</span>
      </label>
      <label class="consumer-field">
        <span>Стоимость первого этапа, <BynSymbol /><span class="sr-only">BYN</span></span>
        <input
          :value="terms.installation_first_stage_amount || ''"
          class="consumer-input"
          data-testid="installation-first-stage-amount"
          inputmode="decimal"
          placeholder="Например, 3000,00"
          @input="updateFirstStageAmount"
        />
      </label>
      <label class="consumer-field">
        <span>Стоимость второго этапа, <BynSymbol /><span class="sr-only">BYN</span></span>
        <input
          :value="terms.installation_remaining_amount ?? (calculation.remainingCents === null ? '' : centsToAmount(calculation.remainingCents))"
          class="consumer-input"
          data-testid="installation-second-stage-amount"
          inputmode="decimal"
          @input="updateSecondStageAmount"
        />
      </label>
      <label class="consumer-field">
        <span>Работы первого этапа</span>
        <textarea :value="terms.installation_first_stage_works ?? stageDefaults.first" rows="3" maxlength="4000" class="consumer-textarea" data-testid="installation-first-stage-works" @input="updateText('installation_first_stage_works', $event)" />
      </label>
      <label class="consumer-field">
        <span>Работы второго этапа</span>
        <textarea :value="terms.installation_second_stage_works ?? stageDefaults.second" rows="3" maxlength="4000" class="consumer-textarea" data-testid="installation-second-stage-works" @input="updateText('installation_second_stage_works', $event)" />
      </label>
      <label class="consumer-field sm:col-span-2">
        <span>Условия завершения и расчёта за второй этап</span>
        <textarea :value="terms.installation_second_stage_due ?? stageDefaults.due" rows="2" maxlength="2000" class="consumer-textarea" data-testid="installation-second-stage-due" @input="updateText('installation_second_stage_due', $event)" />
      </label>
    </div>
    <p v-if="terms.installation_two_stages && error" class="mt-2 text-xs font-semibold text-rose-700 dark:text-rose-300" data-testid="installation-two-stages-error">
      {{ error }}
    </p>
  </section>
</template>

<style scoped>
.consumer-field { @apply flex min-w-0 flex-col gap-1.5 text-xs font-semibold text-brand-950/80 dark:text-brand-100/80; }
.consumer-input { @apply h-10 w-full rounded-xl border border-brand-200 bg-white px-3 text-sm font-normal text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/15 dark:border-brand-900 dark:bg-slate-900 dark:text-white; }
.consumer-textarea { @apply w-full rounded-xl border border-brand-200 bg-white px-3 py-2 text-sm font-normal text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/15 dark:border-brand-900 dark:bg-slate-900 dark:text-white; }
.consumer-toggle { @apply h-9 rounded-lg border px-3 text-sm font-semibold transition; }
.consumer-toggle-active { @apply border-brand-600 bg-brand-600 text-white; }
.consumer-toggle-idle { @apply border-brand-200 bg-white text-brand-900 hover:border-brand-400 dark:border-brand-900 dark:bg-slate-900 dark:text-brand-100; }
.installation-stage-choice { @apply rounded-lg px-3 py-1.5 text-sm font-semibold transition; }
.installation-stage-choice-active { @apply bg-brand-600 text-white; }
.installation-stage-choice-idle { @apply text-brand-900 hover:bg-brand-50 dark:text-brand-100 dark:hover:bg-brand-900/30; }
</style>
