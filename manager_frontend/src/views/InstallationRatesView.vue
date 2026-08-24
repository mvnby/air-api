<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { api } from '../api';
import type { ManagerInstallationRateResponse } from '../client';
import InstallationRateCard from '../components/InstallationRateCard.vue';
import InstallationRateEditModal from '../components/InstallationRateEditModal.vue';
import { getApiErrorMessage } from '../utils/api-errors';

const rates = ref<ManagerInstallationRateResponse[]>([]);
const loading = ref(false);
const error = ref('');
const toast = ref('');
const editingRate = ref<ManagerInstallationRateResponse | null>(null);
const showEditModal = ref(false);

const automaticRates = computed(() => rates.value.filter((rate) => rate.selection_status === 'automatic_fixed'));
const quotedRates = computed(() => rates.value.filter((rate) => (
  rate.selection_status === 'matched_manual_quote' || rate.selection_status === 'legacy_manual_quote'
)));
const unsupportedRates = computed(() => rates.value.filter((rate) => rate.selection_status === 'unsupported'));

const setToast = (message: string) => {
  toast.value = message;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 2500);
};

const loadRates = async () => {
  loading.value = true;
  error.value = '';
  try {
    const response = await api.listManagerInstallationRates();
    rates.value = response.items || [];
  } catch (e) {
    error.value = getApiErrorMessage(e);
    rates.value = [];
  } finally {
    loading.value = false;
  }
};

const openEdit = (rate: ManagerInstallationRateResponse) => {
  editingRate.value = rate;
  showEditModal.value = true;
};

const handleSaved = async () => {
  setToast('Публичный тариф обновлён');
  await loadRates();
};

onMounted(loadRates);
</script>

<template>
  <div class="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
    <Transition name="toast">
      <div
        v-if="toast"
        class="fixed right-8 top-20 z-50 flex items-center gap-3 rounded-lg border border-teal-500 bg-teal-600 px-4 py-3 text-white shadow-xl shadow-teal-900/30"
      >
        <span class="material-icons-round text-xl">check_circle</span>
        <span class="text-sm font-medium">{{ toast }}</span>
      </div>
    </Transition>

    <div class="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 class="flex items-center gap-3 text-2xl font-bold tracking-tight text-gray-900 dark:text-white">
          <span class="material-icons-round text-teal-600 dark:text-teal-400">handyman</span>
          Публичный монтаж
        </h1>
        <p class="mt-1 text-sm text-gray-500 dark:text-slate-400">
          Цены, которые видит покупатель, и правила выбора тарифа при оформлении заказа
        </p>
      </div>
      <a
        href="/manager/tariffs"
        class="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
      >
        <span class="material-icons-round text-base">receipt_long</span>
        Тарифы смет
      </a>
    </div>

    <div class="mb-6 rounded-xl border border-teal-200 bg-teal-50 p-4 dark:border-teal-500/30 dark:bg-teal-500/10">
      <div class="mb-3 text-sm font-semibold text-teal-950 dark:text-teal-100">Как выбирается монтаж</div>
      <div class="grid gap-2 text-sm sm:grid-cols-[1fr_auto_1fr_auto_1fr] sm:items-center">
        <div class="rounded-lg bg-white px-3 py-2 text-gray-800 shadow-sm dark:bg-slate-800 dark:text-slate-100">
          <span class="font-medium">Карточка товара</span>
          <span class="mt-0.5 block text-xs text-gray-500 dark:text-slate-400">Комплектная система и её форм-фактор</span>
        </div>
        <span class="material-icons-round hidden text-teal-500 sm:block">arrow_forward</span>
        <div class="rounded-lg bg-white px-3 py-2 text-gray-800 shadow-sm dark:bg-slate-800 dark:text-slate-100">
          <span class="font-medium">Точное совпадение</span>
          <span class="mt-0.5 block text-xs text-gray-500 dark:text-slate-400">Канальный → канальный, кассетный → кассетный</span>
        </div>
        <span class="material-icons-round hidden text-teal-500 sm:block">arrow_forward</span>
        <div class="rounded-lg bg-white px-3 py-2 text-gray-800 shadow-sm dark:bg-slate-800 dark:text-slate-100">
          <span class="font-medium">Цена или ручной расчёт</span>
          <span class="mt-0.5 block text-xs text-gray-500 dark:text-slate-400">Неизвестные товары не считаются как настенные</span>
        </div>
      </div>
    </div>

    <div
      v-if="error"
      class="mb-6 rounded-xl border border-red-200 bg-red-50 p-4 text-red-600 dark:border-red-500/50 dark:bg-red-500/10 dark:text-red-400"
    >
      {{ error }}
    </div>

    <div v-if="loading" class="flex justify-center py-24">
      <div class="h-9 w-9 animate-spin rounded-full border-4 border-gray-200 border-t-teal-500 dark:border-slate-700"></div>
    </div>

    <template v-else>
      <section v-if="automaticRates.length" class="mb-8">
        <div class="mb-3 flex items-center gap-2">
          <h2 class="text-base font-semibold text-gray-900 dark:text-white">Фиксированный расчёт</h2>
          <span class="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
            {{ automaticRates.length }}
          </span>
        </div>
        <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <InstallationRateCard
            v-for="rate in automaticRates"
            :key="rate.id"
            :rate="rate"
            @edit="openEdit"
          />
        </div>
      </section>

      <section v-if="quotedRates.length" class="mb-8">
        <div class="mb-3 flex items-center gap-2">
          <h2 class="text-base font-semibold text-gray-900 dark:text-white">Цена «от» и ручной расчёт</h2>
          <span class="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-500/15 dark:text-amber-200">
            {{ quotedRates.length }}
          </span>
        </div>
        <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <InstallationRateCard
            v-for="rate in quotedRates"
            :key="rate.id"
            :rate="rate"
            @edit="openEdit"
          />
        </div>
      </section>

      <section v-if="unsupportedRates.length">
        <div class="mb-3 flex items-center gap-2">
          <h2 class="text-base font-semibold text-gray-900 dark:text-white">Не подключено к публичному подбору</h2>
          <span class="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 dark:bg-slate-700 dark:text-slate-300">
            {{ unsupportedRates.length }}
          </span>
        </div>
        <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <InstallationRateCard
            v-for="rate in unsupportedRates"
            :key="rate.id"
            :rate="rate"
          />
        </div>
      </section>

      <div v-if="!rates.length" class="rounded-xl border border-dashed border-gray-300 py-16 text-center text-sm text-gray-500 dark:border-slate-600 dark:text-slate-400">
        Публичные монтажные тарифы не найдены
      </div>
    </template>

    <InstallationRateEditModal
      v-model="showEditModal"
      :rate="editingRate"
      @success="handleSaved"
    />
  </div>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.25s ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(-0.75rem);
}
</style>
