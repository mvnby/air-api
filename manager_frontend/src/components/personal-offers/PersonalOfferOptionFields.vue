<script setup lang="ts">
import type { DraftOption } from '../../services/personal-offers';
import { productReaderUrl } from '../../services/product-reader-api';

defineProps<{
  option: DraftOption;
  title: string;
  image?: string | null;
  isPackage: boolean;
}>();
</script>

<template>
  <div class="col-span-full row-start-1 flex min-w-0 items-center gap-3 lg:col-span-1 lg:col-start-2">
    <img v-if="productReaderUrl(image)" :src="productReaderUrl(image) ?? undefined" alt="" loading="lazy" class="h-12 w-16 shrink-0 rounded-md bg-gray-50 object-contain" />
    <p class="min-w-0 break-words text-sm font-semibold">{{ title }}</p>
  </div>
  <div class="col-span-full grid min-w-0 grid-cols-[minmax(6rem,8rem)_minmax(0,1fr)] items-end gap-2 lg:col-span-2 lg:col-start-2">
    <label class="block min-w-0 text-xs font-medium">
      Цена, BYN
      <input v-model="option.price_byn" type="text" inputmode="decimal" maxlength="14" :aria-label="'Цена, BYN — ' + title" class="field-input option-input" />
    </label>
    <label class="block min-w-0 text-xs font-medium">
      {{ isPackage ? 'Помещение или пояснение' : 'Пояснение для клиента' }}
      <textarea v-model="option.note" rows="1" maxlength="500" class="field-input option-input resize-y" />
    </label>
  </div>
</template>

<style scoped>
.option-input {
  display: block;
  height: 2.25rem;
  min-height: 2.25rem;
  margin-top: 0.25rem;
  padding: 0.4rem 0.625rem;
  font-size: 0.875rem;
  line-height: 1.25rem;
}
</style>
