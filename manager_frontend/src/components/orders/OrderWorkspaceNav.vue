<script setup lang="ts">
import { BriefcaseBusiness, FileText, Plus, ReceiptText, Wrench } from 'lucide-vue-next';
import type { OrderWorkflowType } from './order-workspace';

export type OrderWorkspaceSection = 'proposal' | 'documents' | 'work' | 'payments';

const props = defineProps<{
  active: OrderWorkspaceSection;
  workflow: OrderWorkflowType;
}>();

const emit = defineEmits<{
  select: [section: OrderWorkspaceSection];
  'add-product': [];
}>();

const items = [
  { id: 'proposal' as const, label: 'Предложение', icon: BriefcaseBusiness },
  { id: 'documents' as const, label: 'Документы', icon: FileText },
  { id: 'work' as const, label: 'Работы', icon: Wrench },
  { id: 'payments' as const, label: 'Оплаты', icon: ReceiptText },
];
</script>

<template>
  <nav class="flex min-w-0 items-center gap-0.5 overflow-x-auto rounded-xl border border-slate-200 bg-slate-50 p-1 dark:border-slate-700 dark:bg-slate-900" aria-label="Рабочая область заказа" data-order-usage="workspace-navigation">
    <button
      v-for="item in items"
      :key="item.id"
      type="button"
      class="inline-flex min-h-9 min-w-0 flex-1 items-center justify-center gap-1 rounded-lg px-1 text-xs font-semibold transition sm:flex-none sm:px-3 sm:text-sm"
      :class="active === item.id ? 'bg-white text-teal-700 shadow-sm dark:bg-slate-800 dark:text-teal-200' : 'text-slate-600 hover:bg-white/80 hover:text-slate-950 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white'"
      :aria-current="active === item.id ? 'page' : undefined"
      :data-order-usage="`workspace-${item.id}`"
      @click="emit('select', item.id)"
    >
      <component :is="item.icon" :size="15" class="hidden shrink-0 sm:block" aria-hidden="true" />
      {{ item.id === 'work' && workflow === 'repair' ? 'Ремонт' : item.label }}
    </button>
    <button
      type="button"
      class="ml-auto hidden min-h-9 shrink-0 items-center gap-1 rounded-lg px-2.5 text-xs font-semibold text-teal-700 hover:bg-teal-50 dark:text-teal-200 dark:hover:bg-teal-500/10 lg:inline-flex"
      data-order-usage="workspace-add-product"
      @click="emit('add-product')"
    >
      <Plus :size="15" aria-hidden="true" />
      <span class="hidden sm:inline">Товар</span>
    </button>
  </nav>
</template>
