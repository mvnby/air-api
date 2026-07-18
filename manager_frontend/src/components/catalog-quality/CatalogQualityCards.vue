<script setup lang="ts">
import { computed, ref } from 'vue';
import { ExternalLink, Image as ImageIcon, Images, Wrench } from 'lucide-vue-next';
import type { ManagerCatalogQualityReportResponse } from '../../api';
import { countLabel } from './catalog-quality-copy';

type QualityProduct = ManagerCatalogQualityReportResponse['items'][number];
type QualityIssue = NonNullable<QualityProduct['issues']>[number];

const props = defineProps<{
  items: QualityProduct[];
  groups?: ManagerCatalogQualityReportResponse['groups'];
  grouped?: boolean;
  selectedBrandTitle?: string;
  hideEquipmentType?: boolean;
  hideSeries?: boolean;
}>();
const emit = defineEmits<{
  open: [product: QualityProduct];
  openMedia: [product: QualityProduct];
  openSeriesMedia: [product: QualityProduct];
}>();
const failedImages = ref(new Set<number>());

const groupedItems = computed(() => {
  const buckets = new Map<string, { key: string; label: string; items: QualityProduct[] }>();
  for (const product of props.items) {
    const key = props.grouped ? product.group_key || 'other' : 'all';
    const label = props.grouped ? product.group_label || 'Без группы' : '';
    const bucket = buckets.get(key) ?? { key, label, items: [] };
    bucket.items.push(product);
    buckets.set(key, bucket);
  }
  return [...buckets.values()];
});

const groupSummary = (key: string) => props.groups?.find((group) => group.key === key);
const seriesMediaProduct = (group: { key: string; items: QualityProduct[] }) =>
  group.key.startsWith('series:') ? group.items.find((product) => product.series_id) : undefined;
const imageSrc = (url?: string | null) => !url ? '' : url.startsWith('http') || url.startsWith('/') ? url : `/${url}`;
const publicSiteBaseUrl = (() => {
  const configured = String(import.meta.env.WEBSITE_URL || '').trim();
  if (configured) return configured.replace(/\/+$/, '');
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    return `${window.location.protocol}//${window.location.hostname}:4321`;
  }
  return `${window.location.protocol}//${window.location.host}`;
})();
const publicProductUrl = (slug: string) => `${publicSiteBaseUrl}/product/${slug}/`;
const formatNumber = (value?: number | null) => new Intl.NumberFormat('ru-RU').format(Number(value || 0));
const scoreTone = (score: number) => score >= 85
  ? 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-950 dark:text-emerald-200 dark:ring-emerald-800'
  : score >= 65
    ? 'bg-amber-50 text-amber-800 ring-amber-200 dark:bg-amber-950 dark:text-amber-200 dark:ring-amber-800'
    : 'bg-red-50 text-red-700 ring-red-200 dark:bg-red-950 dark:text-red-200 dark:ring-red-800';
const severityTone = (severity: QualityIssue['severity']) => severity === 'critical'
  ? 'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-200'
  : severity === 'warning'
    ? 'bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-200'
    : 'bg-sky-50 text-sky-700 dark:bg-sky-950 dark:text-sky-200';
const priorityBorder = (priority?: string) => priority === 'high'
  ? 'border-l-red-500'
  : priority === 'medium' ? 'border-l-amber-400' : 'border-l-gray-300';
const priorityTone = (priority?: string) => priority === 'high'
  ? 'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-200'
  : priority === 'medium'
    ? 'bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-200'
    : 'bg-gray-100 text-gray-600 dark:bg-slate-800 dark:text-slate-300';
const priorityLabel = (priority?: string) => priority === 'high' ? 'Высокий приоритет' : priority === 'medium' ? 'Средний приоритет' : 'Низкий приоритет';
const hasIssueCategory = (product: QualityProduct, category: string) => (product.issues ?? []).some((issue) => issue.category === category);
const displayTitle = (product: QualityProduct) => {
  const brand = props.selectedBrandTitle?.trim();
  if (!brand) return product.title;
  const title = product.title.trim();
  return title.toLocaleLowerCase('ru').startsWith(`${brand.toLocaleLowerCase('ru')} `)
    ? title.slice(brand.length).trim()
    : title;
};
const identityParts = (product: QualityProduct) => [
  props.selectedBrandTitle ? '' : product.brand_title || 'Без бренда',
  props.hideSeries ? '' : product.series_title || 'без серии',
].filter(Boolean);
const imageSizeLabel = (product: QualityProduct) => product.main_image_width && product.main_image_height
  ? `${product.main_image_width} × ${product.main_image_height} px`
  : '';
const markImageFailed = (productId: number) => {
  failedImages.value = new Set(failedImages.value).add(productId);
};
const openGroupMedia = (group: { key: string; items: QualityProduct[] }) => {
  const product = seriesMediaProduct(group);
  if (product) emit('openSeriesMedia', product);
};
const visibleIssues = (product: QualityProduct) => (product.issues ?? []).filter((issue) => !(
  issue.code === 'out_of_stock'
  && product.work_priority === 'low'
  && Number(product.available_qty || 0) === 0
));
</script>

