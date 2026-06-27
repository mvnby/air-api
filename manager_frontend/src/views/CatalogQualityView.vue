<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { watchDebounced } from '@vueuse/core';
import {
  AlertTriangle,
  BadgeDollarSign,
  CheckCircle2,
  CircleAlert,
  Image as ImageIcon,
  Info,
  ListChecks,
  PackageCheck,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Truck,
  X,
} from 'lucide-vue-next';
import { api, type ManagerCatalogQualityReportResponse } from '../api';
import { getApiErrorMessage } from '../utils/api-errors';

type QualityProduct = ManagerCatalogQualityReportResponse['items'][number];
type QualityIssue = NonNullable<QualityProduct['issues']>[number];
type CategoryFilter = 'all' | 'media' | 'identity' | 'specs' | 'commerce' | 'supplier';
type SeverityFilter = 'all' | 'critical' | 'warning' | 'info';

const report = ref<ManagerCatalogQualityReportResponse | null>(null);
const loading = ref(false);
const error = ref('');
const search = ref('');
const activeCategory = ref<CategoryFilter>('all');
const activeSeverity = ref<SeverityFilter>('all');
const selectedIssueCode = ref<string | null>(null);
const onlyProblems = ref(true);
const page = ref(1);
const limit = 50;

const categoryFilters: Array<{ value: CategoryFilter; label: string; icon: unknown }> = [
  { value: 'all', label: 'Все', icon: Sparkles },
  { value: 'media', label: 'Медиа', icon: ImageIcon },
  { value: 'identity', label: 'Бренд и серия', icon: PackageCheck },
  { value: 'specs', label: 'Характеристики', icon: ListChecks },
  { value: 'supplier', label: 'Поставщики', icon: Truck },
  { value: 'commerce', label: 'Цена и наличие', icon: BadgeDollarSign },
];

const severityFilters: Array<{ value: SeverityFilter; label: string; icon: unknown }> = [
  { value: 'all', label: 'Все приоритеты', icon: SlidersHorizontal },
  { value: 'critical', label: 'Критично', icon: CircleAlert },
  { value: 'warning', label: 'Предупреждения', icon: AlertTriangle },
  { value: 'info', label: 'Заметки', icon: Info },
];

const items = computed(() => report.value?.items ?? []);
const meta = computed(() => report.value?.meta);
const totalPages = computed(() => meta.value?.pages ?? 1);
const hasActiveFilters = computed(() => (
  activeCategory.value !== 'all'
  || activeSeverity.value !== 'all'
  || !!selectedIssueCode.value
  || !!search.value.trim()
  || !onlyProblems.value
));

const categoryCounts = computed(() => {
  const map: Record<string, number> = {};
  for (const item of report.value?.categories ?? []) {
    map[item.category] = item.count;
  }
  return map;
});

const severityCounts = computed(() => {
  const counts: Record<SeverityFilter, number> = { all: 0, critical: 0, warning: 0, info: 0 };
  for (const item of report.value?.summary ?? []) {
    counts[item.severity] += item.count;
    counts.all += item.count;
  }
  return counts;
});

const topSummary = computed(() => (report.value?.summary ?? []).slice(0, 10));

const healthTone = computed(() => {
  const score = report.value?.average_score ?? 100;
  if (score >= 85) return 'text-emerald-700 bg-emerald-50 border-emerald-200';
  if (score >= 65) return 'text-amber-700 bg-amber-50 border-amber-200';
  return 'text-red-700 bg-red-50 border-red-200';
});

const loadReport = async () => {
  loading.value = true;
  error.value = '';
  try {
    report.value = await api.getCatalogQualityReport({
      page: page.value,
      limit,
      q: search.value.trim() || null,
      category: activeCategory.value === 'all' ? null : activeCategory.value,
      severity: activeSeverity.value === 'all' ? null : activeSeverity.value,
      issueCode: selectedIssueCode.value,
      onlyProblems: onlyProblems.value,
    });
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    loading.value = false;
  }
};

watchDebounced(search, async () => {
  page.value = 1;
  await loadReport();
}, { debounce: 350 });

watch([activeCategory, activeSeverity, selectedIssueCode, onlyProblems], async () => {
  page.value = 1;
  await loadReport();
});

