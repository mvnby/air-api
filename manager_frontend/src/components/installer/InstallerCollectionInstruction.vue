<script setup lang="ts">
import { Banknote } from 'lucide-vue-next';
import type { InstallerCollection } from '../../services/installer-workspace';
defineProps<{ collection: InstallerCollection }>();
</script>
<template>
  <div v-if="collection.status === 'ready' && collection.amount != null && collection.currency" class="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-emerald-950 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-100" data-testid="collection-instruction">
    <p class="flex items-center gap-2 text-sm font-medium"><Banknote class="h-4 w-4" aria-hidden="true" />Вам поручено получить</p>
    <p class="mt-1 text-2xl font-bold tabular-nums">{{ collection.amount }} <span class="text-base font-medium">{{ collection.currency }}</span></p>
    <p class="mt-1 text-xs">Сумма указана менеджером для этой работы.</p>
  </div>
  <p v-else-if="collection.status === 'requires_review'" class="rounded-xl bg-amber-50 p-4 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-100" role="status">Поручение получить оплату требует уточнения. Свяжитесь с менеджером перед получением денег.</p>
  <p v-else class="rounded-xl bg-gray-50 p-4 text-sm text-gray-500 dark:bg-slate-800 dark:text-slate-300">Получение оплаты вам не поручено.</p>
</template>
