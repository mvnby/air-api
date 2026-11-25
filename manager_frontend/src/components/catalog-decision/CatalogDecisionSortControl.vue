<script setup lang="ts">
import { useId } from 'vue';
import { ArrowDown, ArrowUp } from 'lucide-vue-next';
import type { CatalogDecisionSort } from '../../services/catalog-decision-api';

defineProps<{
  sort: CatalogDecisionSort;
  direction: 'asc' | 'desc';
  hasFormFilter?: boolean;
}>();
const emit = defineEmits<{ sort: [value: CatalogDecisionSort] }>();
const descriptionId = useId();

const options: Array<{ key: CatalogDecisionSort; label: string }> = [
  { key: 'recommended', label: 'Настенные первыми' },
  { key: 'title', label: 'Модель' },
  { key: 'cooling_power', label: 'Мощность охлаждения' },
  { key: 'retail_price', label: 'Цена клиенту' },
  { key: 'purchase_cost', label: 'Закупка' },
  { key: 'rrc', label: 'РРЦ' },
  { key: 'margin_abs', label: 'Маржа' },
  { key: 'margin_pct', label: 'Маржа %' },
  { key: 'availability', label: 'Остаток' },
];
</script>

<template>
  <div class="flex min-w-0 items-center gap-1" role="group" aria-label="Сортировка каталога">
    <label class="flex min-w-0 items-center gap-2">
      <span class="text-xs text-[var(--kitlane-muted)]">Сортировка</span>
      <select :value="sort" class="h-9 w-52 min-w-0 rounded-lg border border-[var(--kitlane-control-border)] bg-[var(--mv-surface)] px-2 text-sm" aria-label="Сортировать модели" :aria-describedby="sort === 'recommended' && !hasFormFilter ? descriptionId : undefined" @change="emit('sort', ($event.target as HTMLSelectElement).value as CatalogDecisionSort)">
        <option v-for="option in options" :key="option.key" :value="option.key">{{ option.label }}</option>
      </select>
    </label>
    <span v-if="sort === 'recommended' && !hasFormFilter" :id="descriptionId" class="sr-only">Другие формы блоков тоже в подборе.</span>
    <button v-if="sort !== 'recommended'" type="button" class="inline-flex size-9 shrink-0 items-center justify-center rounded-lg border border-[var(--kitlane-control-border)] bg-[var(--mv-surface)] hover:bg-[var(--kitlane-accent-soft)]" title="Изменить направление сортировки" :aria-label="direction === 'asc' ? 'Изменить порядок: сейчас по возрастанию' : 'Изменить порядок: сейчас по убыванию'" @click="emit('sort', sort)">
      <component :is="direction === 'asc' ? ArrowUp : ArrowDown" class="size-4" aria-hidden="true" />
    </button>
  </div>
</template>
