<script setup lang="ts">
import type { CatalogDecisionItem, CatalogDecisionSort } from '../../services/catalog-decision-api';
const props = defineProps<{ items: CatalogDecisionItem[]; selectedIds: number[]; sort: CatalogDecisionSort; direction: 'asc' | 'desc' }>();
const emit = defineEmits<{ sort: [value: CatalogDecisionSort]; toggle: [item: CatalogDecisionItem] }>();
const money = (value: number | null | undefined) => value === null || value === undefined ? '—' : `${value.toLocaleString('ru-BY')} BYN`;
const sortLabel = (key: CatalogDecisionSort, label: string) => `${label}${props.sort === key ? (props.direction === 'asc' ? ' ↑' : ' ↓') : ''}`;
const selected = (id: number) => props.selectedIds.includes(id);
const mobileSorts: Array<{ key: CatalogDecisionSort; label: string }> = [
  { key: 'title', label: 'Модель' },
  { key: 'retail_price', label: 'Розница' },
  { key: 'purchase_cost', label: 'Закупка' },
  { key: 'rrc', label: 'РРЦ' },
  { key: 'margin_abs', label: 'Маржа' },
  { key: 'margin_pct', label: 'Маржа %' },
  { key: 'availability', label: 'Остаток' },
];
</script>

<template>
  <div class="space-y-2">
    <section class="rounded-xl border border-gray-200 bg-white p-3 md:hidden" aria-label="Сортировка каталога">
      <p class="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">Сортировка</p>
      <div class="flex flex-wrap gap-1.5">
        <button v-for="item in mobileSorts" :key="item.key" type="button" class="rounded-full border px-2.5 py-1.5 text-xs font-medium transition" :class="sort === item.key ? 'border-teal-600 bg-teal-600 text-white' : 'border-gray-200 text-gray-700'" :aria-pressed="sort === item.key" @click="emit('sort', item.key)">{{ sortLabel(item.key, item.label) }}</button>
      </div>
    </section>
    <div class="grid gap-2 md:hidden">
      <article v-for="item in items" :key="item.id" class="rounded-xl border border-gray-200 bg-white p-3 shadow-sm"><div class="flex gap-3"><img v-if="item.main_image" :src="item.main_image" alt="" class="h-16 w-16 rounded-lg object-cover" /><div class="min-w-0 flex-1"><a :href="`/manager/products/${item.id}`" class="line-clamp-2 font-semibold text-gray-900 hover:text-teal-700">{{ item.title }}</a><p class="mt-1 text-xs text-gray-500">{{ [item.brand_title, item.series_title, item.cooling_power_kw ? `${item.cooling_power_kw} кВт` : ''].filter(Boolean).join(' · ') }}</p></div><button type="button" class="h-9 shrink-0 rounded-lg border px-2 text-xs font-semibold" :class="selected(item.id) ? 'border-teal-600 bg-teal-600 text-white' : 'border-gray-200 text-teal-700'" @click="emit('toggle', item)">{{ selected(item.id) ? 'Выбран' : 'Выбрать' }}</button></div><div class="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 border-t border-gray-100 pt-2 text-sm"><span class="text-gray-500">Розница</span><strong class="text-right">{{ money(item.retail_price_byn) }}</strong><span class="text-gray-500">Закупка</span><span class="text-right">{{ money(item.purchase_cost_byn) }}</span><span class="text-gray-500">РРЦ</span><span class="text-right">{{ money(item.recommended_price_byn) }}</span><span class="text-gray-500">Маржа</span><span class="text-right">{{ item.margin_pct == null ? '—' : `${Math.round(item.margin_pct * 100)}%` }}</span><span class="text-gray-500">Поставка</span><span class="text-right" :class="item.availability === 'in_stock' ? 'text-emerald-700' : 'text-gray-500'">{{ item.availability === 'in_stock' ? `${item.supplier_name || '—'} · ${item.supplier_qty}` : 'Под заказ' }}</span></div></article>
    </div>
    <div class="hidden overflow-x-auto rounded-xl border border-gray-200 bg-white md:block"><table class="min-w-full text-left text-sm"><thead class="bg-gray-50 text-xs uppercase text-gray-500"><tr><th class="w-20 px-3 py-3">В подбор</th><th class="px-3 py-3"><button @click="emit('sort', 'title')">{{ sortLabel('title', 'Модель') }}</button></th><th class="px-3 py-3"><button @click="emit('sort', 'retail_price')">{{ sortLabel('retail_price', 'Розница') }}</button></th><th class="px-3 py-3"><button @click="emit('sort', 'purchase_cost')">{{ sortLabel('purchase_cost', 'Закупка') }}</button></th><th class="px-3 py-3"><button @click="emit('sort', 'rrc')">{{ sortLabel('rrc', 'РРЦ') }}</button></th><th class="px-3 py-3"><button @click="emit('sort', 'margin_abs')">{{ sortLabel('margin_abs', 'Маржа') }}</button></th><th class="px-3 py-3"><button @click="emit('sort', 'availability')">{{ sortLabel('availability', 'Поставщик / остаток') }}</button></th></tr></thead><tbody class="divide-y divide-gray-100"><tr v-for="item in items" :key="item.id"><td class="px-3 py-3"><button type="button" class="rounded-lg border px-2.5 py-1.5 text-xs font-semibold" :class="selected(item.id) ? 'border-teal-600 bg-teal-600 text-white' : 'border-gray-200 text-teal-700'" @click="emit('toggle', item)">{{ selected(item.id) ? 'Выбран' : 'Добавить' }}</button></td><td class="px-3 py-3"><a :href="`/manager/products/${item.id}`" class="font-semibold text-teal-700 hover:underline">{{ item.title }}</a><div class="text-xs text-gray-500">{{ [item.brand_title, item.series_title, item.cooling_power_kw ? `${item.cooling_power_kw} кВт` : ''].filter(Boolean).join(' · ') }}</div></td><td class="px-3 py-3">{{ money(item.retail_price_byn) }}</td><td class="px-3 py-3">{{ money(item.purchase_cost_byn) }}</td><td class="px-3 py-3">{{ money(item.recommended_price_byn) }}</td><td class="px-3 py-3"><div>{{ money(item.margin_abs_byn) }}</div><div class="text-xs text-gray-500">{{ item.margin_pct == null ? '—' : `${Math.round(item.margin_pct * 100)}%` }}</div></td><td class="px-3 py-3"><div>{{ item.supplier_name || '—' }}</div><span :class="item.availability === 'in_stock' ? 'text-emerald-700' : 'text-gray-500'">{{ item.availability === 'in_stock' ? `В наличии: ${item.supplier_qty}` : 'Под заказ' }}</span></td></tr></tbody></table></div>
    <p v-if="items.length === 0" class="rounded-xl border border-dashed border-gray-200 bg-white p-10 text-center text-sm text-gray-500">По этому запросу товаров нет</p>
  </div>
</template>
