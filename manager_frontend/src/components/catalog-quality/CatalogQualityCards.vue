<script setup lang="ts">
import { computed, ref } from 'vue';
import { ExternalLink, Image as ImageIcon } from 'lucide-vue-next';
import type { ManagerCatalogQualityReportResponse } from '../../api';

type QualityProduct = ManagerCatalogQualityReportResponse['items'][number];
type QualityIssue = NonNullable<QualityProduct['issues']>[number];

const props = defineProps<{
  items: QualityProduct[];
  groups?: ManagerCatalogQualityReportResponse['groups'];
  grouped?: boolean;
}>();
const emit = defineEmits<{ open: [product: QualityProduct]; selectIssue: [code: string] }>();
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
const imageSrc = (url?: string | null) => !url ? '' : url.startsWith('http') || url.startsWith('/') ? url : `/${url}`;
const formatNumber = (value?: number | null) => new Intl.NumberFormat('ru-RU').format(Number(value || 0));
const scoreTone = (score: number) => score >= 85
  ? 'bg-emerald-50 text-emerald-700 ring-emerald-200'
  : score >= 65 ? 'bg-amber-50 text-amber-800 ring-amber-200' : 'bg-red-50 text-red-700 ring-red-200';
const severityTone = (severity: QualityIssue['severity']) => severity === 'critical'
  ? 'bg-red-50 text-red-700'
  : severity === 'warning' ? 'bg-amber-50 text-amber-800' : 'bg-sky-50 text-sky-700';
const priorityBorder = (priority?: string) => priority === 'high'
  ? 'border-l-red-500'
  : priority === 'medium' ? 'border-l-amber-400' : 'border-l-gray-300';
const markImageFailed = (productId: number) => {
  failedImages.value = new Set(failedImages.value).add(productId);
};
</script>

<template>
  <div class="space-y-5 px-4 py-4 sm:px-5">
    <section v-for="group in groupedItems" :key="group.key">
      <header v-if="grouped" class="mb-2 flex flex-wrap items-center justify-between gap-2 border-b border-gray-200 pb-2">
        <div><h2 class="font-bold text-gray-950">{{ group.label }}</h2><p class="text-xs text-gray-500">{{ group.items.length }} на этой странице</p></div>
        <p v-if="groupSummary(group.key)" class="text-xs font-semibold text-gray-500">
          Score {{ groupSummary(group.key)?.average_score }} · критичных {{ groupSummary(group.key)?.critical_products || 0 }}
        </p>
      </header>

      <div class="grid gap-3 xl:grid-cols-2">
        <article v-for="product in group.items" :key="product.product_id" class="grid min-h-36 grid-cols-[96px,minmax(0,1fr)] gap-3 rounded-lg border border-l-4 border-gray-200 bg-white p-3 shadow-sm" :class="priorityBorder(product.work_priority)">
          <button class="relative aspect-[4/3] self-start overflow-hidden rounded-lg bg-gray-100" @click="emit('open', product)">
            <img v-if="product.main_image && !failedImages.has(product.product_id)" :src="imageSrc(product.main_image)" :alt="product.title" class="h-full w-full object-contain" loading="lazy" @error="markImageFailed(product.product_id)">
            <span v-else class="grid h-full place-items-center text-gray-400"><ImageIcon class="h-7 w-7" /></span>
            <span class="absolute left-1.5 top-1.5 rounded-md px-1.5 py-1 text-xs font-bold ring-1" :class="scoreTone(product.score)">{{ product.score }}</span>
          </button>

          <div class="min-w-0">
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0">
                <button class="line-clamp-2 text-left text-sm font-bold leading-5 text-gray-950 hover:text-teal-700" @click="emit('open', product)">{{ product.title }}</button>
                <p class="mt-1 truncate text-xs text-gray-500">{{ product.brand_title || 'Без бренда' }} / {{ product.series_title || 'без серии' }}</p>
              </div>
              <button class="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-gray-200 text-gray-500 hover:border-teal-300 hover:text-teal-700" title="Открыть товар" @click="emit('open', product)"><ExternalLink class="h-4 w-4" /></button>
            </div>

            <div class="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs font-medium text-gray-600">
              <span>{{ product.equipment_type_label || 'Тип не определен' }}</span>
              <span>{{ product.available_qty || 0 }} шт.</span>
              <span>{{ product.image_count || 0 }} фото</span>
              <span>{{ product.supplier_mapping_count || 0 }} поставщ.</span>
              <span :class="product.is_published ? 'text-emerald-700' : 'text-gray-500'">{{ product.is_published ? 'На сайте' : 'Скрыт' }}</span>
            </div>

            <div class="mt-2 flex flex-wrap gap-1">
              <button v-for="issue in (product.issues ?? []).slice(0, 4)" :key="issue.code" class="rounded-md px-1.5 py-1 text-[11px] font-semibold" :class="severityTone(issue.severity)" :title="issue.detail || issue.message" @click="emit('selectIssue', issue.code)">{{ issue.label }}</button>
              <span v-if="product.issue_count > 4" class="rounded-md bg-gray-100 px-1.5 py-1 text-[11px] font-semibold text-gray-500">+{{ formatNumber(product.issue_count - 4) }}</span>
            </div>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>
