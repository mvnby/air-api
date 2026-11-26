<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ArrowLeft, Calculator, ExternalLink, Plus } from 'lucide-vue-next';
import {
  ManagerInstallationMaterialsService as materialsApi,
  type InstallationMaterialCostResult,
  type InstallationMaterialPriceInput,
  type InstallationMaterialPriceItem,
} from '../client';
import { useDemoReadOnly } from '../services/manager-demo';
import { useManagerDocumentTitle } from '../services/manager-document-title';
import { managerSession } from '../services/manager-session';
import { getApiErrorMessage } from '../utils/api-errors';

type Unit = InstallationMaterialPriceInput['unit'];
type SelectedPrice = { price: InstallationMaterialPriceItem; quantity: string };
const units: Record<Unit, string> = { m: 'м', m2: 'м²', piece: 'шт.', set: 'компл.', kg: 'кг', l: 'л', roll: 'рул.' };
const pageSize = 50;
const format = new Intl.NumberFormat('ru-BY', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const quantityFormat = new Intl.NumberFormat('ru-BY', { maximumFractionDigits: 4 });
const money = (value: string | number) => `${format.format(Number(value))} BYN`;
const numberText = (value: string | number) => quantityFormat.format(Number(value));
const unitMoney = (price: InstallationMaterialPriceItem) => numberText(Number(price.pack_price_byn) / Number(price.pack_quantity));
const toDecimal = (value: string | number) => String(value).trim().replace(',', '.');
const minskToday = () => new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Minsk' }).format(new Date());
const demoReadOnly = useDemoReadOnly();
useManagerDocumentTitle(computed(() => 'Себестоимость материалов'));

const entries = ref<InstallationMaterialPriceItem[]>([]);
const searchInput = ref('');
const query = ref('');
const offset = ref(0);
const hasMore = ref(false);
const loading = ref(false);
const loadError = ref('');
const savedMessage = ref('');
const edit = ref<{ data: InstallationMaterialPriceInput; source?: InstallationMaterialPriceItem } | null>(null);
const saving = ref(false);
const saveError = ref('');
const selected = ref<SelectedPrice[]>([]);
const calculating = ref(false);
const result = ref<InstallationMaterialCostResult | null>(null);
const calculationError = ref('');
const selectedIds = computed(() => new Set(selected.value.map(line => line.price.id)));
let listRequest = 0;
let scopeVersion = 0;

const load = async (nextOffset = 0) => {
  const request = ++listRequest;
  loading.value = true;
  loadError.value = '';
  try {
    const page = await materialsApi.listManagerInstallationMaterialPrices(query.value, nextOffset, pageSize);
    if (request !== listRequest) return;
    entries.value = page.items;
    hasMore.value = page.has_more;
    offset.value = nextOffset;
  } catch (error) {
    if (request === listRequest) loadError.value = getApiErrorMessage(error);
  } finally {
    if (request === listRequest) loading.value = false;
  }
};

const search = () => {
  query.value = searchInput.value.trim();
  void load();
};

const openEditor = (entry?: InstallationMaterialPriceItem) => {
  saveError.value = '';
  savedMessage.value = '';
  if (entry) {
    const { id: _id, version: _version, ...data } = entry;
    edit.value = { data: { ...data }, source: entry };
  } else {
    edit.value = {
      data: { title: '', supplier: '', unit: 'm', pack_quantity: '1', pack_price_byn: '', checked_on: minskToday(), source_url: null, note: '' },
    };
  }
};

const save = async () => {
  if (!edit.value || saving.value) return;
  const { data, source } = edit.value;
  const payload = {
    ...data,
    pack_quantity: toDecimal(data.pack_quantity),
    pack_price_byn: toDecimal(data.pack_price_byn),
    source_url: data.source_url?.trim() || null,
  };
  if (!(Number(payload.pack_quantity) > 0) || !(Number(payload.pack_price_byn) > 0)) {
    saveError.value = 'Укажите положительное количество в упаковке и закупочную цену.';
    return;
  }
  const scope = scopeVersion;
  saving.value = true;
  saveError.value = '';
  try {
    const saved = source
      ? await materialsApi.updateManagerInstallationMaterialPrice(source.id, { ...payload, expected_version: source.version })
      : await materialsApi.createManagerInstallationMaterialPrice(payload);
    if (scope !== scopeVersion) return;
    const chosen = selected.value.find(line => line.price.id === saved.id);
    if (chosen) {
      chosen.price = saved;
      result.value = null;
    }
    edit.value = null;
    savedMessage.value = 'Закупочная цена сохранена.';
    await load(offset.value);
  } catch (error) {
    if (scope === scopeVersion) saveError.value = getApiErrorMessage(error);
  } finally {
    if (scope === scopeVersion) saving.value = false;
  }
};

const add = (price: InstallationMaterialPriceItem) => {
  if (!selectedIds.value.has(price.id) && selected.value.length < 100) selected.value.push({ price, quantity: '1' });
};
const remove = (id: number) => { selected.value = selected.value.filter(line => line.price.id !== id); };
watch(selected, () => { result.value = null; calculationError.value = ''; }, { deep: true });

const calculate = async () => {
  if (calculating.value || !selected.value.length) return;
  const items = selected.value.map(line => ({
    price_id: line.price.id, quantity: toDecimal(line.quantity), expected_version: line.price.version,
  }));
  if (items.some(({ quantity }) => !/^\d+(?:\.\d{1,4})?$/.test(quantity) || Number(quantity) <= 0)) {
    calculationError.value = 'Укажите расход больше нуля, до четырёх знаков после запятой.';
    return;
  }
  const scope = scopeVersion;
  calculating.value = true;
  calculationError.value = '';
  result.value = null;
  try {
    const calculated = await materialsApi.calculateManagerInstallationMaterialCost({ items });
    if (scope === scopeVersion) result.value = calculated;
  } catch (error) {
    if (scope === scopeVersion) calculationError.value = getApiErrorMessage(error);
  } finally {
    if (scope === scopeVersion) calculating.value = false;
  }
};

watch(() => managerSession.auth.value?.tenant_id, () => {
  scopeVersion++;
  listRequest++;
  entries.value = [];
  selected.value = [];
  searchInput.value = '';
  query.value = '';
  offset.value = 0;
  hasMore.value = false;
  loading.value = false;
  loadError.value = '';
  edit.value = null;
  savedMessage.value = '';
  saving.value = false;
  calculating.value = false;
  if (managerSession.auth.value?.tenant_id != null) void load();
}, { immediate: true });
</script>

<template>
  <section class="mx-auto w-full max-w-[1450px] p-4 lg:p-6">
    <a href="/manager/tariffs" class="inline-flex items-center gap-1.5 text-sm font-semibold text-brand-700 dark:text-brand-300">
      <ArrowLeft :size="16" aria-hidden="true" /> Тарифы смет
    </a>
    <header class="mb-5 mt-3 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold">Себестоимость материалов</h1>
        <p class="mt-1 text-sm text-slate-500 dark:text-slate-300">Закупочные цены компании и расчёт по фактическому расходу.</p>
      </div>
      <button v-if="!demoReadOnly" type="button" class="btn-mini inline-flex items-center gap-1.5" :disabled="saving || calculating" @click="openEditor()">
        <Plus :size="16" aria-hidden="true" /> Добавить цену
      </button>
    </header>
    <p v-if="savedMessage" role="status" class="mb-3 text-sm text-brand-700 dark:text-brand-300">{{ savedMessage }}</p>

    <form v-if="edit" class="mb-5 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900" @submit.prevent="save">
      <h2 class="mb-3 font-semibold">{{ edit.source ? 'Изменить закупочную цену' : 'Новая закупочная цена' }}</h2>
      <fieldset :disabled="saving" class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label class="text-sm sm:col-span-2">Материал<input v-model="edit.data.title" required maxlength="180" class="field-input mt-1" /></label>
        <label class="text-sm">Поставщик<input v-model="edit.data.supplier" required maxlength="120" class="field-input mt-1" /></label>
        <label class="text-sm">Дата сверки<input v-model="edit.data.checked_on" required type="date" class="field-input mt-1" /></label>
        <label class="text-sm">Единица расхода<select v-model="edit.data.unit" class="field-input mt-1"><option v-for="(label, unit) in units" :key="unit" :value="unit">{{ label }}</option></select></label>
        <label class="text-sm">Количество в упаковке<input v-model="edit.data.pack_quantity" required inputmode="decimal" class="field-input mt-1" /></label>
        <label class="text-sm">Цена упаковки, BYN<input v-model="edit.data.pack_price_byn" required inputmode="decimal" class="field-input mt-1" /></label>
        <label class="text-sm">Ссылка на прайс<input v-model="edit.data.source_url" type="url" class="field-input mt-1" /></label>
        <label class="text-sm sm:col-span-2 lg:col-span-4">Примечание<input v-model="edit.data.note" maxlength="500" class="field-input mt-1" placeholder="Артикул, НДС, минимальная отгрузка" /></label>
      </fieldset>
      <p v-if="saveError" role="alert" class="mt-2 text-sm text-red-700 dark:text-red-300">{{ saveError }}</p>
      <div class="mt-4 flex gap-2">
        <button type="submit" class="btn-mini" :disabled="saving">{{ saving ? 'Сохраняем…' : 'Сохранить' }}</button>
        <button type="button" class="btn-mini-outline" :disabled="saving" @click="edit = null">Отмена</button>
      </div>
    </form>

    <div class="grid items-start gap-5 xl:grid-cols-[minmax(0,3fr)_minmax(20rem,2fr)]">
      <div class="min-w-0 rounded-xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
        <form class="flex items-center gap-2 border-b border-slate-200 p-3 dark:border-slate-700" @submit.prevent="search">
          <input v-model="searchInput" type="search" maxlength="180" aria-label="Материал или поставщик" placeholder="Материал или поставщик" class="field-input min-w-0" />
          <button type="submit" class="btn-mini-outline" :disabled="loading">Найти</button>
        </form>
        <p v-if="loadError" role="alert" class="p-3 text-sm text-red-700 dark:text-red-300">{{ loadError }}</p>
        <p v-else-if="loading && !entries.length" role="status" class="p-4 text-sm">Загружаем цены…</p>
        <p v-else-if="!entries.length" class="p-4 text-sm text-slate-500">{{ query ? 'По этому запросу цен нет.' : 'Добавьте первую закупочную цену.' }}</p>
        <ul v-else class="divide-y divide-slate-200 dark:divide-slate-700">
          <li v-for="entry in entries" :key="entry.id" class="flex flex-wrap items-start justify-between gap-2 p-3">
            <div class="min-w-0 flex-1 break-words">
              <p class="text-sm font-semibold">{{ entry.title }}</p>
              <p class="text-xs text-slate-500 dark:text-slate-300">{{ entry.supplier }} · {{ entry.checked_on.split('-').reverse().join('.') }}</p>
              <p v-if="entry.note" class="mt-1 text-xs text-slate-500 dark:text-slate-300">{{ entry.note }}</p>
              <a v-if="entry.source_url" :href="entry.source_url" target="_blank" rel="noopener noreferrer" class="mt-1 inline-flex items-center gap-1 text-xs font-semibold text-brand-700 dark:text-brand-300">
                Прайс <ExternalLink :size="12" aria-hidden="true" />
              </a>
            </div>
            <div class="shrink-0 text-right">
              <p class="text-sm font-semibold">{{ money(entry.pack_price_byn) }} за {{ numberText(entry.pack_quantity) }} {{ units[entry.unit] }}</p>
              <p v-if="Number(entry.pack_quantity) !== 1" class="text-xs text-slate-500">{{ unitMoney(entry) }} BYN/{{ units[entry.unit] }}</p>
              <div class="mt-1 flex justify-end gap-1.5">
                <button v-if="!demoReadOnly" type="button" class="btn-mini-outline text-xs" :disabled="saving || calculating" @click="openEditor(entry)">Изменить</button>
                <button type="button" class="btn-mini-outline text-xs" :disabled="calculating || selectedIds.has(entry.id) || selected.length >= 100" @click="add(entry)">
                  {{ selectedIds.has(entry.id) ? 'В расчёте' : 'В расчёт' }}
                </button>
              </div>
            </div>
          </li>
        </ul>
        <div v-if="offset || hasMore" class="flex justify-between gap-2 border-t border-slate-200 p-3 dark:border-slate-700">
          <button type="button" class="btn-mini-outline" :disabled="!offset || loading" @click="load(offset - pageSize)">Назад</button>
          <button type="button" class="btn-mini-outline" :disabled="!hasMore || loading" @click="load(offset + pageSize)">Далее</button>
        </div>
      </div>

      <form class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900" @submit.prevent="calculate">
        <h2 class="flex items-center gap-2 text-base font-semibold"><Calculator :size="18" aria-hidden="true" /> Расчёт расхода</h2>
        <p v-if="!selected.length" class="mt-2 text-sm text-slate-500">Добавьте материалы из справочника и укажите, сколько уйдёт на монтаж.</p>
        <fieldset :disabled="calculating" class="mt-2 space-y-3">
          <div v-for="line in selected" :key="line.price.id" class="flex items-end gap-2 border-b border-slate-200 pb-2 dark:border-slate-700">
            <label class="min-w-0 flex-1 text-sm">
              <span class="block break-words">{{ line.price.title }}</span>
              <span class="text-xs text-slate-500">Расход, {{ units[line.price.unit] }}</span>
              <input v-model="line.quantity" required inputmode="decimal" class="field-input mt-1" />
            </label>
            <button type="button" class="btn-mini-outline text-xs" @click="remove(line.price.id)">Убрать</button>
          </div>
        </fieldset>
        <button v-if="selected.length" type="submit" class="btn-mini mt-3" :disabled="calculating || saving">{{ calculating ? 'Считаем…' : 'Рассчитать' }}</button>
        <p v-if="calculationError" role="alert" class="mt-2 text-sm text-red-700 dark:text-red-300">{{ calculationError }}</p>
        <div v-if="result" class="mt-4 rounded-lg bg-slate-50 p-3 dark:bg-slate-800" aria-live="polite">
          <dl class="space-y-1 text-sm">
            <div v-for="line in result.items" :key="line.price_id" class="flex justify-between gap-2">
              <dt class="min-w-0 break-words">{{ line.price.title }} · {{ numberText(line.quantity) }} {{ units[line.price.unit] }}</dt>
              <dd class="shrink-0">{{ money(line.total_byn) }}</dd>
            </div>
          </dl>
          <p class="mt-2 border-t border-slate-200 pt-2 font-semibold dark:border-slate-700">Материалы · {{ money(result.total_byn) }}</p>
        </div>
      </form>
    </div>
  </section>
</template>
