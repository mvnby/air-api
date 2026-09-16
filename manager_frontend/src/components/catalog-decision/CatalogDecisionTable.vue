<script setup lang="ts">
import { computed, useSlots } from 'vue';
import type { CatalogDecisionItem, CatalogDecisionSort } from '../../services/catalog-decision-api';
import CatalogMoney from './CatalogMoney.vue';

const props = defineProps<{
  items: CatalogDecisionItem[];
  selectedIds: number[];
  sort: CatalogDecisionSort;
  direction: 'asc' | 'desc';
  busy?: boolean;
  existingIds?: number[];
}>();
const emit = defineEmits<{
  sort: [value: CatalogDecisionSort];
  toggle: [item: CatalogDecisionItem];
  details: [item: CatalogDecisionItem];
}>();

const slots = useSlots();
const hasActions = computed(() => Boolean(slots.actions));
const formLabels: Record<string, string> = {
  wall: 'Настенный', console: 'Консольный', cassette: 'Кассетный', duct: 'Канальный', floor_ceiling: 'Напольно-потолочный', column: 'Колонный',
};
const wifiLabels: Record<string, string> = { builtin: 'Встроен', ready: 'Опция', none: 'Нет' };
const sortLabel = (key: CatalogDecisionSort, label: string) => `${label}${props.sort === key ? (props.direction === 'asc' ? ' ↑' : ' ↓') : ''}`;
const sortState = (key: CatalogDecisionSort) => props.sort !== key ? 'none' : props.direction === 'asc' ? 'ascending' : 'descending';
const inProposal = (id: number) => props.existingIds?.includes(id) ?? false;
const selected = (id: number) => props.selectedIds.includes(id);
const amount = (value: number | null | undefined, suffix: string) => value == null ? '—' : `${value} ${suffix}`;
const percent = (value: number | null | undefined) => value == null ? '—' : `${(value * 100).toLocaleString('ru-BY', { maximumFractionDigits: 2 })}%`;
const availability = (item: CatalogDecisionItem) => item.availability === 'in_stock' ? 'В наличии' : 'Нет в наличии';
const stock = (item: CatalogDecisionItem) => item.supplier_qty == null ? 'Остаток: —' : `Остаток: ${item.supplier_qty}`;
const specs = (item: CatalogDecisionItem) => [
  item.is_inverter ? 'Инвертор' : 'Обычный',
  `Охл.: ${amount(item.cooling_power_kw, 'кВт')}`,
  item.heating_min_c == null ? 'Обогрев: —' : `Обогрев до ${item.heating_min_c} °C`,
  `Wi-Fi: ${wifiLabels[item.wifi || ''] || '—'}`,
].join(' · ');
const identity = (item: CatalogDecisionItem) => [item.brand_title, item.series_title, formLabels[item.indoor_form_factor || '']].filter(Boolean).join(' · ');
const mobileSorts: Array<{ key: CatalogDecisionSort; label: string }> = [
  { key: 'title', label: 'Модель' },
  { key: 'retail_price', label: 'Цена клиенту' },
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
        <button v-for="item in mobileSorts" :key="item.key" type="button" class="rounded-full border px-2.5 py-1.5 text-xs font-medium transition" :class="sort === item.key ? 'border-brand-600 bg-brand-600 text-white' : 'border-gray-200 text-gray-700'" :aria-pressed="sort === item.key" @click="emit('sort', item.key)">{{ sortLabel(item.key, item.label) }}</button>
      </div>
    </section>

    <div v-if="items.length" class="grid gap-2 md:hidden">
      <article v-for="item in items" :key="item.id" class="rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
        <div class="flex gap-3">
          <img v-if="item.main_image" :src="item.main_image" alt="" class="h-16 w-16 shrink-0 rounded-lg bg-gray-50 object-contain">
          <div class="min-w-0 flex-1">
            <button type="button" class="line-clamp-2 text-left font-semibold text-brand-700 hover:underline" :aria-label="`Открыть карточку ${item.title}`" @click="emit('details', item)">{{ item.title }}</button>
            <p v-if="identity(item)" class="mt-1 text-xs text-gray-500">{{ identity(item) }}</p>
            <p class="mt-1 text-xs leading-5 text-gray-600">{{ specs(item) }}</p>
          </div>
          <button type="button" class="h-9 shrink-0 rounded-lg border px-2 text-xs font-semibold" :class="selected(item.id) ? 'border-brand-600 bg-brand-600 text-white' : 'border-gray-200 text-brand-700'" :aria-pressed="selected(item.id)" :disabled="busy || inProposal(item.id)" @click="emit('toggle', item)">{{ inProposal(item.id) ? 'В предложении' : selected(item.id) ? 'Выбран' : 'Выбрать' }}</button>
        </div>
        <div class="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 border-t border-gray-100 pt-2 text-sm">
          <span class="text-gray-500">Цена клиенту</span><strong class="text-right"><CatalogMoney :value="item.retail_price_byn" /></strong>
          <span class="text-gray-500">Закупка</span><span class="text-right"><CatalogMoney :value="item.purchase_cost_byn" /></span>
          <span class="text-gray-500">РРЦ</span><span class="text-right"><CatalogMoney :value="item.recommended_price_byn" /></span>
          <span class="text-gray-500">Маржа</span><span class="text-right"><CatalogMoney :value="item.margin_abs_byn" /><span class="text-xs text-gray-500"> · {{ percent(item.margin_pct) }}</span></span>
          <span class="text-gray-500">{{ item.supplier_name || 'Поставщик' }}</span><span class="text-right" :class="item.availability === 'in_stock' ? 'text-emerald-700' : 'text-gray-500'">{{ availability(item) }} · {{ stock(item) }}</span>
        </div>
        <div v-if="hasActions" class="mt-3 border-t border-gray-100 pt-2"><slot name="actions" :item="item" /></div>
      </article>
    </div>

    <div v-if="items.length" class="hidden overflow-x-auto rounded-xl border border-gray-200 bg-white md:block">
      <table class="min-w-full text-left text-sm">
        <thead class="bg-gray-50 text-xs uppercase text-gray-500">
          <tr>
            <th class="w-20 px-3 py-3"><span class="sr-only">В подбор</span></th>
            <th class="px-3 py-3" :aria-sort="sortState('title')"><button type="button" class="font-semibold hover:text-gray-900" @click="emit('sort', 'title')">{{ sortLabel('title', 'Модель') }}</button></th>
            <th class="px-3 py-3" :aria-sort="sortState('retail_price')"><button type="button" class="font-semibold hover:text-gray-900" @click="emit('sort', 'retail_price')">{{ sortLabel('retail_price', 'Цена клиенту') }}</button></th>
            <th class="px-3 py-3" :aria-sort="sortState('purchase_cost')"><button type="button" class="font-semibold hover:text-gray-900" @click="emit('sort', 'purchase_cost')">{{ sortLabel('purchase_cost', 'Закупка') }}</button></th>
            <th class="px-3 py-3" :aria-sort="sortState('rrc')"><button type="button" class="font-semibold hover:text-gray-900" @click="emit('sort', 'rrc')">{{ sortLabel('rrc', 'РРЦ') }}</button></th>
            <th class="px-3 py-3" :aria-sort="sortState('margin_abs')"><button type="button" class="font-semibold hover:text-gray-900" @click="emit('sort', 'margin_abs')">{{ sortLabel('margin_abs', 'Маржа') }}</button></th>
            <th class="px-3 py-3" :aria-sort="sortState('availability')"><button type="button" class="font-semibold hover:text-gray-900" @click="emit('sort', 'availability')">{{ sortLabel('availability', 'Остаток') }}</button></th>
            <th v-if="hasActions" class="px-3 py-3"><span class="sr-only">Действия</span></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          <tr v-for="item in items" :key="item.id" :class="selected(item.id) ? 'bg-brand-50/60' : ''">
            <td class="px-3 py-3"><button type="button" class="rounded-lg border px-2.5 py-1.5 text-xs font-semibold" :class="selected(item.id) ? 'border-brand-600 bg-brand-600 text-white' : 'border-gray-200 text-brand-700'" :aria-pressed="selected(item.id)" :disabled="busy || inProposal(item.id)" @click="emit('toggle', item)">{{ inProposal(item.id) ? 'В предложении' : selected(item.id) ? 'Выбран' : 'Добавить' }}</button></td>
            <td class="min-w-72 px-3 py-3"><div class="flex gap-2.5"><img v-if="item.main_image" :src="item.main_image" alt="" class="h-12 w-12 shrink-0 rounded-md bg-gray-50 object-contain"><div class="min-w-0"><button type="button" class="text-left font-semibold text-brand-700 hover:underline" :aria-label="`Открыть карточку ${item.title}`" @click="emit('details', item)">{{ item.title }}</button><div v-if="identity(item)" class="mt-0.5 text-xs text-gray-500">{{ identity(item) }}</div><div class="mt-1 text-xs leading-5 text-gray-600">{{ specs(item) }}</div></div></div></td>
            <td class="px-3 py-3 font-semibold"><CatalogMoney :value="item.retail_price_byn" /></td>
            <td class="px-3 py-3"><CatalogMoney :value="item.purchase_cost_byn" /></td>
            <td class="px-3 py-3"><CatalogMoney :value="item.recommended_price_byn" /></td>
            <td class="px-3 py-3"><CatalogMoney :value="item.margin_abs_byn" /><div class="mt-0.5 text-xs text-gray-500">{{ percent(item.margin_pct) }}</div></td>
            <td class="min-w-36 px-3 py-3"><div>{{ item.supplier_name || '—' }}</div><div class="mt-0.5 text-xs" :class="item.availability === 'in_stock' ? 'text-emerald-700' : 'text-gray-500'">{{ availability(item) }} · {{ stock(item) }}</div></td>
            <td v-if="hasActions" class="px-3 py-3"><slot name="actions" :item="item" /></td>
          </tr>
        </tbody>
      </table>
    </div>

    <slot v-if="!items.length" name="empty">
      <p class="rounded-xl border border-dashed border-gray-200 bg-white p-10 text-center text-sm text-gray-500">По этому запросу товаров нет</p>
    </slot>
  </div>
</template>
