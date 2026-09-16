<script setup lang="ts">
import { computed, ref } from 'vue';
import { ExternalLink, X } from 'lucide-vue-next';
import { useDialogA11y } from '../../composables/useDialogA11y';
import type { CatalogDecisionItem } from '../../services/catalog-decision-api';
import CatalogMoney from './CatalogMoney.vue';

const props = defineProps<{ open: boolean; item?: CatalogDecisionItem | null }>();
const emit = defineEmits<{ close: [] }>();

const dialogRef = ref<HTMLElement | null>(null);
const closeButtonRef = ref<HTMLElement | null>(null);
const formLabels: Record<string, string> = {
  wall: 'Настенный', console: 'Консольный', cassette: 'Кассетный', duct: 'Канальный', floor_ceiling: 'Напольно-потолочный', column: 'Колонный',
};
const wifiLabels: Record<string, string> = { builtin: 'Встроен', ready: 'Опция', none: 'Нет' };
const formFactor = computed(() => formLabels[props.item?.indoor_form_factor || ''] || '—');
const wifi = computed(() => wifiLabels[props.item?.wifi || ''] || '—');
const cooling = computed(() => props.item?.cooling_power_kw == null ? '—' : `${props.item.cooling_power_kw} кВт`);
const heating = computed(() => props.item?.heating_min_c == null ? '—' : `До ${props.item.heating_min_c} °C`);
const area = computed(() => props.item?.area_m2 == null ? '—' : `${props.item.area_m2} м²`);
const availability = computed(() => props.item?.availability === 'in_stock' ? 'В наличии' : 'Нет в наличии');
const close = () => emit('close');

useDialogA11y({
  open: computed(() => props.open),
  dialogRef,
  initialFocusRef: closeButtonRef,
  close,
});
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-[130] flex items-end justify-center bg-slate-950/55 p-0 sm:items-center sm:p-4" @mousedown.self="close">
      <section ref="dialogRef" role="dialog" aria-modal="true" aria-labelledby="catalog-decision-product-details-title" tabindex="-1" class="max-h-[94vh] w-full max-w-2xl overflow-y-auto rounded-t-lg border border-slate-200 bg-white shadow-2xl outline-none sm:rounded-lg">
        <header class="flex items-start justify-between gap-4 border-b border-slate-200 px-4 py-3 sm:px-5">
          <div class="min-w-0">
            <h2 id="catalog-decision-product-details-title" class="truncate text-base font-semibold text-slate-950">{{ item?.title || 'Карточка модели' }}</h2>
            <p v-if="item && (item.brand_title || item.series_title)" class="mt-1 text-sm text-slate-600">{{ [item.brand_title, item.series_title].filter(Boolean).join(' · ') }}</p>
          </div>
          <button ref="closeButtonRef" type="button" class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100" aria-label="Закрыть" @click="close"><X class="h-5 w-5" /></button>
        </header>
        <div v-if="item" class="grid gap-4 p-4 sm:grid-cols-[10rem_1fr] sm:p-5">
          <img v-if="item.main_image" :src="item.main_image" alt="" class="h-40 w-full rounded-lg bg-slate-50 object-contain">
          <div v-else class="hidden sm:block"></div>
          <dl class="grid grid-cols-2 gap-x-5 gap-y-3 text-sm">
            <div><dt class="text-slate-500">Цена клиенту</dt><dd class="mt-0.5 font-semibold text-slate-950"><CatalogMoney :value="item.retail_price_byn" /></dd></div>
            <div><dt class="text-slate-500">РРЦ</dt><dd class="mt-0.5 text-slate-950"><CatalogMoney :value="item.recommended_price_byn" /></dd></div>
            <div><dt class="text-slate-500">Охлаждение</dt><dd class="mt-0.5 text-slate-950">{{ cooling }}</dd></div>
            <div><dt class="text-slate-500">Обогрев</dt><dd class="mt-0.5 text-slate-950">{{ heating }}</dd></div>
            <div><dt class="text-slate-500">Инвертор</dt><dd class="mt-0.5 text-slate-950">{{ item.is_inverter ? 'Да' : 'Нет' }}</dd></div>
            <div><dt class="text-slate-500">Wi-Fi</dt><dd class="mt-0.5 text-slate-950">{{ wifi }}</dd></div>
            <div><dt class="text-slate-500">Внутренний блок</dt><dd class="mt-0.5 text-slate-950">{{ formFactor }}</dd></div>
            <div><dt class="text-slate-500">Площадь</dt><dd class="mt-0.5 text-slate-950">{{ area }}</dd></div>
            <div><dt class="text-slate-500">Поставщик</dt><dd class="mt-0.5 text-slate-950">{{ item.supplier_name || '—' }}</dd></div>
            <div><dt class="text-slate-500">Остаток</dt><dd class="mt-0.5 text-slate-950">{{ availability }}{{ item.supplier_qty == null ? '' : ` · ${item.supplier_qty} шт.` }}</dd></div>
          </dl>
        </div>
        <footer class="flex justify-end gap-2 border-t border-slate-200 px-4 py-3 sm:px-5">
          <a v-if="item" :href="`/manager/products/${item.id}`" class="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-300 px-4 text-sm font-semibold text-slate-700 hover:bg-slate-50"><ExternalLink class="h-4 w-4" />Редактировать товар</a>
          <button type="button" class="h-10 rounded-lg bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700" @click="close">Закрыть</button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>
