<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { Link2 } from 'lucide-vue-next';
import type { CatalogDecisionItem } from '../../services/catalog-decision-api';

const props = defineProps<{ item?: CatalogDecisionItem | null }>();
const url = computed(() => props.item?.is_published ? props.item.public_site_url : null);
const state = ref<'idle' | 'copied' | 'manual'>('idle');
const manualInput = ref<HTMLInputElement | null>(null);

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
    manualInput.value?.focus();
  }
};
</script>

<template>
  <div v-if="url" class="min-w-0 space-y-1">
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
    {{ item?.is_published === false ? 'Модель не опубликована.' : 'Публичная карточка недоступна на выбранной витрине.' }}
  </p>
</template>
