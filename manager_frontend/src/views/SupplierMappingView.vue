<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { api } from '../api';
import { getApiErrorMessage } from '../utils/api-errors';

const loading = ref(false);
const error = ref('');
const unmapped = ref<any[]>([]);
const productQuery = ref('');
const productCandidates = ref<any[]>([]);
const selectedProductId = ref<number | null>(null);
const selectedOffer = ref<any | null>(null);

const loadUnmapped = async () => {
  loading.value = true;
  error.value = '';
  try {
    const res = await api.listUnmappedSupplierOffers(1, 100);
    unmapped.value = res.items || [];
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    loading.value = false;
  }
};

const searchProducts = async () => {
  if (!productQuery.value.trim()) return;
  try {
    productCandidates.value = await api.smartSearchProducts(productQuery.value, 20);
  } catch (e) {
    error.value = getApiErrorMessage(e);
  }
};

const startMap = (offer: any) => {
  selectedOffer.value = offer;
  selectedProductId.value = null;
  productCandidates.value = [];
  productQuery.value = offer.title_raw || '';
  void searchProducts();
};

const createMapping = async () => {
  if (!selectedOffer.value || !selectedProductId.value) return;
  try {
    await api.createSupplierMapping({
      product_id: selectedProductId.value,
      supplier_id: selectedOffer.value.supplier_id,
      external_id: selectedOffer.value.external_id,
    });
    selectedOffer.value = null;
    await loadUnmapped();
  } catch (e) {
    error.value = getApiErrorMessage(e);
  }
};

onMounted(loadUnmapped);
</script>

<template>
  <div class="max-w-7xl mx-auto p-6 space-y-4">
    <h1 class="text-2xl font-bold text-slate-900 dark:text-white">Маппинг прайсов</h1>
    <p v-if="error" class="rounded-lg bg-red-50 border border-red-200 text-red-700 px-3 py-2 text-sm">{{ error }}</p>

    <div class="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-xl overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-gray-50 dark:bg-slate-900/40 text-gray-500">
          <tr>
            <th class="p-3 text-left">Supplier</th>
            <th class="p-3 text-left">SKU/ID</th>
            <th class="p-3 text-left">Title</th>
            <th class="p-3 text-left">Qty</th>
            <th class="p-3 text-left">Wholesale</th>
            <th class="p-3 text-right">Action</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="offer in unmapped" :key="`${offer.supplier_id}:${offer.external_id}`" class="border-t border-gray-100 dark:border-slate-700">
            <td class="p-3">{{ offer.supplier_name || offer.supplier_id }}</td>
            <td class="p-3 font-mono">{{ offer.external_id }}</td>
            <td class="p-3">{{ offer.title_raw || '—' }}</td>
            <td class="p-3">{{ offer.qty }}</td>
            <td class="p-3">{{ offer.wholesale_value || '—' }} <span v-if="offer.wholesale_currency">{{ offer.wholesale_currency }}</span></td>
            <td class="p-3 text-right">
              <button class="px-2 py-1 rounded bg-teal-600 text-white" @click="startMap(offer)">Map</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="loading" class="p-4 text-sm text-gray-500">Загрузка...</div>
    </div>

    <div v-if="selectedOffer" class="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-xl p-4 space-y-3">
      <h2 class="font-semibold">Маппинг: {{ selectedOffer.external_id }}</h2>
      <div class="flex gap-2">
        <input v-model="productQuery" class="flex-1 px-3 py-2 rounded border" placeholder="Поиск товара..." @keyup.enter="searchProducts" />
        <button @click="searchProducts" class="px-3 py-2 rounded bg-slate-900 text-white">Найти</button>
      </div>
      <div class="grid md:grid-cols-2 gap-2 max-h-64 overflow-y-auto">
        <label v-for="p in productCandidates" :key="p.id" class="flex items-center gap-2 border rounded px-3 py-2">
          <input v-model.number="selectedProductId" type="radio" :value="p.id" />
          <span>{{ p.title }} ({{ p.price }} BYN)</span>
        </label>
      </div>
      <div class="flex justify-end gap-2">
        <button class="px-3 py-2 rounded border" @click="selectedOffer = null">Отмена</button>
        <button class="px-3 py-2 rounded bg-teal-600 text-white disabled:opacity-50" :disabled="!selectedProductId" @click="createMapping">Сохранить маппинг</button>
      </div>
    </div>
  </div>
</template>
