<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import {
  ManagerDocumentSystemService,
  type DocumentLegalEntityItem,
  type DocumentLegalEntityUpdatePayload,
} from '../client';
import DocumentLegalEntitiesPanel from '../features/documents/settings/DocumentLegalEntitiesPanel.vue';
import KitlanePartnerIdentity from '../components/kitlane/KitlanePartnerIdentity.vue';
import { refreshKitlaneBrand } from '../composables/useKitlaneIdentity';
import { legalEntityTypeForName } from '../features/settings/legal-entity-type';
import {
  StorefrontSettingsApiError,
  storefrontSettingsApi,
  type ServiceCatalogTemplatePreview,
  type StorefrontServiceSettings,
  type StorefrontSettings,
} from '../features/settings/storefront-settings-api';
import { getApiErrorMessage } from '../utils/api-errors';

type Tab = 'company' | 'site' | 'services' | 'staff';
const tabs: Array<{ id: Tab; label: string }> = [
  { id: 'company', label: 'Компания' },
  { id: 'site', label: 'Сайт' },
  { id: 'services', label: 'Услуги' },
  { id: 'staff', label: 'Сотрудники' },
];
const serviceLabels: Record<StorefrontServiceSettings['key'], string> = {
  installation: 'Монтаж', pre_install: 'Предмонтаж', dismantling: 'Демонтаж', maintenance: 'Обслуживание', repair: 'Ремонт',
};
const activeTab = ref<Tab>('company');
const settings = ref<StorefrontSettings | null>(null);
const draft = ref<StorefrontSettings | null>(null);
const loading = ref(true);
const saving = ref(false);
const uploadingLogo = ref(false);
const clonePreview = ref<ServiceCatalogTemplatePreview | null>(null);
const cloneLoading = ref(false);
const cloneBusy = ref(false);
const entities = ref<DocumentLegalEntityItem[]>([]);
const selectedEntityId = ref<number | null>(null);
const entitiesLoading = ref(false);
const entitySaving = ref(false);
const message = ref('');
const messageType = ref<'success' | 'error'>('success');

const notify = (value: string, type: 'success' | 'error' = 'success') => {
  message.value = value;
  messageType.value = type;
};
const copy = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
const hasChanges = computed(() => JSON.stringify(settings.value) !== JSON.stringify(draft.value));

