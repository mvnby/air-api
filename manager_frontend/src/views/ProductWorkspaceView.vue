<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ChevronLeft,
  CircleAlert,
  ClipboardCopy,
  ExternalLink,
  FileText,
  Images,
  Link2,
  MoreHorizontal,
  Package,
  Save,
  Settings2,
  Sparkles,
  Store,
  Trash2,
  Wrench,
} from 'lucide-vue-next';
import { api, type ManagerCatalogQualityReportResponse, type Product } from '../api';
import type { WebRebuildStatusResponse } from '../client/models/WebRebuildStatusResponse';
import ProductEditModal from '../components/ProductEditModal.vue';
import ProductWorkspaceMedia from '../components/products/ProductWorkspaceMedia.vue';
import ProductWorkspaceFeatures from '../components/products/ProductWorkspaceFeatures.vue';
import { getApiErrorMessage } from '../utils/api-errors';
import { confirmDialog } from '../services/ui-feedback';
import {
  buildProductWorkspacePath,
  getProductWorkspaceNeighbors,
  loadProductWorkspaceContext,
  parseProductWorkspaceLocation,
  getProductImageCount,
  type ProductWorkspaceSection,
} from '../utils/product-workspace';

type QualityProduct = ManagerCatalogQualityReportResponse['items'][number];

type ProductEditorExpose = {
  save: () => Promise<boolean>;
};

const editor = ref<ProductEditorExpose | null>(null);
const product = ref<Product | null>(null);
const loading = ref(true);
const saving = ref(false);
const deleting = ref(false);
const dirty = ref(false);
const errorMessage = ref('');
const toast = ref('');
const moreOpen = ref(false);
const supplierOfferCount = ref<number | null>(null);
const qualityProduct = ref<QualityProduct | null>(null);
const qualityLoaded = ref(false);
const rebuildStatus = ref<WebRebuildStatusResponse | null>(null);
const rebuildLoading = ref(false);
const expertMode = ref(window.localStorage.getItem('manager:product-workspace:expert') === '1');
const location = parseProductWorkspaceLocation(window.location.pathname);
const productId = location.productId;
const activeSection = ref<ProductWorkspaceSection>(location.section);
const context = loadProductWorkspaceContext();
const neighbors = computed(() => getProductWorkspaceNeighbors(context?.productIds || [], productId || 0));

const sections: Array<{ id: ProductWorkspaceSection; label: string; icon: typeof Package }> = [
  { id: 'main', label: 'Основное', icon: Package },
  { id: 'media', label: 'Медиа', icon: Images },
  { id: 'specifications', label: 'Характеристики', icon: Settings2 },
  { id: 'features', label: 'Фичи', icon: Sparkles },
  { id: 'suppliers', label: 'Поставщики', icon: Store },
  { id: 'publication', label: 'Публикация и файлы', icon: FileText },
  { id: 'relations', label: 'Связи и теги', icon: Link2 },
];

const mediaCount = computed(() => product.value ? getProductImageCount(product.value) : 0);

const publicProductUrl = computed(() => {
  if (!product.value?.slug) return null;
  const configured = String(import.meta.env.WEBSITE_URL || '').trim().replace(/\/+$/, '');
  const base = configured || (window.location.hostname === 'localhost'
    ? `${window.location.protocol}//${window.location.hostname}:4321`
    : window.location.origin);
  return `${base}/product/${product.value.slug}`;
});

const availabilityLabel = computed(() => {
  if (!product.value) return 'Нет данных';
  if (product.value.availability_status === 'in_stock_now') return 'В наличии';
  if (product.value.availability_status === 'available_2_3_days') return '2–3 дня';
  if (product.value.availability_status === 'check_availability') return 'Уточнить';
  return 'Нет в наличии';
});

const qualityIssues = computed(() => {
  const sectionByCategory: Record<string, ProductWorkspaceSection> = {
    media: 'media', specs: 'specifications', supplier: 'suppliers', commerce: 'main', identity: 'main',
  };
  return (qualityProduct.value?.issues || []).map((issue) => ({
    label: issue.message || issue.label,
    section: sectionByCategory[issue.category] || 'main',
    critical: issue.severity === 'critical',
  }));
});

const saveStateLabel = computed(() => saving.value ? 'Сохранение…' : dirty.value ? 'Есть несохранённые изменения' : 'Сохранено');

const setExpertMode = (value: boolean) => {
  expertMode.value = value;
  window.localStorage.setItem('manager:product-workspace:expert', value ? '1' : '0');
  moreOpen.value = false;
};

