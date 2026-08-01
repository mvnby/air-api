<script setup lang="ts">
import { computed } from 'vue';

import type { ManagerStorefrontResponse } from '../../client';

const props = defineProps<{
  storefronts: ManagerStorefrontResponse[];
  selectedSlug: string | null;
  disabled?: boolean;
}>();

const emit = defineEmits<{
  select: [slug: string];
}>();

const currentStorefront = computed(() => (
  props.storefronts.find((storefront) => storefront.slug === props.selectedSlug)
  ?? props.storefronts.find((storefront) => storefront.is_current)
  ?? props.storefronts[0]
  ?? null
));

const storefrontLabel = (storefront: ManagerStorefrontResponse) => (
  storefront.city
    ? `${storefront.display_name}, ${storefront.city}`
    : storefront.display_name
);

const onSelectChange = (event: Event) => {
  const value = (event.target as HTMLSelectElement).value;
  if (value) emit('select', value);
};
</script>

<template>
  <section
    v-if="currentStorefront"
    aria-label="Текущая витрина"
    class="rounded-xl border border-gray-200 bg-gray-50 p-2.5"
  >
    <div class="min-w-0 px-1">
      <div class="text-[10px] font-bold uppercase tracking-[0.16em] text-gray-400">Витрина</div>
      <div class="truncate text-xs font-semibold text-gray-800">
        {{ currentStorefront.display_name }}
      </div>
      <div v-if="currentStorefront.city" class="truncate text-[11px] text-gray-500">
        {{ currentStorefront.city }}
      </div>
    </div>

    <div
      v-if="storefronts.length === 2"
      class="mt-2 grid grid-cols-2 gap-1 rounded-lg bg-gray-100 p-1"
      role="group"
      aria-label="Выбор витрины"
    >
      <button
        v-for="storefront in storefronts"
        :key="storefront.slug"
        type="button"
        class="min-h-9 min-w-0 rounded-md px-2 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-1"
        :class="storefront.slug === selectedSlug
          ? 'bg-white text-teal-700 shadow-sm'
          : 'text-gray-600 hover:bg-white hover:text-gray-900'"
        :aria-pressed="storefront.slug === selectedSlug"
        :aria-label="`Переключиться: ${storefrontLabel(storefront)}`"
        :disabled="disabled || storefront.slug === selectedSlug"
        @click="emit('select', storefront.slug)"
      >
        <span class="block truncate">{{ storefront.display_name }}</span>
        <span v-if="storefront.city" class="block truncate text-[10px] font-normal opacity-70">
          {{ storefront.city }}
        </span>
      </button>
    </div>

    <label v-else-if="storefronts.length > 2" class="mt-2 block">
      <span class="sr-only">Выберите витрину</span>
      <select
        :value="selectedSlug || currentStorefront.slug"
        :disabled="disabled"
        aria-label="Выберите витрину"
        class="min-h-9 w-full rounded-lg border border-gray-300 bg-white px-2 text-xs font-medium text-gray-700 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/30 disabled:cursor-wait disabled:opacity-60"
        @change="onSelectChange"
      >
        <option v-for="storefront in storefronts" :key="storefront.slug" :value="storefront.slug">
          {{ storefrontLabel(storefront) }}
        </option>
      </select>
    </label>
  </section>
</template>