const load = async () => {
  loading.value = true;
  try {
    const result = await storefrontSettingsApi.get();
    settings.value = result;
    draft.value = copy(result);
  } catch (error) {
    notify(`Не удалось загрузить настройки: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    loading.value = false;
  }
};
const save = async () => {
  if (!draft.value || saving.value) return;
  saving.value = true;
  try {
    const saved = await storefrontSettingsApi.save(copy(draft.value));
    settings.value = saved;
    draft.value = copy(saved);
    refreshKitlaneBrand();
    notify('Настройки сохранены');
  } catch (error) {
    if ((error instanceof StorefrontSettingsApiError || typeof error === 'object') && (error as { status?: number } | null)?.status === 409) {
      notify('Настройки изменились у другого пользователя. Загрузите свежую версию и повторите правки.', 'error');
      return;
    }
    notify(`Не удалось сохранить: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    saving.value = false;
  }
};
const uploadLogo = async (event: Event, compact: boolean) => {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file || !draft.value || uploadingLogo.value) return;
  uploadingLogo.value = true;
  try {
    const asset = await storefrontSettingsApi.uploadLogo(file);
    if (!draft.value) return;
    if (compact) {
      draft.value.site.compact_logo_asset_id = asset.id;
      draft.value.site.compact_logo_url = asset.url;
    } else {
      draft.value.site.logo_asset_id = asset.id;
      draft.value.site.logo_url = asset.url;
    }
    notify('Логотип загружен. Сохраните настройки, чтобы опубликовать его.');
  } catch (error) {
    notify(`Не удалось загрузить логотип: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    uploadingLogo.value = false;
    input.value = '';
  }
};
const clearLogo = (compact: boolean) => {
  if (!draft.value) return;
  if (compact) {
    draft.value.site.compact_logo_asset_id = null;
    draft.value.site.compact_logo_url = null;
  } else {
    draft.value.site.logo_asset_id = null;
    draft.value.site.logo_url = null;
  }
};
const loadPreview = async () => {
  cloneLoading.value = true;
  try { clonePreview.value = await storefrontSettingsApi.previewTemplate(); }
  catch (error) { notify(`Не удалось проверить шаблон услуг: ${getApiErrorMessage(error)}`, 'error'); }
  finally { cloneLoading.value = false; }
};
const cloneTemplate = async () => {
  if (!clonePreview.value || cloneBusy.value) return;
  cloneBusy.value = true;
  try {
    const result = await storefrontSettingsApi.cloneTemplate(clonePreview.value.source_fingerprint);
    notify(result.status === 'cloned' ? 'Каталог услуг скопирован. Проверьте и сохраните названия.' : 'Этот каталог уже был скопирован ранее.');
    await loadPreview();
  } catch (error) {
    notify(error instanceof StorefrontSettingsApiError && error.status === 409
      ? 'Шаблон или ваш каталог изменились. Обновите проверку перед копированием.'
      : `Не удалось скопировать шаблон: ${getApiErrorMessage(error)}`, 'error');
  } finally { cloneBusy.value = false; }
};
const loadEntities = async (preferId?: number) => {
  entitiesLoading.value = true;
  try {
    entities.value = (await ManagerDocumentSystemService.listManagerDocumentLegalEntities()).items;
    selectedEntityId.value = entities.value.some(item => item.id === (preferId || selectedEntityId.value))
      ? (preferId || selectedEntityId.value) : entities.value.find(item => item.is_default)?.id || entities.value[0]?.id || null;
  } catch (error) { notify(`Не удалось загрузить реквизиты: ${getApiErrorMessage(error)}`, 'error'); }
  finally { entitiesLoading.value = false; }
};
const createEntity = async (displayName: string) => {
  entitySaving.value = true;
  try {
    const entityType = legalEntityTypeForName(displayName);
    const entity = await ManagerDocumentSystemService.createManagerDocumentLegalEntity({ display_name: displayName, entity_type: entityType });
    await loadEntities(entity.id); notify('Компания добавлена');
  } catch (error) { notify(`Не удалось добавить компанию: ${getApiErrorMessage(error)}`, 'error'); }
  finally { entitySaving.value = false; }
};
const updateEntity = async (id: number, changes: DocumentLegalEntityUpdatePayload) => {
  entitySaving.value = true;
  try { await ManagerDocumentSystemService.patchManagerDocumentLegalEntity(id, changes); await loadEntities(id); notify('Реквизиты сохранены'); }
  catch (error) { notify(`Не удалось сохранить реквизиты: ${getApiErrorMessage(error)}`, 'error'); }
  finally { entitySaving.value = false; }
};
watch(activeTab, tab => { if (tab === 'services' && !clonePreview.value) void loadPreview(); });
onMounted(() => { void Promise.all([load(), loadEntities()]); });
</script>

<template>
  <main class="min-h-full bg-slate-50 p-4 dark:bg-slate-950 sm:p-6 lg:p-8">
    <div class="mx-auto max-w-5xl space-y-6">
      <header class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div><p class="text-xs font-bold uppercase tracking-[0.18em] text-brand-600">Ваше пространство</p><h1 class="mt-1 font-['Space_Grotesk'] text-3xl font-bold text-slate-950 dark:text-white">Настройки</h1><p class="mt-2 text-sm text-slate-500">Компания, данные сайта, услуги и доступ команды.</p></div>
        <button v-if="activeTab === 'site' || activeTab === 'services'" type="button" class="rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60" :disabled="saving || uploadingLogo || !hasChanges" @click="save">{{ saving ? 'Сохраняем…' : 'Сохранить' }}</button>
      </header>
      <div class="flex flex-wrap gap-2 border-b border-slate-200 pb-3 dark:border-slate-800">
        <button v-for="tab in tabs" :key="tab.id" type="button" class="rounded-lg px-3 py-2 text-sm font-semibold" :class="activeTab === tab.id ? 'bg-brand-600 text-white' : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-900'" @click="activeTab = tab.id">{{ tab.label }}</button>
      </div>
      <section v-if="loading" class="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900">Загружаем настройки…</section>
      <template v-else>
        <section v-if="activeTab === 'company'" class="space-y-4"><p class="text-sm text-slate-500">Эти реквизиты используются в ваших документах.</p><DocumentLegalEntitiesPanel :items="entities" :selected-id="selectedEntityId" :loading="entitiesLoading" :saving="entitySaving" @select="selectedEntityId = $event" @create="createEntity" @update="updateEntity" /></section>
        <section v-else-if="activeTab === 'site' && draft" class="grid gap-4 rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900 sm:grid-cols-2">
          <div class="sm:col-span-2 space-y-3"><h2 class="font-semibold text-slate-950 dark:text-white">Бренд сайта и рабочего пространства</h2><KitlanePartnerIdentity :name="draft.site.display_name" :logo-url="draft.site.logo_url" :compact-logo-url="draft.site.compact_logo_url" /><p class="text-xs text-slate-500">Название и логотипы доступны на сайте через настройки витрины. После загрузки нажмите «Сохранить».</p></div>
          <div class="space-y-2"><label class="field">Полный логотип<input type="file" accept="image/*,.svg" :disabled="uploadingLogo" @change="uploadLogo($event, false)" /></label><button v-if="draft.site.logo_asset_id" type="button" class="text-sm text-brand-700" @click="clearLogo(false)">Убрать полный логотип</button></div>
          <div class="space-y-2"><label class="field">Компактный знак (необязательно)<input type="file" accept="image/*,.svg" :disabled="uploadingLogo" @change="uploadLogo($event, true)" /></label><button v-if="draft.site.compact_logo_asset_id" type="button" class="text-sm text-brand-700" @click="clearLogo(true)">Убрать компактный знак</button></div>
          <label class="field">Название сайта<input v-model="draft.site.display_name" /></label><label class="field">Город<input v-model="draft.site.city" /></label><label class="field">Телефон<input v-model="draft.site.phone" type="tel" /></label><label class="field">Публичный email для связи<input v-model="draft.site.email" type="email" /></label><label class="field sm:col-span-2">Адрес<input v-model="draft.site.address" /></label><label class="field">Часы работы<input v-model="draft.site.work_hours" /></label><label class="field">Ссылка на Telegram поддержки<input v-model="draft.site.support_telegram_url" type="url" placeholder="https://t.me/..." /></label><p class="sm:col-span-2 text-xs text-slate-500">Email показывается посетителям как контакт. Уведомления на него не настраиваются здесь.</p>
        </section>
        <section v-else-if="activeTab === 'services' && draft" class="space-y-4"><div class="grid gap-4 md:grid-cols-2"><article v-for="service in draft.services" :key="service.key" class="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"><div class="flex items-start justify-between gap-3"><h2 class="font-semibold text-slate-950 dark:text-white">{{ serviceLabels[service.key] }}</h2><label class="flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-200"><input v-model="service.enabled" type="checkbox" class="h-5 w-5" />{{ service.enabled ? 'Включена' : 'Выключена' }}</label></div><label class="field mt-4">Название<input v-model="service.title" /></label><label class="field mt-4">Описание<textarea v-model="service.description" rows="3" /></label></article></div><div class="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"><h2 class="font-semibold text-slate-950 dark:text-white">Скопировать стартовый каталог</h2><p class="mt-1 text-sm text-slate-500">Скопируются услуги и тарифы без перезаписи ваших данных.</p><p v-if="cloneLoading" class="mt-3 text-sm text-slate-500">Проверяем шаблон…</p><template v-else-if="clonePreview"><p class="mt-3 text-sm text-slate-600">В шаблоне: {{ clonePreview.source_counts.services }} услуг, {{ clonePreview.source_counts.tariffs }} тарифов.</p><button type="button" class="mt-3 rounded-xl border border-brand-600 px-4 py-2 text-sm font-semibold text-brand-700 disabled:opacity-50" :disabled="!clonePreview.can_clone || cloneBusy || hasChanges" @click="cloneTemplate">{{ cloneBusy ? 'Копируем…' : 'Скопировать каталог' }}</button><p v-if="hasChanges" class="mt-2 text-xs text-slate-500">Сначала сохраните изменения услуг.</p><p v-else-if="!clonePreview.can_clone" class="mt-2 text-xs text-slate-500">Копирование недоступно: локальный каталог уже существует или шаблон не готов.</p></template></div><div class="flex flex-wrap gap-3 text-sm font-semibold text-brand-700"><a href="/manager/tariffs">Тарифы смет</a><a href="/manager/installation-rates">Публичные расценки</a></div></section>
        <section v-else class="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"><h2 class="font-['Space_Grotesk'] text-xl font-bold text-slate-950 dark:text-white">Сотрудники</h2><p class="mt-2 max-w-2xl text-sm leading-6 text-slate-500">Добавляйте сотрудников и назначайте роли. Роль определяет, какие разделы и действия доступны в вашей компании.</p><a href="/manager/staff" class="mt-4 inline-flex rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white">Открыть сотрудников</a><p class="mt-5 text-xs text-slate-500">Партнёрские приглашения в бот сотрудников пока недоступны. Ссылка Telegram поддержки на вкладке «Сайт» служит для связи с клиентами и не открывает доступ сотрудникам.</p></section>
      </template>
    </div>
    <div v-if="message" class="fixed bottom-6 right-6 z-[100] max-w-md rounded-xl px-5 py-3 text-sm font-semibold text-white shadow-2xl" :class="messageType === 'success' ? 'bg-emerald-600' : 'bg-red-600'">{{ message }}</div>
  </main>
</template>

<style scoped>
.field { @apply grid gap-1.5 text-sm font-semibold text-slate-700 dark:text-slate-200; }
.field input, .field textarea { @apply w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 outline-none ring-brand-500 focus:ring-2 dark:border-slate-700 dark:bg-slate-950 dark:text-white; }
</style>
