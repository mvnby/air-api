<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { getApiErrorMessage } from '../utils/api-errors';
import {
  installationDiscountsApi,
  type InstallationDiscountPolicy,
  type InstallationDiscountProduct,
  type InstallationDiscountStatus,
} from '../services/installation-discounts-api';

const policy = ref<InstallationDiscountPolicy | null>(null);
const overrides = ref<InstallationDiscountProduct[]>([]);
const total = ref(0);
const loading = ref(false);
const savingPolicy = ref(false);
const savingProductId = ref<number | null>(null);
const error = ref('');
const toast = ref('');
const search = ref('');
const searchResults = ref<InstallationDiscountProduct[]>([]);
const searching = ref(false);
const draftDiscounts = ref<Record<number, number>>({});

const formatAmount = (value: number | null | undefined) => {
  if (value === null || value === undefined) return 'нет данных';
  return `${new Intl.NumberFormat('ru-BY', { maximumFractionDigits: 2 }).format(value)} BYN`;
};

const configuredDiscountLabel = (amount: number) => (
  amount === 0 ? 'Без скидки (0 BYN)' : `${formatAmount(amount)}`
);

const statusMeta: Record<InstallationDiscountStatus, { label: string; className: string }> = {
  legacy: { label: 'Старая схема', className: 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-200' },
  active: { label: 'Применяется', className: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300' },
  disabled: { label: 'Без скидки', className: 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-200' },
  blocked_low_margin: { label: 'Защита маржи', className: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-200' },
  blocked_missing_cost: { label: 'Нет себестоимости', className: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300' },
};

const setToast = (message: string) => {
  toast.value = message;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 2600);
};

const syncDraft = (item: InstallationDiscountProduct) => {
  draftDiscounts.value[item.product_id] = item.configured_discount;
};

const load = async () => {
  loading.value = true;
  error.value = '';
  try {
    const response = await installationDiscountsApi.list(100, 1);
    policy.value = response.policy;
    overrides.value = response.items;
    total.value = response.total;
    response.items.forEach(syncDraft);
  } catch (cause) {
    error.value = getApiErrorMessage(cause);
  } finally {
    loading.value = false;
  }
};

const savePolicy = async (nextEnabled = policy.value?.is_enabled) => {
  if (!policy.value || nextEnabled === undefined) return;
  if (policy.value.default_discount < 0 || policy.value.minimum_margin < 0) {
    error.value = 'Суммы не могут быть отрицательными';
    return;
  }
  savingPolicy.value = true;
  error.value = '';
  try {
    policy.value = await installationDiscountsApi.updatePolicy({
      is_enabled: nextEnabled,
      default_discount: policy.value.default_discount,
      minimum_margin: policy.value.minimum_margin,
    });
    setToast(nextEnabled ? 'Защита маржи включена' : 'Защита маржи выключена');
    await load();
  } catch (cause) {
    error.value = getApiErrorMessage(cause);
  } finally {
    savingPolicy.value = false;
  }
};

const toggleEnabled = () => {
  if (!policy.value || savingPolicy.value) return;
  void savePolicy(!policy.value.is_enabled);
};

const searchProducts = async () => {
  const query = search.value.trim();
  if (!query) {
    searchResults.value = [];
    return;
  }
  searching.value = true;
  error.value = '';
  try {
    const response = await installationDiscountsApi.searchProducts(query);
    searchResults.value = response.items;
    response.items.forEach(syncDraft);
  } catch (cause) {
    error.value = getApiErrorMessage(cause);
  } finally {
    searching.value = false;
  }
};

const saveOverride = async (product: InstallationDiscountProduct) => {
  const amount = Number(draftDiscounts.value[product.product_id]);
  if (!Number.isInteger(amount) || amount < 0) {
    error.value = 'Скидка должна быть целым числом от 0 BYN';
    return;
  }
  savingProductId.value = product.product_id;
  error.value = '';
  try {
    const updated = await installationDiscountsApi.saveProductOverride(product.product_id, amount);
    const index = overrides.value.findIndex((item) => item.product_id === product.product_id);
    if (index >= 0) {
      overrides.value[index] = updated;
    } else {
      overrides.value = [updated, ...overrides.value];
      total.value += 1;
    }
    searchResults.value = searchResults.value.map((item) => item.product_id === updated.product_id ? updated : item);
    syncDraft(updated);
    setToast(amount === 0 ? 'Для товара сохранено: без скидки' : 'Исключение сохранено');
  } catch (cause) {
    error.value = getApiErrorMessage(cause);
  } finally {
    savingProductId.value = null;
  }
};

const inheritDefault = async (product: InstallationDiscountProduct) => {
  savingProductId.value = product.product_id;
  error.value = '';
  try {
    await installationDiscountsApi.deleteProductOverride(product.product_id);
    overrides.value = overrides.value.filter((item) => item.product_id !== product.product_id);
    await load();
    if (search.value.trim()) await searchProducts();
    setToast('Исключение удалено: товар наследует общую скидку');
  } catch (cause) {
    error.value = getApiErrorMessage(cause);
  } finally {
    savingProductId.value = null;
  }
};

onMounted(load);
</script>

<template>
  <div class="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
    <Transition name="toast">
      <div v-if="toast" class="fixed right-8 top-20 z-50 rounded-lg bg-teal-600 px-4 py-3 text-sm font-medium text-white shadow-xl">
        {{ toast }}
      </div>
    </Transition>

    <header class="mb-6">
      <h1 class="flex items-center gap-3 text-2xl font-bold tracking-tight text-gray-900 dark:text-white">
        <span class="material-icons-round text-teal-600 dark:text-teal-400">sell</span>
        Скидки на монтаж
      </h1>
      <p class="mt-1 text-sm text-gray-500 dark:text-slate-400">
        Скидка применяется к монтажу только если у товара достаточно маржи.
      </p>
    </header>

    <div v-if="error" class="mb-6 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-500/40 dark:bg-red-500/10 dark:text-red-300">
      {{ error }}
    </div>

    <section v-if="policy" class="mb-8 rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-800">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 class="text-base font-semibold text-gray-900 dark:text-white">Общее правило</h2>
          <p class="mt-1 max-w-2xl text-sm text-gray-500 dark:text-slate-400">
            При включении скидка проверяется по фактической закупочной цене и марже товара до скидки на монтаж.
          </p>
        </div>
        <button
          type="button"
          role="switch"
          :aria-checked="policy.is_enabled"
          :disabled="savingPolicy"
          class="inline-flex items-center gap-2 rounded-full px-3 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60"
          :class="policy.is_enabled ? 'bg-teal-600 text-white' : 'bg-gray-100 text-gray-700 dark:bg-slate-700 dark:text-slate-200'"
          @click="toggleEnabled"
        >
          <span class="relative h-5 w-9 rounded-full" :class="policy.is_enabled ? 'bg-teal-400' : 'bg-gray-300 dark:bg-slate-500'">
            <span class="absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform" :class="policy.is_enabled ? 'translate-x-4' : 'translate-x-0.5'" />
          </span>
          {{ policy.is_enabled ? 'Защита маржи включена' : 'Защита маржи выключена' }}
        </button>
      </div>

      <div class="mt-5 grid gap-4 md:grid-cols-3">
        <label class="block">
          <span class="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">Скидка по умолчанию, BYN</span>
          <input v-model.number="policy.default_discount" type="number" min="0" step="1" class="h-10 w-full rounded-lg border border-gray-300 bg-white px-3 text-sm dark:border-slate-600 dark:bg-slate-900 dark:text-white" />
          <span class="mt-1 block text-xs text-gray-500">{{ configuredDiscountLabel(policy.default_discount) }}</span>
        </label>
        <label class="block">
          <span class="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">Минимальная маржа, BYN</span>
          <input v-model.number="policy.minimum_margin" type="number" min="0" step="1" class="h-10 w-full rounded-lg border border-gray-300 bg-white px-3 text-sm dark:border-slate-600 dark:bg-slate-900 dark:text-white" />
          <span class="mt-1 block text-xs text-gray-500">Ниже этого уровня скидка не применяется.</span>
        </label>
        <div class="flex items-end">
          <button type="button" class="h-10 rounded-lg bg-teal-600 px-4 text-sm font-semibold text-white hover:bg-teal-500 disabled:opacity-60" :disabled="savingPolicy" @click="savePolicy()">
            {{ savingPolicy ? 'Сохраняем…' : 'Сохранить правило' }}
          </button>
        </div>
      </div>
    </section>

    <section class="mb-8 rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-800">
      <div class="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 class="text-base font-semibold text-gray-900 dark:text-white">Исключение для товара</h2>
          <p class="mt-1 text-sm text-gray-500 dark:text-slate-400">Найди товар и задай персональную сумму. 0 означает «без скидки».</p>
        </div>
        <form class="flex w-full max-w-xl gap-2" @submit.prevent="searchProducts">
          <input v-model="search" type="search" placeholder="Название или slug товара" class="h-10 min-w-0 flex-1 rounded-lg border border-gray-300 bg-white px-3 text-sm dark:border-slate-600 dark:bg-slate-900 dark:text-white" />
          <button type="submit" class="h-10 rounded-lg border border-teal-300 px-3 text-sm font-semibold text-teal-700 hover:bg-teal-50 dark:border-teal-500/50 dark:text-teal-300" :disabled="searching">
            {{ searching ? 'Ищем…' : 'Найти' }}
          </button>
        </form>
      </div>

      <div v-if="searchResults.length" class="mt-4 divide-y divide-gray-100 rounded-lg border border-gray-200 dark:divide-slate-700 dark:border-slate-700">
        <article v-for="product in searchResults" :key="product.product_id" class="flex flex-wrap items-center gap-3 p-3">
          <img v-if="product.main_image" :src="product.main_image" :alt="product.title" class="h-10 w-10 rounded-md object-cover" />
          <div class="min-w-48 flex-1">
            <div class="text-sm font-semibold text-gray-900 dark:text-white">{{ product.title }}</div>
            <div class="text-xs text-gray-500 dark:text-slate-400">{{ product.slug }} · {{ formatAmount(product.retail_price) }}</div>
          </div>
          <input v-model.number="draftDiscounts[product.product_id]" type="number" min="0" step="1" class="h-9 w-28 rounded-lg border border-gray-300 bg-white px-2 text-sm dark:border-slate-600 dark:bg-slate-900 dark:text-white" :aria-label="`Скидка для ${product.title}`" />
          <button type="button" class="h-9 rounded-lg bg-teal-600 px-3 text-sm font-semibold text-white hover:bg-teal-500 disabled:opacity-60" :disabled="savingProductId === product.product_id" @click="saveOverride(product)">
            {{ product.has_override ? 'Сохранить' : 'Добавить' }}
          </button>
          <button
            v-if="product.has_override"
            type="button"
            class="h-9 rounded-lg border border-gray-300 px-3 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-60 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-700"
            :disabled="savingProductId === product.product_id"
            @click="inheritDefault(product)"
          >
            Наследовать общую
          </button>
        </article>
      </div>
    </section>

    <section class="rounded-xl border border-gray-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-800">
      <div class="flex items-center justify-between border-b border-gray-200 px-5 py-4 dark:border-slate-700">
        <div>
          <h2 class="text-base font-semibold text-gray-900 dark:text-white">Персональные исключения</h2>
          <p class="mt-0.5 text-sm text-gray-500 dark:text-slate-400">{{ total }} {{ total === 1 ? 'товар' : 'товаров' }} с отдельной настройкой.</p>
        </div>
      </div>

      <div v-if="loading" class="flex justify-center py-16"><div class="h-8 w-8 animate-spin rounded-full border-4 border-gray-200 border-t-teal-500" /></div>
      <div v-else-if="!overrides.length" class="p-10 text-center text-sm text-gray-500 dark:text-slate-400">Пока все товары наследуют общую скидку.</div>
      <div v-else class="divide-y divide-gray-100 dark:divide-slate-700">
        <article v-for="product in overrides" :key="product.product_id" class="p-5">
          <div class="flex flex-wrap items-start gap-3">
            <img v-if="product.main_image" :src="product.main_image" :alt="product.title" class="h-12 w-12 rounded-lg object-cover" />
            <div class="min-w-52 flex-1">
              <div class="text-sm font-semibold text-gray-900 dark:text-white">{{ product.title }}</div>
              <div class="mt-0.5 text-xs text-gray-500 dark:text-slate-400">{{ product.slug }}</div>
            </div>
            <span class="rounded-full px-2 py-1 text-xs font-semibold" :class="statusMeta[product.status].className">{{ statusMeta[product.status].label }}</span>
          </div>

          <div class="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-5">
            <div><div class="text-xs text-gray-500">Розничная цена</div><div class="font-medium text-gray-900 dark:text-white">{{ formatAmount(product.retail_price) }}</div></div>
            <div><div class="text-xs text-gray-500">Себестоимость</div><div class="font-medium text-gray-900 dark:text-white">{{ formatAmount(product.purchase_cost) }}</div></div>
            <div><div class="text-xs text-gray-500">Маржа товара</div><div class="font-medium text-gray-900 dark:text-white">{{ formatAmount(product.margin) }}</div></div>
            <div><div class="text-xs text-gray-500">Задано</div><div class="font-medium text-gray-900 dark:text-white">{{ configuredDiscountLabel(product.configured_discount) }}</div></div>
            <div><div class="text-xs text-gray-500">Применится</div><div class="font-medium text-teal-700 dark:text-teal-300">{{ configuredDiscountLabel(product.applied_discount) }}</div></div>
          </div>

          <p class="mt-3 text-xs text-gray-500 dark:text-slate-400">{{ product.status_note }}</p>
          <div class="mt-4 flex flex-wrap items-center gap-2">
            <input v-model.number="draftDiscounts[product.product_id]" type="number" min="0" step="1" class="h-9 w-28 rounded-lg border border-gray-300 bg-white px-2 text-sm dark:border-slate-600 dark:bg-slate-900 dark:text-white" :aria-label="`Скидка для ${product.title}`" />
            <button type="button" class="h-9 rounded-lg bg-teal-600 px-3 text-sm font-semibold text-white hover:bg-teal-500 disabled:opacity-60" :disabled="savingProductId === product.product_id" @click="saveOverride(product)">Сохранить</button>
            <button type="button" class="h-9 rounded-lg border border-gray-300 px-3 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-60 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-700" :disabled="savingProductId === product.product_id" @click="inheritDefault(product)">Наследовать общую</button>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<style scoped>
.toast-enter-active, .toast-leave-active { transition: opacity .2s ease, transform .2s ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(-0.5rem); }
</style>
