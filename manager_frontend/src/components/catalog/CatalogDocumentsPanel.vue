<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { FileText, Link2, Plus, Trash2, Upload } from 'lucide-vue-next';
import { MANAGER_CAPABILITY, hasManagerCapability } from '../../manager-capabilities';
import { managerSession } from '../../services/manager-session';
import { catalogDocumentsApi, type CatalogDocumentInput, type CatalogDocumentKind, type CatalogDocumentTarget, type CatalogDocumentWorkspace } from '../../services/catalog-documents-api';
import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{ targetType: CatalogDocumentTarget; targetId: number; readOnly?: boolean }>();
const emit = defineEmits<{ saved: [] }>();
const workspace = ref<CatalogDocumentWorkspace | null>(null);
const draft = ref<CatalogDocumentInput[]>([]);
const baseline = ref('[]');
const loading = ref(false);
const busy = ref(false);
const error = ref('');
const notice = ref('');
const fileInput = ref<HTMLInputElement | null>(null);
let version = 0;
let cancelPending: (() => void) | null = null;
const canEdit = computed(() => !props.readOnly && hasManagerCapability(managerSession.auth.value, MANAGER_CAPABILITY.catalogMasterEdit));
const dirty = computed(() => JSON.stringify(draft.value) !== baseline.value);
const ownUrls = computed(() => new Set(draft.value.map(item => item.url.trim())));
const kinds: { value: CatalogDocumentKind; label: string }[] = [
  { value: 'catalog', label: 'Каталог' }, { value: 'operation', label: 'Эксплуатация' },
  { value: 'installation', label: 'Монтаж' }, { value: 'service', label: 'Сервис' },
  { value: 'brochure', label: 'Буклет' }, { value: 'certificate', label: 'Сертификат' }, { value: 'other', label: 'Другой документ' },
];
const originLabel = (type: CatalogDocumentTarget) => ({ brand: 'Бренд', series: 'Серия', product: 'Товар' }[type]);
const kindLabel = (value: CatalogDocumentKind) => kinds.find(item => item.value === value)?.label || value;
const newDocument = (title = '', url = ''): CatalogDocumentInput => ({ title, url, kind: 'other', source_url: null, language: null, year: null, visibility: 'public', inherit_to_products: true });
const applyWorkspace = (value: CatalogDocumentWorkspace) => {
  workspace.value = value;
  draft.value = value.own.map(item => ({ title: item.title, url: item.url, kind: item.kind, source_url: item.source_url, language: item.language, year: item.year, visibility: item.visibility, inherit_to_products: item.inherit_to_products }));
  baseline.value = JSON.stringify(draft.value);
};
const load = async () => {
  const requestVersion = ++version;
  cancelPending?.();
  cancelPending = null;
  workspace.value = null;
  draft.value = [];
  baseline.value = '[]';
  busy.value = false;
  error.value = '';
  notice.value = '';
  if (props.targetId <= 0) { loading.value = false; return; }
  loading.value = true;
  const request = catalogDocumentsApi.get(props.targetType, props.targetId);
  cancelPending = () => request.cancel();
  try {
    const result = await request;
    if (requestVersion === version) applyWorkspace(result);
  } catch (failure) {
    if (requestVersion === version && !request.isCancelled) error.value = getApiErrorMessage(failure) || 'Не удалось загрузить документы.';
  } finally {
    if (requestVersion === version) { loading.value = false; cancelPending = null; }
  }
};
const save = async () => {
  if (busy.value) return false;
  if (!dirty.value) return true;
  if (!canEdit.value || !workspace.value) return false;
  if (draft.value.some(item => !item.title.trim() || !item.url.trim())) { error.value = 'Укажите название и ссылку для каждого документа.'; return false; }
  const requestVersion = version;
  busy.value = true;
  error.value = '';
  notice.value = '';
  const documents = draft.value.map(item => ({ ...item, title: item.title.trim(), url: item.url.trim(), source_url: item.source_url?.trim() || null, language: item.language?.trim() || null, year: item.year || null }));
  const request = catalogDocumentsApi.replace(props.targetType, props.targetId, documents);
  cancelPending = () => request.cancel();
  try {
    const result = await request;
    if (requestVersion === version) { applyWorkspace(result); notice.value = 'Документы сохранены.'; emit('saved'); return true; }
    return false;
  } catch (failure) {
    if (requestVersion === version && !request.isCancelled) error.value = getApiErrorMessage(failure) || 'Не удалось сохранить документы.';
    return false;
  } finally {
    if (requestVersion === version) { busy.value = false; cancelPending = null; }
  }
};
const upload = async (event: Event) => {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = '';
  if (!file || !canEdit.value || !workspace.value || busy.value || draft.value.length >= 100) return;
  if (file.size > 25 * 1024 * 1024) { error.value = 'Размер документа превышает 25 МБ.'; return; }
  const requestVersion = version;
  busy.value = true;
  error.value = '';
  notice.value = '';
  const request = catalogDocumentsApi.upload(props.targetType, props.targetId, file);
  cancelPending = () => request.cancel();
  try {
    const result = await request;
    if (requestVersion === version) {
      if (draft.value.some(item => item.url === result.url)) notice.value = 'Этот файл уже добавлен.';
      else { draft.value.push(newDocument(result.title, result.url)); notice.value = 'Файл загружен. Сохраните список документов.'; }
    }
  } catch (failure) {
    if (requestVersion === version && !request.isCancelled) error.value = getApiErrorMessage(failure) || 'Не удалось загрузить файл.';
  } finally {
    if (requestVersion === version) { busy.value = false; cancelPending = null; }
  }
};
watch(() => [props.targetType, props.targetId], () => { void load(); }, { immediate: true });
onBeforeUnmount(() => { ++version; cancelPending?.(); });
defineExpose({ isDirty: dirty, isBusy: busy, save });
</script>

