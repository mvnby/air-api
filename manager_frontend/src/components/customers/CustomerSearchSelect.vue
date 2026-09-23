<script setup lang="ts">
import { ref } from 'vue';
import { useDebounceFn } from '@vueuse/core';
import { api } from '../../api';
import type { ManagerCatalogCustomerItemResponse } from '../../client';

const selectedCustomer = defineModel<ManagerCatalogCustomerItemResponse | null>({ default: null });

const props = withDefaults(defineProps<{
  placeholder?: string;
  resultTestIdPrefix?: string;
  disabled?: boolean;
}>(), {
  placeholder: 'Поиск по телефону, УНП, имени...',
  resultTestIdPrefix: 'select-customer',
  disabled: false,
});

const query = ref('');
const results = ref<ManagerCatalogCustomerItemResponse[]>([]);
const loading = ref(false);
const failed = ref(false);
let requestId = 0;

const customerLabel = (customer: ManagerCatalogCustomerItemResponse) => (
  customer.full_legal_name || customer.name || `Клиент #${customer.id}`
);

const clear = () => {
  selectedCustomer.value = null;
  query.value = '';
  results.value = [];
  failed.value = false;
  loading.value = false;
  requestId += 1;
};

const onInput = () => {
  requestId += 1;
  results.value = [];
  failed.value = false;
  loading.value = false;
  void search(query.value);
};

const search = useDebounceFn(async (value: string) => {
  const normalizedQuery = value.trim();
  const currentRequestId = ++requestId;
  failed.value = false;
  if (normalizedQuery.length < 3) {
    results.value = [];
    loading.value = false;
    return;
  }

  loading.value = true;
  try {
    const response = await api.getManagerCustomers(1, 10, normalizedQuery);
    if (currentRequestId !== requestId || normalizedQuery !== query.value.trim()) return;
    results.value = response.items || [];
  } catch {
    if (currentRequestId !== requestId) return;
    results.value = [];
    failed.value = true;
  } finally {
    if (currentRequestId === requestId) loading.value = false;
  }
}, 400);

const retry = () => void search(query.value);

const select = (customer: ManagerCatalogCustomerItemResponse) => {
  selectedCustomer.value = customer;
  query.value = '';
  results.value = [];
  failed.value = false;
  loading.value = false;
  requestId += 1;
};
</script>

<template>
  <div data-testid="customer-search-select">
    <div v-if="selectedCustomer" class="flex items-center justify-between gap-3 rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-sm text-slate-800 dark:border-brand-700 dark:bg-brand-950/40 dark:text-slate-100">
      <div class="min-w-0">
        <p class="truncate font-medium">{{ customerLabel(selectedCustomer) }}</p>
        <p v-if="selectedCustomer.phone || selectedCustomer.inn" class="truncate text-xs text-slate-500 dark:text-slate-400">
          {{ selectedCustomer.phone || (selectedCustomer.inn ? `УНП ${selectedCustomer.inn}` : '') }}
        </p>
      </div>
      <button type="button" class="shrink-0 text-xs font-semibold text-brand-700 hover:text-brand-900 disabled:opacity-50 dark:text-brand-300 dark:hover:text-brand-200" data-testid="clear-selected-customer" :disabled="props.disabled" @click="clear">
        Очистить
      </button>
    </div>

    <template v-else>
      <div class="relative">
        <span class="material-icons-round absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">search</span>
        <input
          v-model="query"
          data-testid="customer-search"
          type="search"
          class="w-full rounded-lg border border-gray-300 bg-white py-2 pl-10 pr-9 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-brand-900"
          :placeholder="props.placeholder"
          :disabled="props.disabled"
          @input="onInput"
        />
        <span v-if="loading" class="material-icons-round absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-brand-500">refresh</span>
      </div>
      <p v-if="query.trim().length > 0 && query.trim().length < 3" class="mt-2 text-xs text-slate-500 dark:text-slate-400">Введите минимум 3 символа</p>
      <div v-else-if="failed" class="mt-2 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300" role="alert">
        Не удалось найти клиентов.
        <button type="button" class="ml-1 font-semibold underline" @click="retry">Повторить</button>
      </div>
      <p v-else-if="query.trim().length >= 3 && !loading && !results.length" class="mt-2 text-xs text-slate-500 dark:text-slate-400">Клиенты не найдены</p>
      <div v-else-if="results.length" class="mt-2 max-h-52 space-y-1 overflow-y-auto">
        <button
          v-for="result in results"
          :key="result.id"
          type="button"
          :data-testid="`${props.resultTestIdPrefix}-${result.id}`"
          class="block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-left text-sm transition-colors hover:border-brand-300 hover:bg-brand-50 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-800 dark:hover:border-brand-600 dark:hover:bg-slate-700"
          :disabled="props.disabled"
          @click="select(result)"
        >
          <span class="block font-medium text-slate-800 dark:text-slate-100">{{ customerLabel(result) }}</span>
          <span v-if="result.phone || result.inn" class="block text-xs text-slate-500 dark:text-slate-400">{{ result.phone }}<template v-if="result.phone && result.inn"> · </template><template v-if="result.inn">УНП {{ result.inn }}</template></span>
        </button>
      </div>
    </template>
  </div>
</template>
