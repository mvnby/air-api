<script setup lang="ts">
import { computed } from 'vue';
import type { ConsumerDocumentTerms } from '../model/consumer-document-terms';
import {
  calculateInstallationTwoStages,
  formatByn,
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
));

const update = (changes: Partial<ConsumerDocumentTerms>) => {
  emit('updateTerms', { ...props.terms, ...changes });
};

const toggle = () => {
  const enabled = !props.terms.installation_two_stages;
  update({
    installation_two_stages: enabled,
    installation_first_stage_amount: enabled ? props.terms.installation_first_stage_amount : null,
  });
};

const updateFirstStageAmount = (event: Event) => {
  const value = (event.target as HTMLInputElement).value.trim();
  update({ installation_first_stage_amount: value || null });
};

const firstStageDescription = computed(() => (
  props.terms.installation_outdoor_unit_in_first_stage
    ? 'наружный блок, коммуникации и штробление'
    : 'коммуникации и штробление'
));

const secondStageDescription = computed(() => (
  props.terms.installation_outdoor_unit_in_first_stage
    ? 'внутренний блок, подключение и пусконаладка'
    : 'внутренний и наружный блоки, подключение и пусконаладка'
));
</script>

<template>
  <section class="mt-5 border-t border-teal-200 pt-4 dark:border-teal-900/70" data-testid="installation-two-stages">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h5 class="text-sm font-bold text-teal-950 dark:text-teal-100">Монтаж</h5>
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
      <p class="sm:col-span-2 text-xs leading-5 text-teal-900/75 dark:text-teal-200/75" data-testid="installation-two-stages-description">
        Сумма выбранного предложения: {{ formatByn(proposalTotalCents) }}. Первый этап: {{ firstStageDescription }}. Второй: {{ secondStageDescription }} после ремонта по договорённости.
      </p>
      <div class="sm:col-span-2">
        <span class="text-xs font-semibold text-teal-950/80 dark:text-teal-100/80">Первый этап</span>
        <div class="mt-1.5 inline-flex rounded-xl border border-teal-200 bg-white p-1 dark:border-teal-900 dark:bg-slate-900" aria-label="Состав первого этапа">
          <button
            type="button"
            class="installation-stage-choice"
            :class="terms.installation_outdoor_unit_in_first_stage ? 'installation-stage-choice-active' : 'installation-stage-choice-idle'"
            :aria-pressed="terms.installation_outdoor_unit_in_first_stage"
            data-testid="installation-outdoor-first-stage"
            @click="update({ installation_outdoor_unit_in_first_stage: true })"
          >
            Коммуникации + наружный блок
          </button>
          <button
            type="button"
            class="installation-stage-choice"
            :class="!terms.installation_outdoor_unit_in_first_stage ? 'installation-stage-choice-active' : 'installation-stage-choice-idle'"
            :aria-pressed="!terms.installation_outdoor_unit_in_first_stage"
            data-testid="installation-outdoor-second-stage"
            @click="update({ installation_outdoor_unit_in_first_stage: false })"
          >
            Только коммуникации
          </button>
        </div>
      </div>
      <label class="consumer-field">
        <span>К оплате за первый этап, BYN</span>
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
        <span>К оплате за второй этап, BYN</span>
        <input
          :value="formatByn(calculation.remainingCents)"
          class="consumer-input bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
          data-testid="installation-second-stage-amount"
          readonly
        />
      </label>
    </div>
    <p v-if="terms.installation_two_stages && calculation.error" class="mt-2 text-xs font-semibold text-rose-700 dark:text-rose-300" data-testid="installation-two-stages-error">
      {{ calculation.error }}
    </p>
  </section>
</template>

<style scoped>
.consumer-field { @apply flex min-w-0 flex-col gap-1.5 text-xs font-semibold text-teal-950/80 dark:text-teal-100/80; }
.consumer-input { @apply h-10 w-full rounded-xl border border-teal-200 bg-white px-3 text-sm font-normal text-slate-900 outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/15 dark:border-teal-900 dark:bg-slate-900 dark:text-white; }
.consumer-toggle { @apply h-9 rounded-lg border px-3 text-sm font-semibold transition; }
.consumer-toggle-active { @apply border-teal-600 bg-teal-600 text-white; }
.consumer-toggle-idle { @apply border-teal-200 bg-white text-teal-900 hover:border-teal-400 dark:border-teal-900 dark:bg-slate-900 dark:text-teal-100; }
.installation-stage-choice { @apply rounded-lg px-3 py-1.5 text-sm font-semibold transition; }
.installation-stage-choice-active { @apply bg-teal-600 text-white; }
.installation-stage-choice-idle { @apply text-teal-900 hover:bg-teal-50 dark:text-teal-100 dark:hover:bg-teal-900/30; }
</style>