const setToast = (message: string) => {
  toast.value = message;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 3500);
};

const navigate = (path: string, replace = false) => {
  if (replace) window.history.replaceState({}, '', path);
  else window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

const loadProductQuality = async (detail: Product) => {
  qualityLoaded.value = false;
  qualityProduct.value = null;
  const quality = await api.getCatalogQualityReport({
    q: detail.slug || detail.title,
    onlyProblems: false,
    limit: 20,
  }).catch(() => null);
  if (product.value?.id !== detail.id) return;
  qualityProduct.value = quality?.items.find((item) => item.product_id === detail.id) || null;
  qualityLoaded.value = true;
};

const loadProduct = async () => {
  if (!productId) {
    errorMessage.value = 'Некорректный ID товара';
    loading.value = false;
    return;
  }
  loading.value = true;
  errorMessage.value = '';
  try {
    const [detail, rebuild] = await Promise.all([
      api.getManagerProduct(productId),
      api.getWebRebuildStatus().catch(() => null),
    ]);
    product.value = detail;
    supplierOfferCount.value = null;
    rebuildStatus.value = rebuild;
    loading.value = false;
    void loadProductQuality(detail);
  } catch (error) {
    errorMessage.value = `Не удалось открыть товар: ${getApiErrorMessage(error)}`;
  } finally {
    loading.value = false;
  }
};

const rebuildSite = async () => {
  if (rebuildLoading.value) return;
  rebuildLoading.value = true;
  try {
    rebuildStatus.value = await api.rebuildWeb();
    setToast('Пересборка сайта запущена');
  } catch (error) {
    setToast(`Не удалось запустить сборку: ${getApiErrorMessage(error)}`);
  } finally {
    rebuildLoading.value = false;
  }
};

const confirmLeave = async (): Promise<boolean> => !dirty.value || confirmDialog({
  title: 'Выйти без сохранения?',
  description: 'В товаре есть несохранённые изменения. Они будут потеряны.',
  confirmText: 'Выйти без сохранения',
  variant: 'warning',
});

const goBack = async () => {
  if (!await confirmLeave()) return;
  navigate(context?.returnTo || '/manager/products');
};

const navigateProduct = async (targetId: number | null) => {
  if (!targetId || !await confirmLeave()) return;
  navigate(buildProductWorkspacePath(targetId, activeSection.value));
};

const scrollToSection = (section: ProductWorkspaceSection) => {
  activeSection.value = section;
  window.history.replaceState({}, '', buildProductWorkspacePath(productId || 0, section));
};

const saveCurrent = async (): Promise<boolean> => {
  if (!editor.value || saving.value) return false;
  saving.value = true;
  try {
    const saved = await editor.value.save();
    if (saved) {
      await loadProduct();
      dirty.value = false;
      setToast('Изменения сохранены в CRM');
    }
    return saved;
  } finally {
    saving.value = false;
  }
};

const saveAndNext = async () => {
  const saved = await saveCurrent();
  if (saved && neighbors.value.nextId) await navigateProduct(neighbors.value.nextId);
};

const openMediaEditor = async () => {
  if (!product.value || !await confirmLeave()) return;
  const returnTo = buildProductWorkspacePath(product.value.id, 'media');
  const params = new URLSearchParams({
    editProductId: String(product.value.id),
    editProductQuery: product.value.title,
    productPanel: 'media',
    returnTo,
  });
  navigate(`/manager/products?${params.toString()}`);
};

const openPublicProduct = () => {
  if (publicProductUrl.value) window.open(publicProductUrl.value, '_blank', 'noopener,noreferrer');
};

const copyPublicProductLink = async () => {
  if (!publicProductUrl.value) return;
  await navigator.clipboard.writeText(publicProductUrl.value);
  setToast('Ссылка на товар скопирована');
  moreOpen.value = false;
};

const deleteProduct = async () => {
  if (!product.value || deleting.value) return;
  if (!await confirmDialog({
    title: 'Удалить товар?',
    description: `«${product.value.title}». Товар со связями удалить не получится.`,
    confirmText: 'Удалить товар',
    variant: 'danger',
  })) return;
  deleting.value = true;
  try {
    await api.deleteProduct(product.value.id);
    navigate(context?.returnTo || '/manager/products');
  } catch (error) {
    setToast(getApiErrorMessage(error));
  } finally {
    deleting.value = false;
    moreOpen.value = false;
  }
};

const beforeUnload = (event: BeforeUnloadEvent) => {
  if (!dirty.value) return;
  event.preventDefault();
  event.returnValue = '';
};

onMounted(() => {
  window.addEventListener('beforeunload', beforeUnload);
  void loadProduct();
});

onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload));
</script>

