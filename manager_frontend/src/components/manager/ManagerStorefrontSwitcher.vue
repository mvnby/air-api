<script setup lang="ts">
import { computed } from 'vue';

import type { ManagerStorefrontResponse } from '../../client';

const props = defineProps<{
  storefronts: ManagerStorefrontResponse[];
  selectedSlug: string | null;
  disabled?: boolean;
  collapsed?: boolean;
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

const compactLabel = computed(() => {
  const label = currentStorefront.value?.city || currentStorefront.value?.display_name || '';
  return Array.from(label.trim()).slice(0, 2).join('').toUpperCase();
});
</script>

<template>
  <section
    v-if="currentStorefront"
    aria-label="Текущая витрина"
    :class="collapsed ? 'md:flex md:justify-center' : ''"
  >
    <div
      v-if="collapsed"
      data-testid="collapsed-storefront-badge"
      class="hidden h-9 min-w-9 items-center justify-center rounded-lg border border-teal-200 bg-teal-50 px-1 text-[11px] font-bold text-teal-700 md:flex"
      :title="`Витрина: ${storefrontLabel(currentStorefront)}`"
      :aria-label="`Текущая витрина: ${storefrontLabel(currentStorefront)}`"
    >
      {{ compactLabel }}
    </div>

    <div
      class="rounded-xl border border-gray-200 bg-gray-50 p-2.5"
      :class="collapsed ? 'md:hidden' : ''"
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
        v-if="storefronts.length > 1"
        class="mt-2 grid gap-1 rounded-lg bg-gray-100 p-1"
        :class="storefronts.length === 2 ? 'grid-cols-2' : 'grid-cols-1'"
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
    </div>
  </section>
</template>
