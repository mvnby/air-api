<script setup lang="ts">
import { CONTRACT_SCENARIOS, type ContractScenario } from '../model/business-document-terms';

const icon = (value: ContractScenario) => ({
  supply: 'inventory_2', supply_installation: 'construction', installation: 'build',
  services: 'miscellaneous_services', maintenance: 'settings_suggest', repair: 'handyman',
  framework: 'repeat',
}[value]);

defineProps<{ modelValue: ContractScenario | null }>();
const emit = defineEmits<{ 'update:modelValue': [value: ContractScenario] }>();
</script>

<template>
  <section class="contract-section" data-testid="contract-scenario-chooser">
    <div>
      <h4 class="contract-heading">Сценарий договора</h4>
      <p class="contract-help">Определяет условия и подходящий шаблон. Можно поменять для этого договора.</p>
    </div>
    <div class="mt-3 flex gap-2 overflow-x-auto pb-1">
      <button
        v-for="scenario in CONTRACT_SCENARIOS"
        :key="scenario.value"
        type="button"
        class="scenario-card"
        :class="modelValue === scenario.value ? 'scenario-card-active' : 'scenario-card-idle'"
        :aria-pressed="modelValue === scenario.value"
        :data-testid="`contract-scenario-${scenario.value}`"
        @click="emit('update:modelValue', scenario.value)"
      >
        <span class="material-icons-round text-[21px]">{{ icon(scenario.value) }}</span>
        <span class="block text-xs font-bold leading-tight">{{ scenario.label }}</span>
      </button>
    </div>
  </section>
</template>

<style scoped>
.contract-section { @apply mt-4 rounded-xl border border-indigo-200 bg-indigo-50/50 p-4 dark:border-indigo-900/70 dark:bg-indigo-950/20; }
.contract-heading { @apply text-sm font-bold text-indigo-950 dark:text-indigo-100; }
.contract-help { @apply mt-1 text-xs leading-5 text-indigo-900/75 dark:text-indigo-200/75; }
.scenario-card { @apply flex min-h-20 min-w-28 max-w-32 flex-col items-center justify-center gap-1 rounded-xl border px-2 py-2 text-center transition; }
.scenario-card-active { @apply border-indigo-600 bg-indigo-600 text-white shadow-sm; }
.scenario-card-idle { @apply border-indigo-200 bg-white text-indigo-950 hover:border-indigo-400 dark:border-indigo-900 dark:bg-slate-900 dark:text-indigo-100; }
</style>
