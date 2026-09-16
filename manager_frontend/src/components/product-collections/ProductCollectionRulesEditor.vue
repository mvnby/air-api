<script setup lang="ts">
import { computed } from 'vue';
import type { ProductCollectionRuleOptionsResponse } from '../../client';
import type { CollectionForm } from './product-collection-workspace';

const props = defineProps<{
  form: CollectionForm;
  ruleOptions: ProductCollectionRuleOptionsResponse;
  canManagePlatform: boolean;
}>();

const series = computed(() => {
  const brandIds = new Set(props.form.rule_config.brand_ids || []);
  return brandIds.size
    ? (props.ruleOptions.series || []).filter(row => row.parent_id && brandIds.has(row.parent_id))
    : props.ruleOptions.series || [];
});

const updateColors = (event: Event) => {
  props.form.rule_config.colors = (event.target as HTMLInputElement).value
    .split(',')
    .map(value => value.trim())
    .filter(Boolean);
};
</script>

<template>
  <section class="editor-card" data-testid="collection-rules">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 class="font-bold">Как формируется подборка</h2>
        <p class="mt-1 text-xs text-slate-500">Ручные товары и правила сохраняются вместе с остальными настройками.</p>
      </div>
      <label v-if="form.mode !== 'manual'" class="w-full sm:w-56">
        Сортировка
        <select v-model="form.sort_mode" class="field-input">
          <option value="recommended">Рекомендованная</option>
          <option value="price_asc">Сначала дешевле</option>
          <option value="price_desc">Сначала дороже</option>
          <option value="area_asc">Сначала меньшая площадь</option>
          <option value="area_desc">Сначала большая площадь</option>
          <option value="newest">Сначала новые</option>
        </select>
      </label>
    </div>

    <div class="mt-4 grid grid-cols-3 gap-1 rounded-lg bg-slate-100 p-1 dark:bg-slate-800" aria-label="Способ формирования">
      <button
        v-for="choice in [['manual', 'Вручную'], ['automatic', 'По правилам'], ['hybrid', 'Гибрид']] as const"
        :key="choice[0]"
        class="mode-button"
        :class="form.mode === choice[0] ? 'mode-button--active' : ''"
        type="button"
        @click="form.mode = choice[0]"
      >
        {{ choice[1] }}
      </button>
    </div>

    <p v-if="form.mode === 'manual'" class="mt-4 rounded-lg bg-slate-50 p-3 text-sm text-slate-600 dark:bg-slate-800 dark:text-slate-300">
      Состав и порядок задаются списком ниже.
    </p>

    <div v-else class="mt-5 space-y-4">
      <p class="text-sm text-slate-500">Все заполненные условия применяются одновременно.</p>
      <fieldset>
        <legend>Тип товара</legend>
        <div class="mt-2 flex flex-wrap gap-3 text-sm">
          <label
            v-for="kind in [['complete_split_system','Готовая сплит-система'],['indoor_unit','Внутренний блок'],['outdoor_unit','Наружный блок'],['panel','Панель'],['accessory','Аксессуар'],['consumable','Расходник'],['other','Другое']]"
            :key="kind[0]"
            class="flex items-center gap-1"
          >
            <input v-model="form.rule_config.product_kinds" type="checkbox" :value="kind[0]" />{{ kind[1] }}
          </label>
        </div>
      </fieldset>
      <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <label>Цена от<input v-model.number="form.rule_config.min_price" class="field-input" min="0" type="number" /></label>
        <label>Цена до<input v-model.number="form.rule_config.max_price" class="field-input" min="0" type="number" /></label>
        <label>Площадь от, м²<input v-model.number="form.rule_config.min_area_m2" class="field-input" min="0" type="number" /></label>
        <label>Площадь до, м²<input v-model.number="form.rule_config.max_area_m2" class="field-input" min="0" type="number" /></label>
        <label>Шум не выше, дБ<input v-model.number="form.rule_config.max_noise_min_db" class="field-input" min="0" step="0.1" type="number" /></label>
        <label>Обогрев до, °C<input v-model.number="form.rule_config.max_heating_min_c" class="field-input" max="30" min="-60" type="number" /></label>
        <label>Инвертор<select v-model="form.rule_config.is_inverter" class="field-input"><option :value="null">Не важно</option><option :value="true">Да</option><option :value="false">Нет</option></select></label>
        <label>Цвета<input :value="(form.rule_config.colors || []).join(', ')" class="field-input" @input="updateColors" /></label>
      </div>
      <div class="grid gap-4 md:grid-cols-3">
        <label>Бренды<select v-model="form.rule_config.brand_ids" class="field-input min-h-28" multiple><option v-for="row in ruleOptions.brands || []" :key="row.id" :value="row.id">{{ row.label }}</option></select></label>
        <label>Серии<select v-model="form.rule_config.series_ids" class="field-input min-h-28" multiple><option v-for="row in series" :key="row.id" :value="row.id">{{ row.label }}</option></select></label>
        <label>Характеристики<select v-model="form.rule_config.feature_ids" class="field-input min-h-28" multiple><option v-for="row in ruleOptions.features || []" :key="row.id" :value="row.id">{{ row.label }}</option></select></label>
      </div>
      <fieldset>
        <legend>Wi-Fi</legend>
        <div class="mt-2 flex flex-wrap gap-3 text-sm">
          <label><input v-model="form.rule_config.wifi_states" type="checkbox" value="builtin" /> Встроенный</label>
          <label><input v-model="form.rule_config.wifi_states" type="checkbox" value="ready" /> Опциональный</label>
          <label><input v-model="form.rule_config.wifi_states" type="checkbox" value="none" /> Нет</label>
        </div>
      </fieldset>
      <fieldset v-if="canManagePlatform" data-testid="internal-stock-rules">
        <legend>Доступность</legend>
        <div class="mt-2 flex flex-wrap gap-3 text-sm">
          <label><input v-model="form.rule_config.public_stock_states" type="checkbox" value="local_stock" /> Локально</label>
          <label><input v-model="form.rule_config.public_stock_states" type="checkbox" value="supplier_stock" /> У поставщика</label>
          <label><input v-model="form.rule_config.public_stock_states" type="checkbox" value="available_to_order" /> Под заказ</label>
          <label><input v-model="form.rule_config.public_stock_states" type="checkbox" value="out_of_stock" /> Нет в наличии</label>
        </div>
      </fieldset>
    </div>
  </section>
</template>

<style scoped>
.editor-card { border:1px solid rgb(226 232 240); border-radius:12px; background:white; padding:16px; }
.field-input { display:block; width:100%; min-height:38px; margin-top:5px; border:1px solid rgb(203 213 225); border-radius:8px; background:transparent; padding:7px 10px; font-size:14px; }
.mode-button { min-height:38px; min-width:0; border-radius:6px; padding:0 5px; font-size:12px; font-weight:700; color:rgb(71 85 105); overflow-wrap:anywhere; }
.mode-button--active { background:white; color:rgb(30 64 175); box-shadow:0 1px 2px rgb(15 23 42 / .12); }
label, legend { font-size:12px; font-weight:650; color:rgb(71 85 105); }
:global(.dark) .editor-card { background:rgb(15 23 42); border-color:rgb(51 65 85); }
:global(.dark) .field-input { border-color:rgb(71 85 105); }
:global(.dark) .mode-button--active { background:rgb(30 41 59); color:rgb(191 219 254); }
</style>