const refresh = async () => {
  await loadReport();
};

const resetFilters = async () => {
  search.value = '';
  activeCategory.value = 'all';
  activeSeverity.value = 'all';
  selectedIssueCode.value = null;
  onlyProblems.value = true;
  page.value = 1;
  await loadReport();
};

const goToPage = async (nextPage: number) => {
  page.value = Math.min(Math.max(1, nextPage), totalPages.value);
  await loadReport();
};

const selectIssue = (issueCode: string | null) => {
  selectedIssueCode.value = selectedIssueCode.value === issueCode ? null : issueCode;
};

const openProduct = (product: QualityProduct) => {
  const params = new URLSearchParams({
    editProductId: String(product.product_id),
    returnTo: '/manager/catalog-quality',
  });
  if (product.title) {
    params.set('editProductQuery', product.title);
  }
  window.location.href = `/manager/products?${params.toString()}`;
};

const formatNumber = (value: number | null | undefined) => new Intl.NumberFormat('ru-RU').format(Number(value || 0));

const formatCurrency = (value: number | null | undefined) =>
  `${formatNumber(value)} BYN`;

const scoreClass = (score: number) => {
  if (score >= 85) return 'bg-emerald-50 text-emerald-700 ring-emerald-200';
  if (score >= 65) return 'bg-amber-50 text-amber-700 ring-amber-200';
  return 'bg-red-50 text-red-700 ring-red-200';
};

const severityClass = (severity: QualityIssue['severity']) => {
  if (severity === 'critical') return 'bg-red-50 text-red-700 ring-red-200';
  if (severity === 'warning') return 'bg-amber-50 text-amber-700 ring-amber-200';
  return 'bg-sky-50 text-sky-700 ring-sky-200';
};

const cardToneClass = (product: QualityProduct) => {
  const issues = product.issues ?? [];
  if (issues.some((issue) => issue.severity === 'critical')) {
    return 'border-red-200 shadow-[0_16px_40px_rgba(239,68,68,0.08)]';
  }
  if (issues.some((issue) => issue.severity === 'warning')) {
    return 'border-amber-200 shadow-[0_16px_40px_rgba(245,158,11,0.08)]';
  }
  return 'border-emerald-200 shadow-[0_16px_40px_rgba(16,185,129,0.08)]';
};

const categoryIcon = (category: string) => {
  if (category === 'media') return ImageIcon;
  if (category === 'identity') return PackageCheck;
  if (category === 'specs') return ListChecks;
  if (category === 'supplier') return Truck;
  if (category === 'commerce') return BadgeDollarSign;
  return Info;
};

const imageSizeLabel = (product: QualityProduct) => {
  if (!product.main_image_width || !product.main_image_height) return 'размер неизвестен';
  return `${product.main_image_width}x${product.main_image_height}px`;
};

const mediaStatusLabel = (status?: string) => {
  if (status === 'missing') return 'нет фото';
  if (status === 'low_resolution') return 'маленькое фото';
  if (status === 'unknown_dimensions') return 'размер неизвестен';
  if (status === 'ok') return 'медиа ок';
  return 'медиа не проверено';
};

const imageSrc = (url?: string | null) => {
  if (!url) return '';
  if (url.startsWith('http') || url.startsWith('/')) return url;
  return `/${url}`;
};

onMounted(loadReport);
</script>

