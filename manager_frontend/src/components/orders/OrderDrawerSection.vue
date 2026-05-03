<script setup lang="ts">
defineProps<{
  title: string;
  summary?: string;
  expanded: boolean;
  tone?: 'default' | 'blue' | 'amber' | 'emerald';
  hasError?: boolean;
}>();

const emit = defineEmits<{
  'update:expanded': [value: boolean];
}>();

const toneClasses = {
  default: 'border-slate-200 bg-slate-50',
  blue: 'border-blue-100 bg-blue-50/30',
  amber: 'border-amber-100 bg-amber-50/30',
  emerald: 'border-emerald-100 bg-emerald-50/40',
};
</script>

<template>
  <section class="mt-4 rounded-2xl border p-0 shadow-sm" :class="[toneClasses[tone || 'default'], hasError ? 'ring-2 ring-red-400/50' : '']">
    <button
      type="button"
      class="flex w-full items-center justify-between gap-3 rounded-2xl px-4 py-3 text-left"
      :aria-expanded="expanded"
      @click="emit('update:expanded', !expanded)"
    >
      <div class="min-w-0">
        <h3 class="text-sm font-semibold text-slate-900">{{ title }}</h3>
        <p v-if="summary" class="mt-0.5 truncate text-xs text-slate-500">{{ summary }}</p>
      </div>
      <span class="material-icons-round shrink-0 text-[20px] text-slate-500" aria-hidden="true">{{ expanded ? 'expand_less' : 'expand_more' }}</span>
    </button>

    <div v-if="expanded" class="border-t border-white/70 px-4 pb-4 pt-3">
      <slot />
    </div>
  </section>
</template>
