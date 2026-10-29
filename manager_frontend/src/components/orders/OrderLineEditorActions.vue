<script setup lang="ts">
import { Check, Trash2 } from 'lucide-vue-next';

defineProps<{
  commitLabel: string;
  commitAriaLabel?: string;
  cancelAriaLabel?: string;
  removeLabel?: string;
  removeUsage?: string;
}>();
defineEmits<{ commit: []; cancel: []; remove: [] }>();
</script>

<template>
  <div data-line-editor-actions class="sticky bottom-0 z-10 flex flex-wrap items-center justify-end gap-2 border-t border-slate-200 bg-white px-3 py-2 shadow-[0_-3px_10px_-6px_rgba(15,23,42,0.3)] dark:border-slate-700 dark:bg-slate-950">
    <button v-if="removeLabel" type="button" class="mr-auto inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-red-200 bg-red-50 text-red-600 hover:bg-red-100 focus-visible:ring-2 focus-visible:ring-red-500 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400" :aria-label="removeLabel" :title="removeLabel" :data-order-usage="removeUsage" @click="$emit('remove')"><Trash2 class="h-5 w-5 shrink-0" aria-hidden="true" /></button>
    <button type="button" class="btn-mini-outline min-h-11 justify-center" :aria-label="cancelAriaLabel" @click="$emit('cancel')">Отмена</button>
    <button type="button" class="btn-mini min-h-11 justify-center" :aria-label="commitAriaLabel" @click="$emit('commit')"><Check class="h-5 w-5 shrink-0" aria-hidden="true" />{{ commitLabel }}</button>
  </div>
</template>
