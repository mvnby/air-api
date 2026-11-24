<script setup lang="ts">
import { ChevronDown } from 'lucide-vue-next';
import type { DraftOption } from '../../services/personal-offers';
import { productReaderUrl } from '../../services/product-reader-api';

const props = defineProps<{
  option: DraftOption;
  title: string;
  image?: string | null;
  isPackage: boolean;
}>();
const noteInitiallyOpen = Boolean(props.option.note?.trim());
</script>

<template>
  <div class="col-span-full row-start-1 flex min-w-0 items-center gap-3 lg:col-span-1 lg:col-start-2">
    <img v-if="productReaderUrl(image)" :src="productReaderUrl(image) ?? undefined" alt="" loading="lazy" class="h-12 w-16 shrink-0 rounded-md bg-gray-50 object-contain" />
    <p class="min-w-0 break-words text-sm font-semibold">{{ title }}</p>
  </div>
  <label class="col-start-1 row-start-2 flex items-center gap-2 text-xs font-medium lg:col-start-3 lg:row-start-1">
    <span class="whitespace-nowrap">Цена, BYN</span>
    <input v-model="option.price_byn" type="text" inputmode="decimal" maxlength="14" :aria-label="'Цена, BYN — ' + title" class="field-input option-price min-w-0" />
  </label>
  <details :open="noteInitiallyOpen" class="group/note col-span-full min-w-0 lg:col-span-3 lg:col-start-2">
    <summary class="inline-flex min-h-8 cursor-pointer list-none items-center gap-1 text-xs font-semibold text-[var(--kitlane-accent-text)] [&::-webkit-details-marker]:hidden">
      {{ option.note?.trim() ? 'Пояснение для клиента' : 'Добавить пояснение' }}
      <ChevronDown class="h-4 w-4 group-open/note:rotate-180" aria-hidden="true" />
    </summary>
    <textarea v-model="option.note" rows="2" maxlength="500" :aria-label="isPackage ? 'Помещение или пояснение для клиента' : 'Пояснение для клиента'" class="field-input block w-full" />
  </details>
</template>

<style scoped>
.option-price { width: 6.75rem; }
</style>
