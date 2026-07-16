<script setup lang="ts">
import { CreditCard, FileText, PackageCheck, Wrench } from 'lucide-vue-next';
import type { OrderWorkspaceLane, OrderWorkspaceTarget } from './order-workspace';

defineProps<{ lanes: OrderWorkspaceLane[] }>();
const emit = defineEmits<{ open: [target: OrderWorkspaceTarget] }>();

const icons = {
  product: PackageCheck,
  work: Wrench,
  documents: FileText,
  payment: CreditCard,
};

const toneClasses = {
  slate: 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-200',
  sky: 'border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-200',
  amber: 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200',
  teal: 'border-teal-200 bg-teal-50 text-teal-900 dark:border-teal-500/30 dark:bg-teal-500/10 dark:text-teal-200',
  emerald: 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200',
  rose: 'border-rose-200 bg-rose-50 text-rose-900 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200',
};
</script>

<template>
  <section class="mt-3">
    <div class="mb-2">
      <h3 class="text-sm font-semibold text-slate-900 dark:text-white">Ход заказа</h3>
      <p class="text-xs text-slate-500 dark:text-slate-400">Независимые направления продажи и монтажа</p>
    </div>
    <div class="grid gap-2 sm:grid-cols-2">
      <button
        v-for="lane in lanes"
        :key="lane.id"
        type="button"
        class="flex min-h-[88px] items-start gap-3 rounded-xl border p-3 text-left transition hover:-translate-y-px hover:shadow-sm"
        :class="toneClasses[lane.tone]"
        @click="emit('open', lane.target)"
      >
        <component :is="icons[lane.id]" :size="18" class="mt-0.5 shrink-0" aria-hidden="true" />
        <span class="min-w-0">
          <span class="block text-[11px] font-semibold uppercase tracking-[0.08em] opacity-70">{{ lane.label }}</span>
          <span class="mt-0.5 block text-sm font-semibold">{{ lane.status }}</span>
          <span class="mt-1 block text-xs opacity-75">{{ lane.detail }}</span>
        </span>
      </button>
    </div>
  </section>
</template>
