<script setup lang="ts">
import { computed, getCurrentInstance, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { ExternalLink, FileText, LoaderCircle, X } from 'lucide-vue-next';
import { useDialogA11y } from '../../composables/useDialogA11y';
import type { CatalogDecisionItem } from '../../services/catalog-decision-api';
import { productReaderApi, productReaderUrl, type ProductReaderDetail } from '../../services/product-reader-api';
import { managerSession } from '../../services/manager-session';
import { managerStorefrontSelection } from '../../services/manager-storefront-selection';
import { hasManagerCapability, MANAGER_CAPABILITY } from '../../manager-capabilities';
import CatalogMoney from './CatalogMoney.vue';
import ProductReaderGallery from '../products/product-reader/ProductReaderGallery.vue';

const props = defineProps<{
  open: boolean;
  item?: { id: number; title: string } | null;
  selected?: boolean;
  busy?: boolean;
  inProposal?: boolean;
  selectionError?: string;
}>();
const emit = defineEmits<{ close: []; toggle: [item: CatalogDecisionItem]; edit: [id: number] }>();
const instance = getCurrentInstance();
const dialogRef = ref<HTMLElement | null>(null);
const closeButtonRef = ref<HTMLElement | null>(null);
const enlargedCloseRef = ref<HTMLElement | null>(null);
const detail = ref<ProductReaderDetail | null>(null);
const loading = ref(false);
const error = ref('');
const section = ref('overview');
const tabs = [
  { key: 'overview', label: 'Обзор' },
  { key: 'specs', label: 'Все характеристики' },
  { key: 'media', label: 'Фото и документы' },
];
const enlarged = ref<{ url: string; alt?: string | null } | null>(null);
let enlargeTrigger: HTMLElement | null = null;
let requestVersion = 0;
let previousOverflow: string | null = null;
let previousOverflowPriority = '';
const title = computed(() => detail.value?.title || props.item?.title || 'Карточка товара');
const canEdit = computed(() => hasManagerCapability(managerSession.auth.value, MANAGER_CAPABILITY.catalogMasterEdit));
const showSelection = computed(() => hasManagerCapability(managerSession.auth.value, MANAGER_CAPABILITY.crmManage) && !!detail.value?.selection_item);
const eligible = computed(() => !!detail.value?.allowed && detail.value.effective_price != null && detail.value.effective_price > 0);
const selectionDisabled = computed(() => props.busy || props.inProposal || (!props.selected && !eligible.value));
const selectionLabel = computed(() => props.inProposal ? 'В предложении' : props.selected ? 'Убрать из подбора' : 'Добавить в подбор');
const images = computed(() => {
  if (!detail.value) return [];
  const seen = new Set<string>();
  return [{ url: detail.value.main_image, alt: detail.value.title }, ...(detail.value.images ?? [])].flatMap(image => {
    const url = productReaderUrl(image.url);
    if (!url || seen.has(url)) return [];
    seen.add(url);
    return [{ url, alt: image.alt }];
  });
});
const manuals = computed(() => (detail.value?.manuals ?? []).flatMap(manual => {
  const url = productReaderUrl(manual.url);
  return url ? [{ ...manual, url }] : [];
}));
const groups = computed(() => (detail.value?.specification_groups ?? []).filter(group => group.items?.length));
const summary = computed(() => detail.value?.summary_fields ?? []);
const specValue = (item: { value: string; unit?: string | null }) => `${item.value}${item.unit ? ` ${item.unit}` : ''}`;

const closeImage = async () => {
  enlarged.value = null;
  await nextTick();
  if (enlargeTrigger?.isConnected) enlargeTrigger.focus();
  enlargeTrigger = null;
};
const close = () => { if (enlarged.value) void closeImage(); else emit('close'); };
const enlarge = async (image: { url: string; alt?: string | null }) => {
  enlargeTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  enlarged.value = image;
  await nextTick();
  enlargedCloseRef.value?.focus();
};
const toggle = () => {
  if (showSelection.value && !selectionDisabled.value && detail.value?.selection_item) emit('toggle', detail.value.selection_item);
};
const edit = (event: MouseEvent) => {
  if (instance?.vnode.props?.onEdit && detail.value && canEdit.value) {
    event.preventDefault();
    emit('edit', detail.value.id);
  }
};
const load = async () => {
  const version = ++requestVersion;
  detail.value = null;
  error.value = '';
  enlarged.value = null;
  loading.value = false;
  if (!props.open || !props.item || !managerSession.auth.value) return;
  loading.value = true;
  try {
    const result = await productReaderApi.detail(props.item.id);
    if (version === requestVersion) detail.value = result;
  } catch (cause) {
    if (version !== requestVersion) return;
    const status = (cause as { status?: number })?.status;
    error.value = status === 404 ? 'Товар недоступен в текущем каталоге.' : status === 401 || status === 403
      ? 'Нет доступа к этому товару. Проверьте текущую витрину и права доступа.'
      : 'Не удалось загрузить карточку товара. Попробуйте ещё раз.';
  } finally {
    if (version === requestVersion) loading.value = false;
  }
};
watch([
  () => props.open, () => props.item?.id, () => managerSession.auth.value,
  () => managerStorefrontSelection.selectedSlug.value,
], () => { section.value = 'overview'; void load(); }, { immediate: true, flush: 'sync' });

const unlockScroll = () => {
  if (previousOverflow === null) return;
  if (document.body.style.overflow === 'hidden') {
    if (previousOverflow) document.body.style.setProperty('overflow', previousOverflow, previousOverflowPriority);
    else document.body.style.removeProperty('overflow');
  }
  previousOverflow = null;
};
watch(() => props.open, open => {
  if (!open) { unlockScroll(); return; }
  previousOverflow = document.body.style.getPropertyValue('overflow');
  previousOverflowPriority = document.body.style.getPropertyPriority('overflow');
  document.body.style.setProperty('overflow', 'hidden');
}, { immediate: true });
onBeforeUnmount(() => { ++requestVersion; unlockScroll(); });
useDialogA11y({ open: computed(() => props.open), dialogRef, initialFocusRef: closeButtonRef, close });
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-[130] flex items-end justify-center bg-slate-950/60 sm:items-center sm:p-5" @mousedown.self="close">
      <section ref="dialogRef" role="dialog" aria-modal="true" aria-labelledby="catalog-decision-product-details-title" tabindex="-1" class="relative flex max-h-[96dvh] w-full max-w-5xl flex-col overflow-hidden rounded-t-2xl border border-[var(--mv-border)] bg-[var(--mv-surface)] text-[var(--mv-text)] shadow-2xl outline-none sm:max-h-[92dvh] sm:rounded-2xl">
        <div v-show="!enlarged" class="flex min-h-0 flex-1 flex-col">
          <header class="flex shrink-0 items-start justify-between gap-4 border-b border-[var(--mv-border)] px-4 py-4 sm:px-6">
            <div class="min-w-0">
              <p class="mb-1 text-xs font-medium uppercase tracking-wide text-[var(--mv-text-muted)]">Карточка товара</p>
              <h2 id="catalog-decision-product-details-title" class="break-words text-lg font-semibold leading-snug sm:text-xl">{{ title }}</h2>
              <p v-if="detail && (detail.brand_title || detail.series_title)" class="mt-1 text-sm text-[var(--mv-text-muted)]">{{ [detail.brand_title, detail.series_title].filter(Boolean).join(' · ') }}</p>
            </div>
            <button ref="closeButtonRef" type="button" class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg hover:bg-[var(--mv-bg)]" aria-label="Закрыть карточку товара" @click="close"><X aria-hidden="true" class="h-5 w-5" /></button>
          </header>
          <div v-if="loading" role="status" class="flex min-h-64 items-center justify-center gap-3 p-8 text-sm text-[var(--mv-text-muted)]"><LoaderCircle aria-hidden="true" class="h-5 w-5 animate-spin" />Загружаем карточку товара…</div>
          <div v-else-if="error" class="space-y-4 p-6"><p role="alert" class="text-sm text-red-700 dark:text-red-300">{{ error }}</p><button type="button" class="btn-mini-outline" @click="load">Повторить загрузку</button></div>
          <div v-else-if="detail" class="min-h-0 flex-1 overflow-y-auto overscroll-contain">
            <nav class="sticky top-0 z-10 flex gap-1 border-b border-[var(--mv-border)] bg-[var(--mv-surface)] px-3 sm:px-5" aria-label="Разделы карточки товара">
              <button v-for="tab in tabs" :key="tab.key" type="button" class="min-h-12 border-b-2 px-2 py-3 text-sm font-medium sm:px-3" :class="section === tab.key ? 'border-brand-600 text-[var(--kitlane-accent-text)]' : 'border-transparent text-[var(--mv-text-muted)]'" :aria-current="section === tab.key ? 'page' : undefined" @click="section = tab.key">{{ tab.label }}</button>
            </nav>
            <div class="p-4 sm:p-6">
              <div v-if="section === 'overview'" class="grid gap-6 md:grid-cols-2 md:gap-8">
                <ProductReaderGallery :key="detail.id" :images="images" :title="detail.title" @enlarge="enlarge" />
                <div class="min-w-0 space-y-6">
                  <div class="rounded-xl bg-[var(--mv-bg)] p-4">
                    <p class="text-sm text-[var(--mv-text-muted)]">Цена клиенту</p>
                    <p class="mt-1 text-2xl font-semibold"><CatalogMoney :value="detail.effective_price" /></p>
                    <p v-if="detail.selection_item" class="mt-2 text-sm text-[var(--mv-text-muted)]">{{ detail.selection_item.availability === 'in_stock' ? 'В наличии' : 'Под заказ' }}<span v-if="detail.selection_item.supplier_qty != null"> · {{ detail.selection_item.supplier_qty }} шт.</span></p>
                    <p v-if="!detail.allowed" class="mt-2 text-sm text-[var(--mv-text-muted)]">Товар недоступен для подбора в этой витрине.</p>
                    <p v-else-if="detail.effective_price == null" class="mt-2 text-sm text-[var(--mv-text-muted)]">Цена пока не указана.</p>
                  </div>
                  <div><h3 class="mb-3 text-base font-semibold">Основное</h3>
                    <dl v-if="summary.length" class="divide-y divide-[var(--mv-border)] text-sm"><div v-for="field in summary" :key="field.key" class="flex justify-between gap-4 py-2"><dt class="text-[var(--mv-text-muted)]">{{ field.label }}</dt><dd class="min-w-0 break-words text-right font-medium">{{ specValue(field) }}</dd></div></dl>
                    <p v-else class="text-sm text-[var(--mv-text-muted)]">Основные характеристики пока не заполнены.</p>
                    <button v-if="groups.length" type="button" class="mt-3 text-sm font-medium text-[var(--kitlane-accent-text)] underline underline-offset-4" @click="section = 'specs'">Смотреть все характеристики</button>
                  </div>
                  <div><h3 class="mb-2 text-base font-semibold">Описание</h3><p class="whitespace-pre-line break-words text-sm leading-relaxed" :class="!detail.description && 'text-[var(--mv-text-muted)]'">{{ detail.description || 'Описание пока не добавлено.' }}</p></div>
                </div>
              </div>
              <div v-else-if="section === 'specs'" class="space-y-7">
                <section v-for="group in groups" :key="group.key"><h3 class="mb-2 text-base font-semibold">{{ group.label }}</h3>
                  <dl class="divide-y divide-[var(--mv-border)] text-sm"><div v-for="field in group.items" :key="field.key" class="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-4 py-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]"><dt class="break-words text-[var(--mv-text-muted)]">{{ field.label }}</dt><dd class="break-words font-medium">{{ specValue(field) }}</dd></div></dl>
                </section>
                <p v-if="!groups.length" class="py-6 text-sm text-[var(--mv-text-muted)]">Характеристики пока не заполнены.</p>
              </div>
              <div v-else class="grid gap-8 md:grid-cols-2">
                <div><h3 class="mb-4 text-base font-semibold">Фотографии</h3><ProductReaderGallery :images="images" :title="detail.title" @enlarge="enlarge" /></div>
                <div><h3 class="mb-4 text-base font-semibold">Документы</h3><ul v-if="manuals.length" class="space-y-3"><li v-for="(manual, index) in manuals" :key="`${manual.url}-${index}`"><a :href="manual.url" target="_blank" rel="noopener noreferrer" class="flex items-start gap-3 rounded-lg border border-[var(--mv-border)] p-4 text-sm hover:bg-[var(--mv-bg)]"><FileText aria-hidden="true" class="h-5 w-5 shrink-0 text-[var(--kitlane-accent-text)]" /><span class="min-w-0 flex-1 break-words">{{ manual.title || 'Документ' }}</span><ExternalLink aria-hidden="true" class="h-4 w-4 shrink-0" /></a></li></ul><p v-else class="text-sm text-[var(--mv-text-muted)]">Документы пока не добавлены.</p></div>
              </div>
            </div>
          </div>
          <div v-else class="p-6 text-sm text-[var(--mv-text-muted)]">Карточка товара недоступна.</div>
          <footer class="shrink-0 space-y-2 border-t border-[var(--mv-border)] bg-[var(--mv-surface)] px-4 py-3 sm:px-6">
            <p v-if="selectionError" role="alert" class="text-sm text-red-700 dark:text-red-300">{{ selectionError }}</p>
            <p v-if="showSelection && !selected && !eligible" class="text-sm text-[var(--mv-text-muted)]">Добавление в подбор недоступно: проверьте доступность товара и цену.</p>
            <div class="flex flex-wrap items-center justify-end gap-3">
              <a v-if="detail && canEdit" :href="`/manager/products/${detail.id}`" class="mr-auto inline-flex min-h-10 items-center gap-2 text-sm font-medium text-[var(--mv-text-muted)] hover:text-[var(--mv-text)]" @click="edit"><ExternalLink aria-hidden="true" class="h-4 w-4" />Редактировать</a>
              <button v-if="showSelection" type="button" class="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-lg bg-brand-600 px-5 text-sm font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto" :disabled="selectionDisabled" :aria-pressed="!!selected" :aria-busy="!!busy" @click="toggle"><LoaderCircle v-if="busy" aria-hidden="true" class="h-4 w-4 animate-spin" />{{ selectionLabel }}</button>
              <button v-else type="button" class="btn-mini-outline min-h-10" @click="close">Закрыть</button>
            </div>
          </footer>
        </div>
        <div v-if="enlarged" class="flex min-h-[60dvh] flex-col gap-3 p-3 sm:p-5">
          <div class="flex items-center justify-between gap-3"><p class="min-w-0 break-words text-sm">{{ title }}</p><button ref="enlargedCloseRef" type="button" class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg hover:bg-[var(--mv-bg)]" aria-label="Закрыть увеличенное фото" @click="closeImage"><X aria-hidden="true" class="h-5 w-5" /></button></div>
          <img :src="enlarged.url" :alt="enlarged.alt || title" class="min-h-0 max-h-[72dvh] w-full flex-1 rounded-lg bg-white object-contain">
        </div>
      </section>
    </div>
  </Teleport>
</template>
