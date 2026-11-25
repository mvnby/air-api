<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { Check, Link2, Link2Off } from 'lucide-vue-next';
import type { CatalogDecisionItem } from '../../services/catalog-decision-api';

const props = defineProps<{ item?: CatalogDecisionItem | null; compact?: boolean }>();
const url = computed(() => props.item?.is_published ? props.item.public_site_url : null);
const unavailable = computed(() => props.item?.is_published === false
  ? 'Модель не опубликована.'
  : 'Публичная карточка недоступна на выбранной витрине.');
const state = ref<'idle' | 'copied' | 'manual'>('idle');
const manualInput = ref<HTMLInputElement | null>(null);
const manualDialog = ref<HTMLDialogElement | null>(null);

watch(url, () => { state.value = 'idle'; });

const copy = async () => {
  const value = url.value;
  if (!value) return;
  try {
    await navigator.clipboard.writeText(value);
    if (url.value === value) state.value = 'copied';
  } catch {
    if (url.value !== value) return;
    state.value = 'manual';
    await nextTick();
    manualDialog.value?.showModal();
    manualInput.value?.focus();
  }
};
</script>

<template>
  <template v-if="compact">
    <div v-if="url" class="inline-flex">
      <button type="button" class="inline-flex size-9 items-center justify-center rounded-lg border border-[var(--kitlane-control-border)] text-[var(--kitlane-accent-text)] hover:bg-[var(--kitlane-accent-soft)]" aria-label="Копировать ссылку на сайте" :title="state === 'copied' ? 'Ссылка скопирована' : 'Скопировать ссылку на модель'" @click="copy">
        <component :is="state === 'copied' ? Check : Link2" class="size-4" aria-hidden="true" />
      </button>
      <span role="status" class="sr-only">{{ state === 'copied' ? 'Ссылка скопирована' : '' }}</span>
      <dialog v-if="state === 'manual'" ref="manualDialog" aria-label="Ссылка на модель" class="m-auto w-[calc(100%-2rem)] max-w-md space-y-3 rounded-xl border border-[var(--mv-border)] bg-[var(--mv-surface)] p-4 text-left text-[var(--mv-text)] backdrop:bg-slate-950/50" @close="state = 'idle'">
        <label class="block text-sm font-semibold">
          Скопируйте ссылку вручную
          <input ref="manualInput" :value="url" readonly class="field-input mt-2 w-full" @focus="($event.currentTarget as HTMLInputElement).select()">
        </label>
        <form method="dialog" class="text-right">
          <button type="submit" class="btn-mini-outline">Закрыть</button>
        </form>
      </dialog>
    </div>
    <span v-else role="img" :aria-label="unavailable" :title="unavailable" class="inline-flex size-9 items-center justify-center text-[var(--kitlane-muted)]"><Link2Off class="size-4" aria-hidden="true" /></span>
  </template>
  <div v-else-if="url" class="min-w-0 space-y-1">
    <button type="button" class="btn-mini-outline min-h-10" @click="copy">
      <Link2 class="h-4 w-4" aria-hidden="true" />Копировать ссылку на сайте
    </button>
    <p v-if="state === 'copied'" role="status" class="text-xs font-medium text-[var(--kitlane-accent-text)]">Ссылка скопирована</p>
    <label v-if="state === 'manual'" class="block text-xs text-[var(--mv-text-muted)]">
      Скопируйте ссылку вручную
      <input ref="manualInput" :value="url" readonly class="field-input mt-1 w-full text-sm" @focus="($event.currentTarget as HTMLInputElement).select()">
    </label>
  </div>
  <p v-else class="text-xs text-[var(--mv-text-muted)]">
    {{ unavailable }}
  </p>
</template>
