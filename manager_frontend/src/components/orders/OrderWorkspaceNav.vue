<script setup lang="ts">
import { BriefcaseBusiness, FileText, ReceiptText, Wrench } from 'lucide-vue-next';
import type { OrderWorkflowType } from './order-workspace';

export type OrderWorkspaceSection = 'proposal' | 'documents' | 'work' | 'payments';

const props = defineProps<{
  active: OrderWorkspaceSection;
  workflow: OrderWorkflowType;
}>();

const emit = defineEmits<{
  select: [section: OrderWorkspaceSection];
}>();

const items = [
  { id: 'proposal' as const, label: 'Предложение', icon: BriefcaseBusiness },
  { id: 'documents' as const, label: 'Документы', icon: FileText },
  { id: 'work' as const, label: 'Работы', icon: Wrench },
  { id: 'payments' as const, label: 'Оплаты', icon: ReceiptText },
];
</script>

<template>
  <nav class="grid min-w-0 grid-cols-[1.25fr_1.15fr_0.8fr_0.8fr] items-center gap-0.5 rounded-xl border border-slate-200 bg-slate-50 p-1 sm:flex dark:border-slate-700 dark:bg-slate-900" aria-label="Рабочая область заказа" data-order-usage="workspace-navigation">
    <button
      v-for="item in items"
      :key="item.id"
      type="button"
      class="inline-flex min-h-11 min-w-0 items-center justify-center gap-1 rounded-lg px-1 text-xs font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-brand-500 sm:flex-none sm:px-3 sm:text-sm"
      :class="active === item.id ? 'bg-white text-brand-700 shadow-sm dark:bg-slate-800 dark:text-brand-200' : 'text-slate-600 hover:bg-white/80 hover:text-slate-950 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white'"
      :aria-current="active === item.id ? 'page' : undefined"
      :aria-label="item.id === 'work' && workflow === 'repair' ? 'Ремонт' : item.label"
      :data-order-usage="`workspace-${item.id}`"
      @click="emit('select', item.id)"
    >
      <component :is="item.icon" :size="15" class="hidden shrink-0 sm:block" aria-hidden="true" />
      <span class="whitespace-nowrap" data-workspace-label>{{ item.id === 'work' && workflow === 'repair' ? 'Ремонт' : item.label }}</span>
    </button>
  </nav>
</template>
