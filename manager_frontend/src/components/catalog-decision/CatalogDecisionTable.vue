<script setup lang="ts">
import type { CatalogDecisionItem, CatalogDecisionSort } from '../../services/catalog-decision-api';
const props = defineProps<{ items: CatalogDecisionItem[]; sort: CatalogDecisionSort; direction: 'asc' | 'desc' }>();
const emit = defineEmits<{ sort: [value: CatalogDecisionSort] }>();
const money = (value: number | null | undefined) => value === null || value === undefined ? '—' : `${value.toLocaleString('ru-BY')} BYN`;
const sortLabel = (key: CatalogDecisionSort, label: string) => `${label}${props.sort === key ? (props.direction === 'asc' ? ' ↑' : ' ↓') : ''}`;
</script>

<template>
  <div class="overflow-x-auto rounded-xl border border-gray-200 bg-white">
    <table class="min-w-full text-left text-sm"><thead class="bg-gray-50 text-xs uppercase text-gray-500"><tr><th class="px-3 py-3"><button @click="emit('sort', 'title')">{{ sortLabel('title', 'Модель') }}</button></th><th class="px-3 py-3"><button @click="emit('sort', 'retail_price')">{{ sortLabel('retail_price', 'Розница') }}</button></th><th class="px-3 py-3"><button @click="emit('sort', 'purchase_cost')">{{ sortLabel('purchase_cost', 'Закупка') }}</button></th><th class="px-3 py-3"><button @click="emit('sort', 'rrc')">{{ sortLabel('rrc', 'РРЦ') }}</button></th><th class="px-3 py-3"><button @click="emit('sort', 'margin_abs')">{{ sortLabel('margin_abs', 'Маржа') }}</button></th><th class="px-3 py-3"><button @click="emit('sort', 'availability')">{{ sortLabel('availability', 'Поставщик / остаток') }}</button></th></tr></thead>
      <tbody class="divide-y divide-gray-100"><tr v-for="item in items" :key="item.id"><td class="px-3 py-3"><a :href="`/manager/products/${item.id}`" class="font-semibold text-teal-700 hover:underline">{{ item.title }}</a><div class="text-xs text-gray-500">{{ [item.brand_title, item.series_title, item.cooling_power_kw ? `${item.cooling_power_kw} кВт` : ''].filter(Boolean).join(' · ') }}</div></td><td class="px-3 py-3">{{ money(item.retail_price_byn) }}</td><td class="px-3 py-3">{{ money(item.purchase_cost_byn) }}</td><td class="px-3 py-3">{{ money(item.recommended_price_byn) }}</td><td class="px-3 py-3"><div>{{ money(item.margin_abs_byn) }}</div><div class="text-xs text-gray-500">{{ item.margin_pct === null || item.margin_pct === undefined ? '—' : `${Math.round(item.margin_pct * 100)}%` }}</div></td><td class="px-3 py-3"><div>{{ item.supplier_name || '—' }}</div><span :class="item.availability === 'in_stock' ? 'text-emerald-700' : 'text-gray-500'">{{ item.availability === 'in_stock' ? `В наличии: ${item.supplier_qty}` : 'Нет в наличии' }}</span></td></tr></tbody>
    </table>
    <p v-if="items.length === 0" class="p-10 text-center text-sm text-gray-500">По этому запросу товаров нет</p>
  </div>
</template>