<template>
  <div class="min-h-full bg-gray-50 dark:bg-slate-950">
    <header class="sticky top-0 z-30 border-b border-gray-200 bg-white/95 px-4 py-3 shadow-sm backdrop-blur dark:border-slate-800 dark:bg-slate-950/95 sm:px-6">
      <div class="mx-auto flex max-w-[1680px] flex-col gap-3">
        <div class="flex min-w-0 items-center gap-3 pl-12 md:pl-0">
          <button type="button" class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-slate-700 dark:text-slate-200" title="К товарам" @click="goBack">
            <ArrowLeft class="h-4 w-4" />
          </button>
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2 text-xs text-gray-500 dark:text-slate-400">
              <span>Товары</span><span>/</span><span>#{{ productId }}</span>
              <span class="rounded-md px-2 py-0.5 font-semibold" :class="dirty ? 'bg-amber-100 text-amber-800' : 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300'">{{ saveStateLabel }}</span>
            </div>
            <h1 class="mt-0.5 truncate text-lg font-bold text-gray-950 dark:text-white sm:text-xl" :title="product?.title || ''">
              {{ product?.title || 'Карточка товара' }}
            </h1>
          </div>
          <div class="hidden items-center gap-2 lg:flex">
            <span v-if="product" class="rounded-md px-2 py-1 text-xs font-semibold" :class="product.is_published ? 'bg-emerald-100 text-emerald-800' : 'bg-gray-100 text-gray-600'">
              {{ product.is_published ? 'Опубликован' : 'Скрыт' }}
            </span>
            <span v-if="product" class="rounded-md bg-gray-100 px-2 py-1 text-xs font-semibold text-gray-700 dark:bg-slate-800 dark:text-slate-200">{{ product.price }} BYN</span>
            <span v-if="product" class="rounded-md bg-blue-50 px-2 py-1 text-xs font-semibold text-blue-800 dark:bg-blue-950 dark:text-blue-200">{{ availabilityLabel }}</span>
          </div>
          <button type="button" class="hidden h-9 items-center gap-2 rounded-lg border border-gray-200 px-3 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-40 dark:border-slate-700 dark:text-slate-200 sm:inline-flex" :disabled="!publicProductUrl" @click="openPublicProduct">
            <ExternalLink class="h-4 w-4" /> На сайте
          </button>
          <button v-if="activeSection !== 'features'" type="button" class="inline-flex h-9 items-center gap-2 rounded-lg bg-teal-600 px-3 text-sm font-semibold text-white shadow-sm hover:bg-teal-700 disabled:opacity-50" :disabled="saving || loading || activeSection === 'media'" @click="saveCurrent">
            <Save class="h-4 w-4" /> <span class="hidden sm:inline">{{ saving ? 'Сохранение…' : 'Сохранить' }}</span>
          </button>
          <div class="relative">
            <button type="button" class="flex h-9 w-9 items-center justify-center rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-slate-700 dark:text-slate-200" title="Дополнительные действия" @click="moreOpen = !moreOpen">
              <MoreHorizontal class="h-5 w-5" />
            </button>
            <div v-if="moreOpen" class="absolute right-0 top-11 z-40 w-56 rounded-lg border border-gray-200 bg-white p-1.5 shadow-xl dark:border-slate-700 dark:bg-slate-900">
              <button type="button" class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-slate-800" :disabled="!publicProductUrl" @click="openPublicProduct"><ExternalLink class="h-4 w-4" />Открыть на сайте</button>
              <button type="button" class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-slate-800" :disabled="!publicProductUrl" @click="copyPublicProductLink"><ClipboardCopy class="h-4 w-4" />Копировать ссылку</button>
              <button type="button" class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-slate-800" @click="setExpertMode(!expertMode)"><Wrench class="h-4 w-4" />{{ expertMode ? 'Выключить экспертный режим' : 'Экспертный режим' }}</button>
              <div class="my-1 border-t border-gray-100 dark:border-slate-800" />
              <button type="button" class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30" :disabled="deleting" @click="deleteProduct"><Trash2 class="h-4 w-4" />Удалить товар</button>
            </div>
          </div>
        </div>

        <div class="flex items-center justify-between gap-3">
          <div class="flex items-center gap-1">
            <button type="button" class="flex h-8 items-center gap-1 rounded-md px-2 text-xs font-semibold text-gray-600 hover:bg-gray-100 disabled:opacity-35 dark:text-slate-300 dark:hover:bg-slate-800" :disabled="!neighbors.previousId" @click="navigateProduct(neighbors.previousId)"><ChevronLeft class="h-4 w-4" />Предыдущий</button>
            <button type="button" class="flex h-8 items-center gap-1 rounded-md px-2 text-xs font-semibold text-gray-600 hover:bg-gray-100 disabled:opacity-35 dark:text-slate-300 dark:hover:bg-slate-800" :disabled="!neighbors.nextId" @click="navigateProduct(neighbors.nextId)">Следующий<ArrowRight class="h-4 w-4" /></button>
          </div>
          <button v-if="neighbors.nextId && !['media', 'features'].includes(activeSection)" type="button" class="hidden h-8 items-center gap-1 rounded-md px-2 text-xs font-semibold text-teal-700 hover:bg-teal-50 sm:flex" :disabled="saving" @click="saveAndNext">Сохранить и дальше<ArrowRight class="h-4 w-4" /></button>
        </div>
      </div>
    </header>

    <div v-if="loading" class="flex min-h-[520px] items-center justify-center gap-3 text-gray-500">
      <span class="h-6 w-6 animate-spin rounded-full border-2 border-teal-600 border-t-transparent" /> Загрузка товара…
    </div>
    <div v-else-if="errorMessage" class="mx-auto max-w-2xl px-4 py-20 text-center">
      <CircleAlert class="mx-auto h-10 w-10 text-red-500" />
      <p class="mt-4 font-semibold text-red-700">{{ errorMessage }}</p>
      <button type="button" class="mt-5 rounded-lg border border-gray-200 px-4 py-2 text-sm font-semibold" @click="goBack">Вернуться к товарам</button>
    </div>
    <div v-else-if="product" class="mx-auto grid max-w-[1680px] gap-5 px-4 py-5 xl:grid-cols-[190px_minmax(0,1fr)_270px] xl:px-6">
      <nav class="sticky top-[132px] z-20 -mx-4 flex gap-1 overflow-x-auto border-y border-gray-200 bg-white px-4 py-2 dark:border-slate-800 dark:bg-slate-950 xl:mx-0 xl:block xl:self-start xl:border-0 xl:bg-transparent xl:px-0 xl:py-0">
        <button v-for="section in sections" :key="section.id" type="button" class="flex h-10 shrink-0 items-center gap-2 rounded-lg px-3 text-sm font-semibold transition xl:mb-1 xl:w-full" :class="activeSection === section.id ? 'bg-teal-100 text-teal-800 dark:bg-teal-950 dark:text-teal-200' : 'text-gray-600 hover:bg-white dark:text-slate-300 dark:hover:bg-slate-900'" @click="scrollToSection(section.id)">
          <component :is="section.icon" class="h-4 w-4" />{{ section.label }}
          <span v-if="section.id === 'media'" class="ml-auto rounded-full bg-white px-1.5 text-[10px] text-gray-500 dark:bg-slate-800">{{ mediaCount }}</span>
          <span v-if="section.id === 'suppliers'" class="ml-auto rounded-full bg-white px-1.5 text-[10px] text-gray-500 dark:bg-slate-800" :title="supplierOfferCount == null ? 'Счётчик будет доступен после загрузки предложений' : undefined">{{ supplierOfferCount == null ? '—' : supplierOfferCount }}</span>
          <span v-if="section.id === 'publication' && rebuildStatus?.needs_rebuild" class="ml-auto h-2 w-2 rounded-full bg-amber-500" title="Сайт требует пересборки" />
        </button>
      </nav>

      <main class="min-w-0 overflow-hidden rounded-lg border border-gray-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <ProductWorkspaceMedia v-show="activeSection === 'media'" :product="product" @open-editor="openMediaEditor" />
        <ProductWorkspaceFeatures v-if="activeSection === 'features'" :product="product" />
        <ProductEditModal ref="editor" v-show="!['media', 'features'].includes(activeSection)" :model-value="true" :product="product" mode="edit" presentation="workspace" :workspace-section="activeSection" :expert-mode="expertMode" @update:model-value="goBack" @dirty-change="dirty = $event" @supplier-offers-loaded="supplierOfferCount = $event" />
      </main>

      <aside class="space-y-4 xl:sticky xl:top-[132px] xl:self-start">
        <section class="border-y border-gray-200 bg-white py-4 dark:border-slate-800 dark:bg-slate-950 xl:rounded-lg xl:border xl:p-4">
          <div class="flex items-center justify-between gap-3">
            <div>
              <p class="text-xs font-bold uppercase tracking-[0.14em] text-gray-400">Качество карточки</p>
              <p v-if="qualityProduct" class="mt-1 text-lg font-bold text-gray-950 dark:text-white">{{ qualityProduct.score }} / 100</p>
              <p v-else class="mt-1 text-sm font-bold text-gray-700 dark:text-slate-200">{{ qualityLoaded ? 'Нет данных отчёта' : 'Проверяем…' }}</p>
            </div>
            <CheckCircle2 v-if="qualityProduct && qualityIssues.length === 0" class="h-7 w-7 text-emerald-500" />
            <CircleAlert v-else-if="qualityProduct" class="h-7 w-7 text-amber-500" />
          </div>
          <div v-if="qualityIssues.length" class="mt-3 space-y-1.5">
            <button v-for="issue in qualityIssues" :key="issue.label" type="button" class="flex w-full items-start gap-2 rounded-md px-2 py-2 text-left text-xs hover:bg-gray-50 dark:hover:bg-slate-900" :class="issue.critical ? 'text-red-700 dark:text-red-300' : 'text-gray-600 dark:text-slate-300'" @click="scrollToSection(issue.section)">
              <CircleAlert class="mt-0.5 h-3.5 w-3.5 shrink-0" />{{ issue.label }}
            </button>
          </div>
        </section>

        <section class="border-y border-gray-200 bg-white py-4 text-sm dark:border-slate-800 dark:bg-slate-950 xl:rounded-lg xl:border xl:p-4">
          <p class="text-xs font-bold uppercase tracking-[0.14em] text-gray-400">Коммерция</p>
          <dl class="mt-3 space-y-2 text-gray-600 dark:text-slate-300">
            <div class="flex justify-between gap-3"><dt>Цена</dt><dd class="font-semibold text-gray-900 dark:text-white">{{ product.price }} BYN</dd></div>
            <div class="flex justify-between gap-3"><dt>Себестоимость</dt><dd>{{ product.min_cost_byn != null ? `${product.min_cost_byn.toFixed(2)} BYN` : '—' }}</dd></div>
            <div class="flex justify-between gap-3"><dt>Маржа</dt><dd>{{ product.margin_pct_preview != null ? `${(product.margin_pct_preview * 100).toFixed(1)}%` : '—' }}</dd></div>
            <div class="flex justify-between gap-3"><dt>Витебск</dt><dd>{{ product.vitebsk_qty || 0 }}</dd></div>
            <div class="flex justify-between gap-3"><dt>Минск</dt><dd>{{ product.minsk_qty || 0 }}</dd></div>
          </dl>
        </section>

        <section class="border-y py-4 text-sm xl:rounded-lg xl:border xl:p-4" :class="!rebuildStatus ? 'border-gray-200 bg-gray-50 text-gray-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300' : rebuildStatus.needs_rebuild ? 'border-amber-200 bg-amber-50 text-amber-950 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100' : 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-100'">
          <div class="flex items-start gap-2"><Link2 class="mt-0.5 h-4 w-4 shrink-0" /><p>{{ !rebuildStatus ? 'Статус публикации сайта сейчас недоступен.' : rebuildStatus.needs_rebuild ? 'В CRM есть изменения, которые ещё не опубликованы на сайте.' : 'Публичный сайт синхронизирован с каталогом.' }}</p></div>
          <p v-if="rebuildStatus?.last_error" class="mt-2 text-xs font-semibold text-red-700 dark:text-red-300">{{ rebuildStatus.last_error }}</p>
          <button v-if="rebuildStatus?.needs_rebuild" type="button" class="mt-3 inline-flex h-9 w-full items-center justify-center rounded-lg bg-amber-600 px-3 text-sm font-bold text-white hover:bg-amber-700 disabled:opacity-50" :disabled="rebuildLoading" @click="rebuildSite">{{ rebuildLoading ? 'Запускаем…' : 'Пересобрать сайт' }}</button>
        </section>
      </aside>
    </div>

    <Transition name="fade"><div v-if="toast" class="fixed bottom-5 right-5 z-50 rounded-lg bg-gray-950 px-4 py-3 text-sm font-semibold text-white shadow-xl">{{ toast }}</div></Transition>
  </div>
</template>
