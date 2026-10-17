<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue';
import { workerMoneyApi, exactAmount, moneyCents, moneyConflict, type AmountCommand } from '../../services/worker-money';
import type { InstallerCollection } from '../../services/installer-workspace';
import { managerSession } from '../../services/manager-session';
import { getApiErrorMessage } from '../../utils/api-errors';
let active = true;
onBeforeUnmount(() => { active = false; });
const props = defineProps<{ assignmentId: number; collection: InstallerCollection }>();
const emit = defineEmits<{ saved: []; refresh: [] }>();
const amount = ref(''), draft = ref<AmountCommand | null>(null), busy = ref(false), error = ref(''), stale = ref(false), completed = ref(false);
const eligible = computed(() => !managerSession.auth.value?.demo_read_only && props.collection.status === 'ready' && props.collection.currency && (moneyCents(props.collection.amount ?? '') ?? 0n) > 0n && typeof props.collection.version === 'number');
const prepare = () => {
  const value = exactAmount(amount.value);
  if (!value || moneyCents(value)! > moneyCents(props.collection.amount ?? '')!) { error.value = 'Укажите положительную сумму, не больше порученной, с точностью до копеек'; return; }
  error.value = ''; draft.value = { amount: value, currency: props.collection.currency!, expected_version: props.collection.version!, idempotency_key: crypto.randomUUID() };
};
const submit = async () => {
  if (busy.value || stale.value || !draft.value) return;
  busy.value = true; error.value = '';
  try { await workerMoneyApi.receive(props.assignmentId, draft.value); if (!active) return; completed.value = true; draft.value = null; emit('saved'); }
  catch (cause) { stale.value = moneyConflict(cause); error.value = stale.value ? 'Поручение изменилось. Обновите работу и проверьте сумму.' : `${getApiErrorMessage(cause)}. Повторное подтверждение проверит эту же операцию.`; }
  finally { busy.value = false; }
};
</script>
<template>
  <section v-if="eligible && !completed" class="rounded-xl border border-gray-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900" aria-label="Получение денег клиента">
    <template v-if="!draft"><label class="block text-sm font-medium">Фактически получил от клиента ({{ collection.currency }})<input v-model="amount" inputmode="decimal" class="mt-2 block w-full rounded-lg border p-3 dark:bg-slate-800" aria-label="Полученная сумма" /></label><button type="button" class="mt-3 rounded-lg bg-brand-600 px-4 py-3 text-white" @click="prepare">Получил деньги</button></template>
    <template v-else><p class="font-semibold">Подтвердите: вы получили {{ draft.amount }} {{ draft.currency }} от клиента?</p><p class="mt-1 text-sm text-gray-500">Сумма будет учтена как деньги клиента у вас на руках.</p><button type="button" class="mt-3 rounded-lg bg-brand-600 px-4 py-3 text-white disabled:opacity-50" :disabled="busy || stale" @click="submit">{{ busy ? 'Сохраняем…' : 'Подтверждаю получение' }}</button><button v-if="!error" type="button" class="ml-3 p-3" :disabled="busy" @click="draft = null">Назад</button></template>
    <p v-if="error" role="alert" class="mt-3 text-sm text-red-700">{{ error }}</p><button v-if="stale" type="button" class="mt-2 underline" @click="emit('refresh')">Обновить работу</button>
  </section>
</template>