<template>
  <div class="space-y-5 px-4 py-4 sm:px-5">
    <section v-for="group in groupedItems" :key="group.key">
      <header v-if="grouped" class="mb-2 flex flex-wrap items-center justify-between gap-2 border-b border-gray-200 pb-2 dark:border-slate-700">
        <div>
          <h2 class="font-bold text-gray-950 dark:text-slate-100">{{ group.label }}</h2>
          <p class="text-xs text-gray-500 dark:text-slate-400">{{ countLabel(groupSummary(group.key)?.count ?? group.items.length, 'товар', 'товара', 'товаров') }} · score {{ groupSummary(group.key)?.average_score ?? '—' }} · критичных {{ groupSummary(group.key)?.critical_products || 0 }}</p>
        </div>
        <div v-if="groupSummary(group.key)?.media_problem_products" class="flex flex-wrap items-center gap-2">
          <span class="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-800 dark:bg-amber-950 dark:text-amber-200"><Images class="h-3.5 w-3.5" /> Медиа: {{ groupSummary(group.key)?.media_problem_products }}</span>
          <button v-if="seriesMediaProduct(group)" class="inline-flex h-8 items-center gap-1.5 rounded-lg bg-teal-600 px-2.5 text-xs font-semibold text-white hover:bg-teal-700" @click="openGroupMedia(group)"><Images class="h-3.5 w-3.5" />Исправить медиа серии</button>
        </div>
      </header>

      <div class="grid gap-3 xl:grid-cols-2">
        <article v-for="product in group.items" :key="product.product_id" class="grid min-h-36 grid-cols-[92px,minmax(0,1fr)] gap-3 rounded-lg border border-l-4 border-gray-200 bg-white p-3 shadow-sm dark:border-slate-700 dark:bg-slate-900" :class="priorityBorder(product.work_priority)">
          <button class="relative aspect-[4/3] self-start overflow-hidden rounded-lg bg-gray-100 dark:bg-slate-800" @click="emit('open', product)">
            <img v-if="product.main_image && !failedImages.has(product.product_id)" :src="imageSrc(product.main_image)" :alt="product.title" class="h-full w-full object-contain" loading="lazy" @error="markImageFailed(product.product_id)">
            <span v-else class="grid h-full place-items-center text-gray-400"><ImageIcon class="h-7 w-7" /></span>
            <span class="absolute left-1.5 top-1.5 rounded-md px-1.5 py-1 text-xs font-bold ring-1" :class="scoreTone(product.score)">{{ product.score }} / 100</span>
          </button>

          <div class="min-w-0">
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0">
                <button class="line-clamp-2 text-left text-sm font-bold leading-5 text-gray-950 hover:text-teal-700 dark:text-slate-100 dark:hover:text-teal-300" @click="emit('open', product)">{{ displayTitle(product) }}</button>
                <p v-if="identityParts(product).length" class="mt-0.5 truncate text-xs font-semibold uppercase text-gray-500 dark:text-slate-400">{{ identityParts(product).join(' / ') }}</p>
              </div>
              <span class="shrink-0 rounded-full px-2 py-1 text-[10px] font-bold uppercase" :class="priorityTone(product.work_priority)">{{ priorityLabel(product.work_priority) }}</span>
            </div>

            <p class="mt-1.5 text-xs text-gray-500 dark:text-slate-400" :title="product.priority_reason">{{ product.priority_reason }}</p>

            <div class="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs font-medium text-gray-600 dark:text-slate-300">
              <span v-if="!hideEquipmentType">{{ product.equipment_type_label || 'Тип не определен' }}</span>
              <span>{{ product.available_qty || 0 }} шт.</span>
              <span>{{ countLabel(product.supplier_mapping_count || 0, 'поставщик', 'поставщика', 'поставщиков') }}</span>
              <span :class="product.is_published ? 'text-emerald-700' : 'text-gray-500'">{{ product.is_published ? 'На сайте' : 'Скрыт' }}</span>
              <span>{{ product.image_count || 0 }} фото<span v-if="imageSizeLabel(product)"> · {{ imageSizeLabel(product) }}</span></span>
            </div>

            <div class="mt-2 flex flex-wrap gap-1">
              <span v-for="issue in visibleIssues(product).slice(0, 3)" :key="issue.code" class="rounded-md px-1.5 py-1 text-[11px] font-semibold" :class="severityTone(issue.severity)" :title="issue.detail || issue.message">{{ issue.label }}</span>
              <span v-if="visibleIssues(product).length > 3" class="rounded-md bg-gray-100 px-1.5 py-1 text-[11px] font-semibold text-gray-500 dark:bg-slate-800 dark:text-slate-300">Ещё {{ formatNumber(visibleIssues(product).length - 3) }}</span>
            </div>

            <div class="mt-2 flex flex-wrap gap-2 border-t border-gray-100 pt-2 dark:border-slate-700">
              <button v-if="hasIssueCategory(product, 'media')" class="inline-flex h-8 items-center gap-1.5 rounded-lg bg-teal-50 px-2.5 text-xs font-semibold text-teal-800 hover:bg-teal-100 dark:bg-teal-950 dark:text-teal-200 dark:hover:bg-teal-900" @click="emit('openMedia', product)"><Images class="h-3.5 w-3.5" />Исправить медиа</button>
              <button class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-gray-200 px-2.5 text-xs font-semibold text-gray-700 hover:border-teal-300 hover:text-teal-800 dark:border-slate-600 dark:text-slate-200 dark:hover:border-teal-600 dark:hover:text-teal-200" @click="emit('open', product)"><Wrench class="h-3.5 w-3.5" />Открыть карточку</button>
              <a v-if="product.slug" class="grid h-8 w-8 place-items-center rounded-lg border border-gray-200 text-gray-500 hover:border-teal-300 hover:text-teal-700 dark:border-slate-600 dark:text-slate-300 dark:hover:border-teal-600 dark:hover:text-teal-200" :href="publicProductUrl(product.slug)" target="_blank" rel="noopener noreferrer" title="Открыть на сайте"><ExternalLink class="h-3.5 w-3.5" /></a>
            </div>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>
