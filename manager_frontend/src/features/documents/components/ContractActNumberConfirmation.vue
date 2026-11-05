<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import { MAX_PREVIOUS_ACT_NUMBER, type ContractActConfirmation, type PreviousContractAct } from '../model/contract-act-number';

const props = defineProps<{ previous: PreviousContractAct; busy: boolean }>();
const emit = defineEmits<{ confirm: [value: ContractActConfirmation]; cancel: [] }>();
const entered = ref('');
const field = ref<HTMLInputElement | null>(null);
const previousChanged = ref(false);
const focusField = async () => {
  await nextTick();
  field.value?.focus({ preventScroll: true });
  field.value?.scrollIntoView?.({ block: 'center' });
};
onMounted(focusField);
watch(() => props.previous.id, () => {
  entered.value = '';
  previousChanged.value = true;
  void focusField();
});
const verified = computed(() => {
  const value = Number(entered.value);
  return /^\d{1,9}$/.test(entered.value.trim()) && value >= props.previous.minimum && value <= MAX_PREVIOUS_ACT_NUMBER ? value : null;
});
const submit = () => {
  if (props.busy || verified.value === null) return;
  emit('confirm', { previousActId: props.previous.id, previousNumber: verified.value });
};
</script>

<template>
  <form class="mt-3 min-w-0 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-800 dark:bg-amber-950/30" data-testid="contract-act-number-confirmation" @submit.prevent="submit">
    <h4 class="font-bold">Продолжить нумерацию по договору</h4>
    <p v-if="previousChanged" role="status" class="mt-1 font-semibold">Появился более поздний акт. Сверьте номер ещё раз.</p>
    <p class="mt-1 text-slate-700 dark:text-slate-300">Сверьте номер в заголовке последнего акта по договору. В реестре он записан как «{{ previous.number }}».</p>
    <a :href="previous.url || `/manager/orders/kanban?orderId=${previous.orderId}`" target="_blank" rel="noopener noreferrer" class="inline-block py-2 font-semibold text-brand-700 underline dark:text-brand-300">{{ previous.url ? 'Открыть последний акт' : 'Открыть заказ с последним актом' }}</a>
    <label class="mt-1 grid min-w-0 gap-1 text-xs font-semibold">
      Последний номер акта по договору
      <input ref="field" v-model="entered" type="text" inputmode="numeric" pattern="[0-9]{1,9}" maxlength="9" autocomplete="off" class="h-11 w-32 max-w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white" required data-testid="previous-act-number" />
    </label>
    <p v-if="previous.minimum" class="mt-1 text-xs text-slate-600 dark:text-slate-300">В истории уже использован №{{ previous.minimum }}. Введите последний подтверждённый номер.</p>
    <p v-else class="mt-1 text-xs text-slate-600 dark:text-slate-300">Если до сих пор использовались только общие учётные номера, укажите 0.</p>
    <div class="mt-3 flex flex-wrap items-center gap-2">
      <button type="submit" class="min-h-11 rounded-lg bg-brand-600 px-3 font-semibold text-white disabled:opacity-50" :disabled="busy || verified === null">{{ verified === null ? 'Выпустить акт' : `Выпустить акт №${verified + 1}` }}</button>
      <button type="button" class="min-h-11 rounded-lg px-3 text-slate-600 dark:text-slate-300" :disabled="busy" @click="emit('cancel')">Отмена</button>
    </div>
  </form>
</template>
