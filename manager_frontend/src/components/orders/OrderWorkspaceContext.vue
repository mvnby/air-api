<script setup lang="ts">
import { Building2, MapPin, WalletCards } from 'lucide-vue-next';
import { formatMoney } from './order-utils';

defineProps<{
  customerName: string;
  address?: string;
  total: number;
  paid: number;
  balance: number;
}>();

const emit = defineEmits<{
  object: [];
  payments: [];
}>();
</script>

<template>
  <aside class="grid grid-cols-2 gap-2 rounded-2xl border border-slate-200 bg-slate-50/70 p-2.5 text-sm dark:border-slate-700 dark:bg-slate-900/70 lg:sticky lg:top-4 lg:block lg:self-start lg:p-3" aria-label="Контекст заказа" data-order-usage="order-context">
    <div class="flex items-start gap-2">
      <Building2 :size="17" class="mt-0.5 shrink-0 text-slate-400" aria-hidden="true" />
      <div class="min-w-0">
        <p class="text-xs font-medium text-slate-500 dark:text-slate-400">Клиент</p>
        <p class="truncate font-semibold text-slate-900 dark:text-white">{{ customerName || 'Клиент не указан' }}</p>
      </div>
    </div>
    <button type="button" class="flex w-full items-start gap-2 rounded-lg p-1 text-left hover:bg-white dark:hover:bg-slate-800 lg:mt-3" data-order-usage="context-object" @click="emit('object')">
      <MapPin :size="17" class="mt-0.5 shrink-0 text-slate-400" aria-hidden="true" />
      <span class="min-w-0">
        <span class="block text-xs font-medium text-slate-500 dark:text-slate-400">Объект</span>
        <span class="block truncate font-medium text-slate-800 dark:text-slate-100">{{ address || 'Указать адрес' }}</span>
      </span>
    </button>
    <button type="button" class="mt-3 hidden w-full items-start gap-2 rounded-lg border-t border-slate-200 pt-3 text-left hover:text-teal-700 dark:border-slate-700 dark:hover:text-teal-200 lg:flex" data-order-usage="context-payments" @click="emit('payments')">
      <WalletCards :size="17" class="mt-0.5 shrink-0 text-slate-400" aria-hidden="true" />
      <span class="min-w-0">
        <span class="block text-xs font-medium text-slate-500 dark:text-slate-400">Расчёты</span>
        <span class="block font-semibold text-slate-900 dark:text-white">{{ formatMoney(paid) }} из {{ formatMoney(total) }}</span>
        <span class="block text-xs" :class="balance > 0 ? 'text-rose-600 dark:text-rose-300' : 'text-emerald-700 dark:text-emerald-300'">{{ balance > 0 ? `Остаток ${formatMoney(balance)}` : 'Оплачено' }}</span>
      </span>
    </button>
  </aside>
</template>