<template>
  <section class="space-y-4" aria-label="Документы каталога">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div><h3 class="flex items-center gap-2 font-semibold"><FileText :size="18" aria-hidden="true" />Документы и материалы</h3><p class="mt-1 text-sm text-slate-500">Каталоги, инструкции и материалы для проверки характеристик.</p></div>
      <div v-if="canEdit && workspace" class="flex flex-wrap gap-2">
        <button type="button" class="btn-mini-outline" :disabled="busy || draft.length >= 100" @click="draft.push(newDocument())"><Plus :size="14" />Добавить ссылку</button>
        <button type="button" class="btn-mini-outline" :disabled="busy || draft.length >= 100" @click="fileInput?.click()"><Upload :size="14" />Загрузить PDF / DOCX</button>
        <input ref="fileInput" type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" class="hidden" aria-label="Загрузить документ" @change="upload" />
      </div>
    </div>
    <p v-if="targetId <= 0" class="text-sm text-slate-500">Сначала сохраните {{ targetType === 'brand' ? 'бренд' : targetType === 'series' ? 'серию' : 'товар' }}, затем добавьте документы.</p>
    <p v-if="loading" class="text-sm text-slate-500">Загрузка документов…</p>
    <p v-if="error" role="alert" class="text-sm text-red-600">{{ error }}<button v-if="!workspace && !loading" type="button" class="ml-2 underline" @click="load">Повторить</button></p>
    <p v-if="notice" role="status" class="text-sm text-emerald-700 dark:text-emerald-400">{{ notice }}</p>
    <template v-if="workspace">
      <p v-if="!draft.length" class="text-sm text-slate-500">Собственные документы пока не добавлены.</p>
      <fieldset v-for="(item, index) in draft" :key="index" :disabled="!canEdit || busy" class="space-y-3 rounded-lg border border-slate-200 p-3 dark:border-slate-700">
        <legend class="sr-only">Документ {{ index + 1 }}</legend>
        <div class="flex items-start gap-2"><label class="min-w-0 flex-1 text-xs text-slate-500">Название<input v-model="item.title" class="field-input mt-1 w-full" maxlength="250" placeholder="Инструкция по эксплуатации" /></label><button v-if="canEdit" type="button" class="btn-mini-outline mt-5 text-red-600" :aria-label="`Убрать документ ${index + 1}`" @click="draft.splice(index, 1)"><Trash2 :size="15" /></button></div>
        <div class="grid gap-3 sm:grid-cols-2"><label class="text-xs text-slate-500">Тип<select v-model="item.kind" class="field-input mt-1 w-full"><option v-for="kind in kinds" :key="kind.value" :value="kind.value">{{ kind.label }}</option></select></label><label class="text-xs text-slate-500">Доступ<select v-model="item.visibility" class="field-input mt-1 w-full"><option value="public">На сайте и в Manager</option><option value="internal">Только Manager и AI</option></select></label></div>
        <label class="block text-xs text-slate-500">Ссылка на документ<input v-model="item.url" class="field-input mt-1 w-full" maxlength="2048" placeholder="https://…" /></label>
        <a v-if="item.url && /^(https?:\/\/|\/media\/)/i.test(item.url)" :href="item.url" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 text-xs text-brand-600"><Link2 :size="13" />Открыть документ</a>
        <details><summary class="cursor-pointer text-xs text-slate-500">Источник, язык и год</summary><div class="mt-2 grid gap-3 sm:grid-cols-2"><label class="text-xs text-slate-500 sm:col-span-2">Страница источника<input v-model="item.source_url" class="field-input mt-1 w-full" placeholder="Официальная страница материала" maxlength="2048" /></label><label class="text-xs text-slate-500">Язык<input v-model="item.language" class="field-input mt-1 w-full" placeholder="ru, en, ru-BY" maxlength="16" /></label><label class="text-xs text-slate-500">Год<input v-model.number="item.year" class="field-input mt-1 w-full" type="number" min="1900" max="2200" placeholder="2026" /></label></div></details>
        <label v-if="targetType !== 'product'" class="flex items-center gap-2 text-sm"><input v-model="item.inherit_to_products" type="checkbox" />{{ targetType === 'brand' ? 'Доступен у серий и товаров этого бренда' : 'Доступен у всех товаров серии' }}</label>
      </fieldset>
      <p v-if="canEdit" class="text-xs text-slate-500">Загрузка до 25 МБ предназначена для публичных материалов. Для закрытых документов добавьте ссылку на источник и выберите «Только Manager и AI».</p>
      <div v-if="canEdit" class="flex items-center gap-3"><button type="button" class="btn-mini-outline" :disabled="!dirty || busy" @click="save">{{ busy ? 'Подождите…' : 'Сохранить документы' }}</button><span v-if="dirty" class="text-xs text-amber-700 dark:text-amber-400">Есть несохранённые изменения</span></div>
      <div v-if="workspace.inherited.length" class="space-y-2 border-t border-slate-200 pt-4 dark:border-slate-700"><h4 class="text-sm font-medium">Документы бренда и серии</h4><p class="text-xs text-slate-500">Редактируются у владельца и доступны автоматически. Собственный документ по той же ссылке имеет приоритет.</p><div v-for="item in workspace.inherited" :key="`${item.origin_type}-${item.id}`" class="flex items-start gap-2 rounded-lg bg-slate-50 p-3 dark:bg-slate-900"><FileText :size="16" class="mt-0.5 shrink-0 text-slate-400" /><div class="min-w-0"><a :href="item.url" target="_blank" rel="noopener noreferrer" class="text-sm text-brand-600">{{ item.title }}</a><p class="mt-0.5 text-xs text-slate-500">{{ originLabel(item.origin_type) }}: {{ item.origin_title }} · {{ kindLabel(item.kind) }}<span v-if="item.visibility === 'internal'"> · Только Manager и AI</span><span v-if="item.language"> · {{ item.language }}</span><span v-if="item.year"> · {{ item.year }}</span><span v-if="ownUrls.has(item.url)"> · Переопределён здесь</span></p></div></div></div>
    </template>
  </section>
</template>
