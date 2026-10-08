<script setup lang="ts">
import { Building2, ChevronDown, MapPin, WalletCards } from 'lucide-vue-next';
import OrderMoney from './OrderMoney.vue';

defineProps<{
  customerName: string;
  address?: string;
  total: number;
  paid: number;
  balance: number;
  expanded?: 'customer' | 'object' | null;
  disabled?: boolean;
}>();

const emit = defineEmits<{
  customer: [];
  object: [];
  payments: [];
}>();
</script>

<template>
  <aside class="grid gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-2.5 text-sm dark:border-slate-700 dark:bg-slate-900 lg:block lg:self-start lg:p-3" aria-label="Контекст заказа" data-order-usage="order-context">
    <section class="min-w-0">
    <button type="button" class="flex w-full items-start gap-2 rounded-lg p-1 text-left hover:bg-white disabled:opacity-60 dark:hover:bg-slate-800" :disabled="disabled" :aria-expanded="expanded === 'customer'" aria-controls="order-context-customer-editor" data-order-usage="context-customer" @click="emit('customer')">
      <Building2 :size="17" class="mt-0.5 shrink-0 text-slate-400" aria-hidden="true" />
      <span class="min-w-0">
        <p class="text-xs font-medium text-slate-500 dark:text-slate-400">Клиент</p>
        <p class="break-words text-xs font-semibold leading-5 text-slate-900 dark:text-white" :class="expanded === 'customer' ? '' : 'line-clamp-3'" :title="customerName">{{ customerName || 'Выбрать клиента' }}</p>
      </span>
      <ChevronDown :size="14" class="ml-auto mt-1 shrink-0 text-slate-400 transition-transform" :class="expanded === 'customer' ? 'rotate-180' : ''" aria-hidden="true" />
    </button>
    <div v-show="expanded === 'customer'" id="order-context-customer-editor" class="mt-2 border-t border-slate-200 pt-3 dark:border-slate-700"><slot name="customer" /></div>
    </section>
    <section class="min-w-0 lg:mt-3">
    <button type="button" class="flex w-full items-start gap-2 rounded-lg p-1 text-left hover:bg-white disabled:opacity-60 dark:hover:bg-slate-800" :disabled="disabled" :aria-expanded="expanded === 'object'" aria-controls="order-context-object-editor" data-order-usage="context-object" @click="emit('object')">
      <MapPin :size="17" class="mt-0.5 shrink-0 text-slate-400" aria-hidden="true" />
      <span class="min-w-0">
        <span class="block text-xs font-medium text-slate-500 dark:text-slate-400">Объект</span>
        <span class="block break-words text-xs font-medium leading-5 text-slate-800 dark:text-slate-100" :class="expanded === 'object' ? '' : 'line-clamp-2'">{{ address || 'Указать адрес' }}</span>
      </span>
      <ChevronDown :size="14" class="ml-auto mt-1 shrink-0 text-slate-400 transition-transform" :class="expanded === 'object' ? 'rotate-180' : ''" aria-hidden="true" />
    </button>
    <div v-show="expanded === 'object'" id="order-context-object-editor" class="mt-2 border-t border-slate-200 pt-3 dark:border-slate-700"><slot name="object" /></div>
    </section>
    <button type="button" class="mt-3 hidden w-full items-start gap-2 rounded-lg border-t border-slate-200 pt-3 text-left hover:text-brand-700 dark:border-slate-700 dark:hover:text-brand-200 lg:flex" data-order-usage="context-payments" @click="emit('payments')">
      <WalletCards :size="17" class="mt-0.5 shrink-0 text-slate-400" aria-hidden="true" />
      <span class="min-w-0">
        <span class="block text-xs font-medium text-slate-500 dark:text-slate-400">Расчёты</span>
        <span class="relative block font-semibold text-slate-900 dark:text-white"><OrderMoney :value="paid" /> из <OrderMoney :value="total" /></span>
        <span class="relative block text-xs" :class="balance > 0 ? 'text-rose-600 dark:text-rose-300' : 'text-emerald-700 dark:text-emerald-300'"><template v-if="balance > 0">Остаток <OrderMoney :value="balance" /></template><template v-else>Оплачено</template></span>
      </span>
    </button>
  </aside>
</template>
