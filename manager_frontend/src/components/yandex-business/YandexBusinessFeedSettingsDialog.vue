<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { Loader2, RefreshCw, X } from 'lucide-vue-next';

import {
  getYandexBusinessFeedSettings,
  previewYandexBusinessFeedSettings,
  updateYandexBusinessFeedSettings,
  type YandexBusinessFeedPreview,
  type YandexBusinessFeedSettings,
} from '../../services/yandex-business-feed-settings';

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: []; saved: [settings: YandexBusinessFeedSettings] }>();

const defaults = (): YandexBusinessFeedSettings => ({
  selection_mode: 'all_published',
  include_services: true,
  require_ready_image: false,
  require_in_stock: false,
});
const form = ref<YandexBusinessFeedSettings>(defaults());
const preview = ref<YandexBusinessFeedPreview | null>(null);
const loading = ref(false);
const previewing = ref(false);
const saving = ref(false);
const error = ref('');
const exclusionLabel = (reason: string) => ({ missing_ready_yandex_image: 'нет готовой картинки', not_in_stock: 'нет в наличии', not_in_curated_collections: 'не входит в выбранные подборки' }[reason] || 'не соответствует правилам выгрузки');
const close = () => { if (!saving.value) emit('close'); };
const previewSignature = ref('');
const signature = computed(() => JSON.stringify(form.value));
const previewCurrent = computed(() => Boolean(preview.value) && previewSignature.value === signature.value);
watch(signature, () => { preview.value = null; });

const load = async () => {
  loading.value = true;
  error.value = '';
  try {
    form.value = await getYandexBusinessFeedSettings();
    await refreshPreview();
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'Не удалось загрузить настройки фида';
  } finally {
    loading.value = false;
  }
};



const refreshPreview = async () => {
  previewing.value = true;
  error.value = '';
  const snapshot = { ...form.value };
  const requested = JSON.stringify(snapshot);
  try {
    const result = await previewYandexBusinessFeedSettings(snapshot);
    if (signature.value !== requested || !props.open) return;
    preview.value = result;
    previewSignature.value = requested;
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'Не удалось сформировать предпросмотр';
  } finally {
    previewing.value = false;
  }
};