<template>
  <div class="min-h-screen bg-gray-50 px-4 pb-5 pt-12 text-gray-950 sm:px-6 md:py-5 lg:px-8">
    <div class="mx-auto max-w-7xl space-y-5">
      <header class="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm sm:p-5">
        <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div class="min-w-0">
            <p class="text-xs font-semibold uppercase tracking-[0.22em] text-gray-500">PIM quality</p>
            <h1 class="mt-1 text-2xl font-semibold tracking-normal text-gray-950 sm:text-3xl">
              Качество каталога
            </h1>
            <p class="mt-2 max-w-2xl text-sm leading-6 text-gray-600">
              Контроль карточек перед публикацией: медиа, бренд/серия, нормализованные характеристики, цена и связи с поставщиками.
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <button
              class="inline-flex h-10 items-center gap-2 rounded-xl border border-gray-200 bg-white px-3 text-sm font-semibold text-gray-700 transition hover:border-teal-200 hover:text-teal-700 disabled:opacity-60"
              :disabled="loading"
              @click="refresh"
            >
              <RefreshCw class="h-4 w-4" :class="loading ? 'animate-spin' : ''" />
              Обновить
            </button>
            <button
              v-if="hasActiveFilters"
              class="inline-flex h-10 items-center gap-2 rounded-xl bg-gray-100 px-3 text-sm font-semibold text-gray-700 transition hover:bg-gray-200"
              @click="resetFilters"
            >
              <X class="h-4 w-4" />
              Сбросить
            </button>
          </div>
        </div>
      </header>

      <section class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <article class="rounded-2xl border p-4 shadow-sm" :class="healthTone">
          <div class="flex items-center justify-between gap-3">
            <div>
              <p class="text-sm font-medium opacity-80">Средний score</p>
              <p class="mt-2 text-3xl font-semibold">{{ report?.average_score ?? '...' }}</p>
            </div>
            <ShieldCheck class="h-9 w-9 opacity-80" />
          </div>
        </article>
        <article class="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
          <p class="text-sm font-medium text-gray-500">Товаров в проверке</p>
          <p class="mt-2 text-3xl font-semibold">{{ formatNumber(report?.total_products) }}</p>
        </article>
        <article class="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-amber-800 shadow-sm">
          <p class="text-sm font-medium opacity-80">С проблемами</p>
          <p class="mt-2 text-3xl font-semibold">{{ formatNumber(report?.problem_products) }}</p>
        </article>
        <article class="rounded-2xl border border-red-200 bg-red-50 p-4 text-red-800 shadow-sm">
          <p class="text-sm font-medium opacity-80">Критичных карточек</p>
          <p class="mt-2 text-3xl font-semibold">{{ formatNumber(report?.critical_products) }}</p>
        </article>
      </section>

      <section class="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
        <div class="grid gap-3 xl:grid-cols-[minmax(240px,1fr)_auto] xl:items-center">
          <label class="relative block">
            <Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <input
              v-model="search"
              class="h-11 w-full rounded-xl border border-gray-200 bg-gray-50 pl-10 pr-3 text-sm font-medium outline-none transition focus:border-teal-300 focus:bg-white focus:ring-4 focus:ring-teal-100"
              placeholder="Найти товар, slug или модель"
            >
          </label>
          <label class="inline-flex h-11 items-center justify-between gap-3 rounded-xl border border-gray-200 bg-gray-50 px-3 text-sm font-semibold text-gray-700 sm:justify-start">
            <input v-model="onlyProblems" class="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500" type="checkbox">
            Только карточки с проблемами
          </label>
        </div>

        <div class="mt-4 flex gap-2 overflow-x-auto pb-1">
          <button
            v-for="item in categoryFilters"
            :key="item.value"
            class="inline-flex h-10 shrink-0 items-center gap-2 rounded-full border px-3 text-sm font-semibold transition"
            :class="activeCategory === item.value ? 'border-teal-600 bg-teal-600 text-white shadow-sm' : 'border-gray-200 bg-white text-gray-600 hover:border-teal-200 hover:text-teal-700'"
            @click="activeCategory = item.value"
          >
            <component :is="item.icon" class="h-4 w-4" />
            {{ item.label }}
            <span v-if="item.value !== 'all'" class="rounded-full bg-black/10 px-2 py-0.5 text-xs">
              {{ categoryCounts[item.value] || 0 }}
            </span>
          </button>
        </div>

        <div class="mt-3 flex gap-2 overflow-x-auto pb-1">
          <button
            v-for="item in severityFilters"
            :key="item.value"
            class="inline-flex h-9 shrink-0 items-center gap-2 rounded-full border px-3 text-xs font-semibold transition"
            :class="activeSeverity === item.value ? 'border-gray-900 bg-gray-900 text-white' : 'border-gray-200 bg-gray-50 text-gray-600 hover:border-gray-300 hover:text-gray-900'"
            @click="activeSeverity = item.value"
          >
            <component :is="item.icon" class="h-3.5 w-3.5" />
            {{ item.label }}
            <span class="rounded-full bg-black/10 px-1.5 py-0.5">{{ severityCounts[item.value] || 0 }}</span>
          </button>
        </div>
      </section>

      <div v-if="error" class="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700">
        {{ error }}
      </div>

      <div class="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <section class="space-y-3">
          <div class="flex items-center justify-between gap-3">
            <p class="text-sm font-semibold text-gray-500">
              Найдено: {{ formatNumber(meta?.total) }}
            </p>
            <p class="text-xs font-medium text-gray-400">
              Стр. {{ meta?.page || 1 }} из {{ totalPages }}
            </p>
          </div>

          <div v-if="loading && !report" class="grid gap-3">
            <div v-for="index in 4" :key="index" class="h-32 animate-pulse rounded-2xl bg-white shadow-sm" />
          </div>

          <div v-else-if="!items.length" class="rounded-2xl border border-emerald-200 bg-emerald-50 p-8 text-center text-emerald-800">
            <CheckCircle2 class="mx-auto h-10 w-10" />
            <h2 class="mt-3 text-xl font-semibold">Здесь чисто</h2>
            <p class="mt-2 text-sm opacity-80">По текущим фильтрам проблемных карточек не найдено.</p>
          </div>

          <template v-else>
            <article
              v-for="product in items"
              :key="product.product_id"
              class="overflow-hidden rounded-2xl border bg-white shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
              :class="cardToneClass(product)"
            >
              <div class="grid gap-4 p-4 sm:grid-cols-[132px,minmax(0,1fr)]">
                <button
                  class="group relative aspect-[4/3] overflow-hidden rounded-xl bg-gray-100 text-left"
                  @click="openProduct(product)"
                >
                  <img
                    v-if="product.main_image"
                    :src="imageSrc(product.main_image)"
                    :alt="product.title"
                    class="h-full w-full object-contain transition group-hover:scale-105"
                    loading="lazy"
                  >
                  <div v-else class="flex h-full w-full items-center justify-center bg-gray-100 text-gray-400">
                    <ImageIcon class="h-9 w-9" />
                  </div>
                  <span
                    class="absolute left-2 top-2 rounded-full px-2 py-1 text-xs font-bold ring-1"
                    :class="scoreClass(product.score)"
                  >
                    {{ product.score }}
                  </span>
                </button>

                <div class="min-w-0">
                  <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div class="min-w-0">
                      <button class="block text-left text-lg font-semibold leading-snug text-gray-950 hover:text-teal-700" @click="openProduct(product)">
                        {{ product.title }}
                      </button>
                      <p class="mt-1 truncate text-sm font-medium text-gray-500">
                        {{ product.brand_title || 'Без бренда' }}
                        <span class="text-gray-300">/</span>
                        {{ product.series_title || 'без серии' }}
                      </p>
                    </div>
                    <button
                      class="inline-flex h-10 shrink-0 items-center justify-center rounded-xl bg-teal-600 px-3 text-sm font-semibold text-white shadow-sm transition hover:bg-teal-700"
                      @click="openProduct(product)"
                    >
                      Открыть товар
                    </button>
                  </div>

                  <div class="mt-4 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
                    <p class="rounded-xl bg-gray-50 px-3 py-2">
                      <span class="block text-xs font-semibold uppercase text-gray-400">Цена</span>
                      <span class="font-semibold">{{ formatCurrency(product.price) }}</span>
                    </p>
                    <p class="rounded-xl bg-gray-50 px-3 py-2">
                      <span class="block text-xs font-semibold uppercase text-gray-400">Фото</span>
                      <span class="font-semibold">{{ product.image_count || 0 }} шт. · {{ mediaStatusLabel(product.media_status) }}</span>
                    </p>
                    <p class="rounded-xl bg-gray-50 px-3 py-2">
                      <span class="block text-xs font-semibold uppercase text-gray-400">Главное</span>
                      <span class="font-semibold">{{ imageSizeLabel(product) }}</span>
                    </p>
                    <p class="rounded-xl bg-gray-50 px-3 py-2">
                      <span class="block text-xs font-semibold uppercase text-gray-400">Поставщики</span>
                      <span class="font-semibold">{{ product.supplier_mapping_count || 0 }} связей · {{ product.available_qty || 0 }} шт.</span>
                    </p>
                  </div>

                  <div class="mt-4 flex flex-wrap gap-2">
                    <button
                      v-for="issue in product.issues || []"
                      :key="`${product.product_id}-${issue.code}`"
                      class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 transition hover:brightness-95"
                      :class="severityClass(issue.severity)"
                      :title="issue.detail || issue.message"
                      @click="selectIssue(issue.code)"
                    >
                      <component :is="categoryIcon(issue.category)" class="h-3.5 w-3.5" />
                      {{ issue.label }}
                    </button>
                  </div>
                </div>
              </div>
            </article>
          </template>

          <div v-if="report && totalPages > 1" class="flex items-center justify-between rounded-2xl border border-gray-200 bg-white p-3 shadow-sm">
            <button
              class="rounded-xl border border-gray-200 px-3 py-2 text-sm font-semibold text-gray-700 disabled:opacity-40"
              :disabled="page <= 1 || loading"
              @click="goToPage(page - 1)"
            >
              Назад
            </button>
            <span class="text-sm font-semibold text-gray-500">{{ page }} / {{ totalPages }}</span>
            <button
              class="rounded-xl border border-gray-200 px-3 py-2 text-sm font-semibold text-gray-700 disabled:opacity-40"
              :disabled="page >= totalPages || loading"
              @click="goToPage(page + 1)"
            >
              Дальше
            </button>
          </div>
        </section>

        <aside class="space-y-4">
          <section class="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm xl:sticky xl:top-4">
            <div class="flex items-center justify-between gap-3">
              <h2 class="text-base font-semibold text-gray-950">Частые причины</h2>
              <span class="rounded-full bg-gray-100 px-2 py-1 text-xs font-bold text-gray-500">
                {{ formatNumber(report?.summary?.length) }}
              </span>
            </div>

            <div class="mt-3 space-y-2">
              <button
                v-for="item in topSummary"
                :key="item.code"
                class="flex w-full items-center justify-between gap-3 rounded-xl border px-3 py-2 text-left transition hover:border-teal-200 hover:bg-teal-50/60"
                :class="selectedIssueCode === item.code ? 'border-teal-300 bg-teal-50' : 'border-gray-100 bg-gray-50'"
                @click="selectIssue(item.code)"
              >
                <span class="flex min-w-0 items-center gap-2">
                  <component :is="categoryIcon(item.category)" class="h-4 w-4 shrink-0 text-gray-500" />
                  <span class="truncate text-sm font-semibold text-gray-800">{{ item.label }}</span>
                </span>
                <span
                  class="shrink-0 rounded-full px-2 py-1 text-xs font-bold ring-1"
                  :class="severityClass(item.severity)"
                >
                  {{ item.count }}
                </span>
              </button>

              <p v-if="!topSummary.length" class="rounded-xl bg-emerald-50 px-3 py-3 text-sm font-semibold text-emerald-700">
                Массовых проблем не найдено.
              </p>
            </div>
          </section>

          <section class="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
            <h2 class="text-base font-semibold text-gray-950">Категории</h2>
            <div class="mt-3 space-y-2">
              <div
                v-for="item in report?.categories || []"
                :key="item.category"
                class="rounded-xl border border-gray-100 bg-gray-50 p-3"
              >
                <div class="flex items-center justify-between gap-3">
                  <span class="flex items-center gap-2 text-sm font-semibold text-gray-800">
                    <component :is="categoryIcon(item.category)" class="h-4 w-4 text-teal-700" />
                    {{ item.label }}
                  </span>
                  <span class="text-sm font-bold text-gray-950">{{ item.count }}</span>
                </div>
                <div class="mt-2 flex gap-1.5 text-xs font-semibold">
                  <span class="rounded-full bg-red-50 px-2 py-0.5 text-red-700">{{ item.critical || 0 }}</span>
                  <span class="rounded-full bg-amber-50 px-2 py-0.5 text-amber-700">{{ item.warning || 0 }}</span>
                  <span class="rounded-full bg-sky-50 px-2 py-0.5 text-sky-700">{{ item.info || 0 }}</span>
                </div>
              </div>
            </div>
          </section>
        </aside>
      </div>
    </div>
  </div>
</template>
