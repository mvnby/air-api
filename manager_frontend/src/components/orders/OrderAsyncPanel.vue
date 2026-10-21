<script setup lang="ts">
import { nextTick, onMounted, onScopeDispose, shallowRef, ref, type Component } from 'vue';
const props = defineProps<{ load: () => Promise<{ default: Component }>; label: string }>();
const component = shallowRef<Component | null>(null);
const loading = ref(false);
const failed = ref(false);
let generation = 0;
let task: Promise<boolean> | null = null;
const load = (): Promise<boolean> => {
  if (component.value) return Promise.resolve(true);
  if (task) return task;
  task = loadComponent().finally(() => { task = null; });
  return task;
};
const loadComponent = async () => {
  const request = ++generation;
  loading.value = true;
  failed.value = false;
  try {
    const result = await props.load();
    if (request === generation) component.value = result.default;
    await nextTick();
    return request === generation;
  } catch {
    if (request === generation) failed.value = true;
    return false;
  } finally {
    if (request === generation) loading.value = false;
  }
};
onMounted(load);
onScopeDispose(() => { generation++; });
defineExpose({ ready: load });
</script>

<template>
  <slot v-if="component" :component="component" />
  <div v-else class="min-h-48 rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900" :aria-busy="loading" :aria-label="label">
    <div v-if="failed" role="alert">
      <p class="text-sm">Не удалось загрузить раздел «{{ label }}».</p>
      <button type="button" class="btn-mini-outline mt-3 min-h-9 focus-visible:ring-2 focus-visible:ring-brand-500" @click="load">Повторить загрузку раздела</button>
    </div>
    <div v-else role="status" class="space-y-3">
      <p class="text-sm text-slate-600 dark:text-slate-300">Загружаем раздел «{{ label }}»…</p>
      <div aria-hidden="true" class="h-9 rounded-lg bg-slate-200 motion-safe:animate-pulse dark:bg-slate-800" />
      <div aria-hidden="true" class="h-16 rounded-lg bg-slate-200 motion-safe:animate-pulse dark:bg-slate-800" />
    </div>
  </div>
</template>