const save = async () => {
  if (!previewCurrent.value || loading.value || previewing.value || saving.value) return;
  saving.value = true;
  error.value = '';
  try {
    const saved = await updateYandexBusinessFeedSettings(form.value);
    form.value = saved;
    emit('saved', saved);
    emit('close');
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'Не удалось сохранить настройки';
  } finally {
    saving.value = false;
  }
};
watch(() => props.open, (open) => {
  if (open) void load();
  else preview.value = null;
}, { immediate: true });
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-[120] flex items-center justify-center bg-slate-950/55 p-4" @click.self="close">
      <form role="dialog" aria-modal="true" aria-labelledby="yandex-feed-settings-title" class="max-h-[94vh] w-full max-w-2xl overflow-y-auto rounded-3xl bg-white shadow-2xl dark:bg-slate-900" @submit.prevent="save">
        <header class="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-5 dark:border-slate-800">
          <div>
            <p class="text-xs font-bold uppercase tracking-[0.16em] text-brand-600">Яндекс Бизнес</p>
            <h2 id="yandex-feed-settings-title" class="mt-1 text-xl font-bold text-slate-950 dark:text-white">Состав YML-фида</h2>
          </div>
          <button type="button" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800" aria-label="Закрыть" @click="close"><X class="h-5 w-5" /></button>
        </header>

        <div class="space-y-5 px-6 py-6">
          <p class="text-sm leading-6 text-slate-600 dark:text-slate-300">Настройки управляют ассортиментом в Яндекс Бизнесе. В выбранных подборках — до 24 товаров на категорию.</p>
          <a href="/manager/product-collections" class="inline-flex text-sm font-semibold text-brand-700 underline">Выбрать товары и категории в подборках</a>
          <fieldset :disabled="loading || saving" class="space-y-4">
            <legend class="text-sm font-semibold text-slate-900 dark:text-white">Какие товары отдавать</legend>
            <label class="flex cursor-pointer gap-3 rounded-xl border p-4" :class="form.selection_mode === 'all_published' ? 'border-brand-500 bg-brand-50/60 dark:border-brand-500 dark:bg-brand-950/20' : 'border-slate-200 dark:border-slate-700'">
              <input v-model="form.selection_mode" value="all_published" type="radio" name="yandex-feed-mode">
              <span><span class="block font-semibold text-slate-900 dark:text-white">Все опубликованные</span><span class="mt-1 block text-sm text-slate-600 dark:text-slate-300">Все опубликованные товары с ценой, сгруппированные по подборкам и брендам.</span></span>
            </label>
            <label class="flex cursor-pointer gap-3 rounded-xl border p-4" :class="form.selection_mode === 'curated_collections' ? 'border-brand-500 bg-brand-50/60 dark:border-brand-500 dark:bg-brand-950/20' : 'border-slate-200 dark:border-slate-700'">
              <input v-model="form.selection_mode" value="curated_collections" type="radio" name="yandex-feed-mode">
              <span><span class="block font-semibold text-slate-900 dark:text-white">Кураторские подборки</span><span class="mt-1 block text-sm text-slate-600 dark:text-slate-300">Только опубликованные подборки с размещением «Яндекс Бизнес · Категории».</span></span>
            </label>
            <label class="flex items-start gap-3 text-sm text-slate-800 dark:text-slate-200"><input v-model="form.include_services" type="checkbox" class="mt-0.5">Добавлять активные услуги с положительной ценой</label>
            <label class="flex items-start gap-3 text-sm text-slate-800 dark:text-slate-200"><input v-model="form.require_ready_image" type="checkbox" class="mt-0.5">Исключать товары без готового изображения для Яндекса</label>
            <label class="flex items-start gap-3 text-sm text-slate-800 dark:text-slate-200"><input v-model="form.require_in_stock" type="checkbox" class="mt-0.5">Исключать товары без статуса «в наличии сейчас»</label>
          </fieldset>

          <section class="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/60">
            <div class="flex items-center justify-between gap-3"><h3 class="font-semibold text-slate-900 dark:text-white">Предпросмотр</h3><button type="button" class="inline-flex items-center gap-2 text-sm font-semibold text-brand-700 disabled:opacity-60" :disabled="loading || previewing" @click="refreshPreview"><RefreshCw class="h-4 w-4" :class="{ 'animate-spin': previewing }" />Обновить</button></div>
            <div v-if="preview" class="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4"><div><strong class="block text-lg">{{ preview.product_offer_count }}</strong>товаров</div><div><strong class="block text-lg">{{ preview.product_picture_count }}</strong>с картинкой</div><div><strong class="block text-lg">{{ preview.service_offer_count }}</strong>услуг</div><div><strong class="block text-lg">{{ preview.excluded_product_count }}</strong>исключено</div></div>
            <p v-else-if="loading" class="mt-3 text-sm text-slate-500">Считаем состав фида…</p>
            <ul v-if="preview?.editorial_categories?.length" class="mt-3 space-y-1 text-sm"><li v-for="category in preview.editorial_categories" :key="category.category_id">{{ category.title }} — {{ category.offer_count }} товаров</li></ul>
            <p v-if="preview && !preview.product_offer_count" class="mt-3 text-sm text-amber-700">Выгрузка не содержит товаров. Проверьте подборки и ограничения перед сохранением.</p>
            <ul v-if="preview?.excluded_products.length" class="mt-4 space-y-1 text-sm text-slate-600 dark:text-slate-300"><li v-for="item in preview.excluded_products.slice(0, 5)" :key="item.product_id">{{ item.product_title }} — {{ exclusionLabel(item.reason) }}</li></ul>
          </section>
          <p v-if="error" role="alert" class="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{{ error }}</p>
        </div>
        <p v-if="!previewCurrent && !loading" class="px-6 pb-3 text-sm text-amber-700">Обновите предпросмотр перед сохранением изменённых правил.</p>
        <footer class="flex justify-end gap-3 border-t border-slate-100 px-6 py-5 dark:border-slate-800"><button type="button" class="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-600 dark:border-slate-700 dark:text-slate-300" @click="close">Отмена</button><button type="submit" class="inline-flex items-center gap-2 rounded-xl bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-60" :disabled="loading || saving || previewing || !previewCurrent"><Loader2 v-if="saving" class="h-4 w-4 animate-spin" />Сохранить</button></footer>
      </form>
    </div>
  </Teleport>
</template>
