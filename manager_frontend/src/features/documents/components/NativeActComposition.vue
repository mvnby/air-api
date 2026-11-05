<script setup lang="ts">
import MoneyAmount from '../../../components/money/MoneyAmount.vue';
import type { OrderServiceLineResponse } from '../../../client';
import type { useNativeActComposition } from '../composables/use-native-act-composition';
import { formatMoneyAmount } from '../model/document-formatters';

const props = defineProps<{ scope: ReturnType<typeof useNativeActComposition> }>();
const changeSite = () => {
  if (props.scope.selectedBranchId.value !== null) {
    props.scope.onBranchChange();
  } else {
    props.scope.title.value = '';
    props.scope.address.value = '';
  }
};
const updateQuantity = (line: OrderServiceLineResponse, event: Event) => {
  const field = event.target as HTMLInputElement;
  // Let someone clear the box and type a replacement without losing keyboard focus.
  if (!field.value && event.type === 'input') return;
  props.scope.setQuantity(line, field.value);
  field.value = String(props.scope.quantity(line.id));
};
</script>

<template>
  <section class="mt-4 min-w-0 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900" data-testid="native-act-composition">
    <h4 class="text-sm font-bold">Объект и выполненные работы</h4>
    <label v-if="scope.customerBranches.value.length" class="field mt-3">
      <span>Объект клиента</span>
      <select v-model="scope.selectedBranchId.value" class="control" data-testid="act-site" @change="changeSite">
        <option :value="null">Указать объект вручную</option>
        <option v-for="branch in scope.customerBranches.value" :key="branch.id" :value="branch.id">{{ branch.name || branch.delivery_address }}</option>
      </select>
    </label>
    <p v-if="scope.selectedBranchId.value && scope.customerBranches.value.length" class="mt-1 break-words text-xs text-slate-600 dark:text-slate-300">
      {{ scope.address.value }}
    </p>
    <div v-else class="mt-3 grid min-w-0 gap-3 md:grid-cols-2">
      <label class="field"><span>Название объекта</span><input v-model="scope.title.value" class="control" maxlength="500" data-testid="act-site-name" placeholder="Например, магазин" /></label>
      <label class="field"><span>Адрес работ</span><input v-model="scope.address.value" class="control" maxlength="1000" data-testid="act-site-address" placeholder="Улица, дом" /></label>
    </div>
    <ul v-if="scope.lines.value.length" class="mt-3 divide-y divide-slate-200 border-y border-slate-200 dark:divide-slate-700 dark:border-slate-700">
      <li v-for="line in scope.lines.value" :key="line.id" class="grid min-w-0 gap-x-3 py-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
        <label class="flex min-h-11 min-w-0 flex-1 cursor-pointer items-center gap-2">
          <input type="checkbox" class="size-4 shrink-0" :checked="scope.quantity(line.id) > 0" :aria-label="line.service_title" @change="scope.onCheckboxChange(line.id, $event)" />
          <span class="min-w-0 break-words text-sm">{{ line.service_title }}</span>
        </label>
        <label v-if="scope.quantity(line.id) > 0" class="flex min-w-0 items-center gap-2 pl-6 text-xs text-slate-500 sm:pl-0">
          <span class="sm:sr-only">Количество</span>
          <input type="number" inputmode="numeric" class="control w-16" min="0" :max="line.quantity" step="1" :value="scope.quantity(line.id)" :aria-label="`Количество: ${line.service_title}`" @input="updateQuantity(line, $event)" @change="updateQuantity(line, $event)" />
          из {{ line.quantity }}
        </label>
      </li>
    </ul>
    <p v-else class="mt-3 text-sm text-slate-600 dark:text-slate-300">В выбранном предложении нет работ для акта.</p>
    <p v-if="scope.lines.value.length" class="mt-2 flex flex-wrap items-baseline justify-between gap-2 text-sm">
      <span>Выбрано позиций: {{ scope.selectedServiceLineIds.value.length }}</span>
      <strong><MoneyAmount :value="scope.total.value" :formatted-value="formatMoneyAmount(scope.total.value)" /></strong>
    </p>
  </section>
</template>

<style scoped>
.field { @apply flex min-w-0 flex-col gap-1 text-xs font-semibold text-slate-600 dark:text-slate-300; }
.control { @apply h-11 min-w-0 max-w-full rounded-lg border border-slate-300 bg-white px-2 text-sm font-normal text-slate-900 focus:border-brand-500 dark:border-slate-700 dark:bg-slate-950 dark:text-white; }
</style>
