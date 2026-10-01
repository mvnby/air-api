<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { getApiErrorMessage } from '../../utils/api-errors';
import { orderSourceReviewApi, type SourceCard, type SourceCommandHook } from '../../services/order-source-review';

const props = defineProps<{ orderId: number; sourceEnrichment?: unknown; beforeReview?: SourceCommandHook }>();
const emit = defineEmits<{ review: []; toast: [result: { message: string; type: 'success' | 'error' }] }>();
const card = ref<SourceCard | null>(null);
const loading = ref(false);
const error = ref('');
const expanded = ref(false);
const downloadingId = ref<number | null>(null);
let loadVersion = 0;
const equipment = computed(() => card.value?.objects.flatMap((object) => object.equipment) || []);
const unitCount = computed(() => equipment.value.reduce((sum, item) => sum + (item.quantity || 0), 0));
const safeSourceUrl = computed(() => {
  try { const url = new URL(card.value?.source_url || ''); return ['http:', 'https:'].includes(url.protocol) ? url.href : null; }
  catch { return null; }
});
const load = async () => {
  const orderId = props.orderId; const version = ++loadVersion;
  loading.value = true; error.value = '';
  try { const data = await orderSourceReviewApi.card(orderId); if (props.orderId === orderId && version === loadVersion) card.value = data; }
  catch (reason) { if (props.orderId === orderId && version === loadVersion) error.value = getApiErrorMessage(reason); }
  finally { if (props.orderId === orderId && version === loadVersion) loading.value = false; }
};
const review = async () => {
  const orderId = props.orderId;
  try { if (await props.beforeReview?.() === false || props.orderId !== orderId) return; emit('review'); }
  catch (reason) { if (props.orderId === orderId) error.value = getApiErrorMessage(reason); }
};
const download = async (file: SourceCard['originals'][number]) => {
  if (downloadingId.value) return;
  const orderId = props.orderId; downloadingId.value = file.attachment_id;
  try {
    const access = await orderSourceReviewApi.originalAccess(file.attachment_id);
    if (props.orderId !== orderId) return;
    const anchor = document.createElement('a'); anchor.href = access.url; anchor.download = file.name;
    anchor.rel = 'noopener noreferrer'; anchor.referrerPolicy = 'no-referrer';
    document.body.appendChild(anchor); anchor.click(); anchor.remove();
  } catch (reason) { if (props.orderId === orderId) error.value = getApiErrorMessage(reason); }
  finally { if (props.orderId === orderId) downloadingId.value = null; }
};
watch(() => props.orderId, () => { card.value = null; expanded.value = false; downloadingId.value = null; void load(); }, { immediate: true });
watch(() => props.sourceEnrichment, () => { void load(); });
</script>

<template>
  <section class="rounded-xl border border-slate-200 p-3 text-sm dark:border-slate-700" aria-label="Заявка из источника">
    <div class="flex items-center justify-between gap-2">
      <button type="button" class="min-w-0 text-left" :aria-expanded="expanded" @click="expanded = !expanded">
        <span class="block font-semibold">Заявка {{ card ? `№${card.external_id}` : '' }}</span>
        <span v-if="card" class="block text-xs text-slate-500">{{ unitCount }} шт. · {{ card.originals.length }} {{ card.originals.length === 1 ? 'файл' : 'файла' }} · {{ expanded ? 'Свернуть' : 'Подробности' }}</span>
      </button>
      <button type="button" class="shrink-0 text-xs font-semibold text-brand-700" @click="review">Проработать</button>
    </div>
    <p v-if="loading" class="mt-2 text-xs text-slate-500">Загружаем заявку…</p>
    <p v-if="error" role="alert" class="mt-2 break-words text-xs text-red-700">{{ error }} <button type="button" class="underline" @click="load">Повторить</button></p>
    <div v-if="expanded && card" class="mt-3 space-y-3">
      <p v-if="card.title" class="text-xs text-slate-600">{{ card.title }}</p>
      <a v-if="safeSourceUrl" :href="safeSourceUrl" target="_blank" rel="noopener noreferrer" class="text-xs font-semibold text-brand-700 underline">Открыть закупку</a>
      <table v-if="equipment.length" class="w-full text-left text-xs"><thead><tr><th class="pb-2 font-semibold">Модель</th><th class="pb-2 text-right font-semibold">Шт.</th></tr></thead><tbody><tr v-for="(item, index) in equipment" :key="index" class="border-t border-slate-100 align-top"><td class="py-2 pr-2 break-words">{{ [item.brand, item.model].filter(Boolean).join(' ') || 'Модель не указана' }}</td><td class="py-2 text-right">{{ item.quantity ?? '—' }}</td></tr></tbody></table>
      <p v-else class="text-xs text-slate-500">Проверьте модели и количество в проработке источника.</p>
      <div v-if="card.installation_facts?.length"><p class="text-xs font-semibold">Монтаж по заявке</p><p class="mt-1 text-xs text-slate-500">Сверить по объектам и оригиналам. Длины трасс здесь не меняют цену монтажа автоматически.</p><ul class="mt-2 space-y-1 text-xs text-slate-600"><li v-for="(fact, index) in card.installation_facts" :key="index"><span v-if="fact.is_excerpt">Фрагмент: </span>{{ fact.text }}</li></ul></div>
      <details v-if="card.work_summary || card.equipment_details" class="text-xs"><summary class="cursor-pointer font-semibold">Текст заявки</summary><p v-if="card.work_summary" class="mt-2 whitespace-pre-line break-words text-slate-600">{{ card.work_summary }}</p><p v-if="card.equipment_details" class="mt-2 whitespace-pre-line break-words text-slate-600">{{ card.equipment_details }}</p></details>
      <div><p class="mb-1 text-xs font-semibold">Исходные файлы</p><button v-for="file in card.originals" :key="file.attachment_id" type="button" :disabled="Boolean(downloadingId)" class="mt-1 block w-full break-all text-left text-xs font-medium text-brand-700 underline" @click="download(file)">{{ downloadingId === file.attachment_id ? 'Скачиваем…' : file.name }}</button><p v-if="!card.originals.length" class="text-xs text-slate-500">Выберите оригиналы в проработке источника и сохраните заявку.</p></div>
    </div>
  </section>
</template>
