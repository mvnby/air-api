<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import {
  ManagerDocumentSystemService,
  type DocumentLegalEntityItem,
  type DocumentLegalEntityUpdatePayload,
  type DocumentNumberPolicyItem,
  type DocumentNumberPolicyPayload,
  type DocumentPdfRuntimeStatus,
} from '../client';
import { getApiErrorMessage } from '../utils/api-errors';
import DocumentLegalEntitiesPanel from '../features/documents/settings/DocumentLegalEntitiesPanel.vue';
import DocumentNumberPoliciesPanel from '../features/documents/settings/DocumentNumberPoliciesPanel.vue';
import NativeTemplateLibrary from '../features/documents/settings/NativeTemplateLibrary.vue';
import '../features/documents/settings/documents-settings.css';

const legalEntities = ref<DocumentLegalEntityItem[]>([]);
const selectedLegalEntityId = ref<number | null>(null);
const policies = ref<DocumentNumberPolicyItem[]>([]);
const runtime = ref<DocumentPdfRuntimeStatus | null>(null);
const loadingEntities = ref(false);
const loadingPolicies = ref(false);
const savingEntity = ref(false);
const savingPolicyType = ref<string | null>(null);
const activeSettingsTab = ref<'templates' | 'requisites' | 'numbering'>('templates');
const toast = ref('');
const toastType = ref<'success' | 'error'>('success');
let toastTimer: ReturnType<typeof window.setTimeout> | null = null;

const selectedEntity = computed(() => legalEntities.value.find((item) => item.id === selectedLegalEntityId.value) || null);
const runtimeLabel = computed(() => {
  if (!runtime.value) return 'Проверяем PDF…';
  return runtime.value.available ? 'PDF доступен' : 'PDF недоступен';
});
const settingsTabs = [
  { id: 'templates', label: 'Шаблоны', icon: 'description' },
  { id: 'requisites', label: 'Реквизиты', icon: 'business' },
  { id: 'numbering', label: 'Нумерация', icon: 'tag' },
] as const;

const selectSettingsTab = (tab: typeof activeSettingsTab.value) => {
  activeSettingsTab.value = tab;
};
const selectSettingsTabFromKey = async (event: KeyboardEvent) => {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
  event.preventDefault();
  const currentIndex = settingsTabs.findIndex((tab) => tab.id === activeSettingsTab.value);
  const nextIndex = event.key === 'Home' ? 0
    : event.key === 'End' ? settingsTabs.length - 1
      : (currentIndex + (event.key === 'ArrowRight' ? 1 : -1) + settingsTabs.length) % settingsTabs.length;
  const tab = settingsTabs[nextIndex]!;
  selectSettingsTab(tab.id);
  await nextTick();
  document.getElementById(`documents-settings-tab-${tab.id}`)?.focus();
};

const notify = (message: string, type: 'success' | 'error' = 'success') => {
  toast.value = message;
  toastType.value = type;
  if (toastTimer) window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => { toast.value = ''; }, 4500);
};

const loadEntities = async (preferId?: number) => {
  loadingEntities.value = true;
  try {
    legalEntities.value = (await ManagerDocumentSystemService.listManagerDocumentLegalEntities()).items;
    const preferred = preferId || selectedLegalEntityId.value;
    selectedLegalEntityId.value = legalEntities.value.some((item) => item.id === preferred)
      ? preferred
      : legalEntities.value.find((item) => item.is_default)?.id || legalEntities.value[0]?.id || null;
  } catch (error) {
    notify(`Не удалось загрузить продавцов: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    loadingEntities.value = false;
  }
};

const loadPolicies = async () => {
  if (!selectedLegalEntityId.value) {
    policies.value = [];
    return;
  }
  loadingPolicies.value = true;
  try {
    policies.value = (await ManagerDocumentSystemService.listManagerDocumentNumberPolicies(selectedLegalEntityId.value)).items;
  } catch (error) {
    notify(`Не удалось загрузить нумерацию: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    loadingPolicies.value = false;
  }
};

const loadRuntime = async () => {
  try {
    runtime.value = await ManagerDocumentSystemService.getManagerDocumentPdfRuntime();
  } catch (error) {
    runtime.value = { available: false, provider: 'unknown', detail: getApiErrorMessage(error) };
  }
};

onMounted(() => void Promise.all([loadEntities(), loadRuntime()]));
watch(selectedLegalEntityId, () => void loadPolicies());

const createEntity = async (displayName: string) => {
  savingEntity.value = true;
  try {
    const entityType = /^(ип\b|индивидуальный предприниматель)/i.test(displayName.trim())
      ? 'individual_entrepreneur'
      : 'organization';
    const created = await ManagerDocumentSystemService.createManagerDocumentLegalEntity({
      display_name: displayName,
      entity_type: entityType,
    });
    await loadEntities(created.id);
    notify('Продавец добавлен');
  } catch (error) {
    notify(`Не удалось добавить продавца: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    savingEntity.value = false;
  }
};

const updateEntity = async (id: number, changes: DocumentLegalEntityUpdatePayload) => {
  savingEntity.value = true;
  try {
    await ManagerDocumentSystemService.patchManagerDocumentLegalEntity(id, changes);
    await loadEntities(id);
    notify('Реквизиты сохранены');
  } catch (error) {
    notify(`Не удалось сохранить: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    savingEntity.value = false;
  }
};

const savePolicy = async (documentType: string, payload: DocumentNumberPolicyPayload) => {
  if (!selectedLegalEntityId.value) return;
  savingPolicyType.value = documentType;
  try {
    await ManagerDocumentSystemService.upsertManagerDocumentNumberPolicy(selectedLegalEntityId.value, documentType, payload);
    await loadPolicies();
    notify('Правило нумерации сохранено');
  } catch (error) {
    notify(`Не удалось сохранить нумерацию: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    savingPolicyType.value = null;
  }
};
</script>

<template>
  <main class="min-h-full bg-slate-50 p-4 dark:bg-slate-950 sm:p-6 lg:p-8">
    <div class="mx-auto max-w-7xl space-y-6">
      <header class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 class="font-['Space_Grotesk'] text-3xl font-bold text-slate-950 dark:text-white">Шаблоны и реквизиты</h1>
          <p class="mt-2 max-w-3xl text-sm leading-6 text-slate-500">Настройте документы для организации: шаблоны, реквизиты и нумерацию.</p>
        </div>
        <div class="inline-flex w-fit items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold" :class="runtime?.available ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-amber-200 bg-amber-50 text-amber-900'" :title="runtime?.available ? undefined : runtime?.detail || undefined">
          <span class="material-icons-round text-[16px]" aria-hidden="true">{{ runtime?.available ? 'check_circle' : 'info' }}</span>
          {{ runtimeLabel }}
          <span v-if="runtime && !runtime.available && runtime.detail" class="font-normal">· {{ runtime.detail }}</span>
        </div>
      </header>

      <div class="flex flex-col gap-3 rounded-xl border border-brand-200 bg-brand-50 px-4 py-3 text-sm text-brand-900 dark:border-brand-900 dark:bg-brand-950/30 dark:text-brand-200 sm:flex-row sm:items-center sm:justify-between">
        <label v-if="legalEntities.length" class="flex min-w-0 items-center gap-2 font-semibold">
          <span class="shrink-0">Организация / ИП</span>
          <select v-model="selectedLegalEntityId" class="min-w-0 max-w-full rounded-lg border border-brand-200 bg-white px-2 py-1.5 text-sm font-semibold text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/15 dark:border-brand-800 dark:bg-slate-900 dark:text-white" aria-label="Организация или ИП для настроек документов">
            <option v-for="entity in legalEntities" :key="entity.id" :value="entity.id">{{ entity.display_name }}</option>
          </select>
        </label>
        <span v-else>Сначала добавьте организацию или ИП, чтобы настроить документы.</span>
        <span v-if="selectedEntity" class="text-xs text-brand-800/80 dark:text-brand-200/80">{{ selectedEntity.unp ? `УНП ${selectedEntity.unp}` : 'УНП пока не указан' }}</span>
        <button v-else class="settings-button-secondary" type="button" @click="selectSettingsTab('requisites')">Добавить продавца</button>
      </div>

      <div class="grid grid-cols-3 border-b border-slate-200 dark:border-slate-700 sm:flex" role="tablist" aria-label="Настройки документов">
        <button
          v-for="tab in settingsTabs"
          :id="`documents-settings-tab-${tab.id}`"
          :key="tab.id"
          class="inline-flex h-11 items-center justify-center gap-2 border-b-2 px-1.5 text-sm font-semibold transition focus:outline-none focus:ring-2 focus:ring-brand-500/20 sm:px-3"
          :class="activeSettingsTab === tab.id ? 'border-brand-600 text-brand-700 dark:text-brand-300' : 'border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'"
          type="button"
          role="tab"
          :aria-selected="activeSettingsTab === tab.id"
          :aria-controls="`documents-settings-panel-${tab.id}`"
          :tabindex="activeSettingsTab === tab.id ? 0 : -1"
          @click="selectSettingsTab(tab.id)"
          @keydown="selectSettingsTabFromKey"
        >
          <span class="material-icons-round hidden text-[18px] min-[420px]:block" aria-hidden="true">{{ tab.icon }}</span>
          {{ tab.label }}
        </button>
      </div>

      <section id="documents-settings-panel-templates" role="tabpanel" aria-labelledby="documents-settings-tab-templates" v-show="activeSettingsTab === 'templates'">
        <NativeTemplateLibrary :legal-entity-id="selectedLegalEntityId" @toast="notify($event.message, $event.type)" />
      </section>
      <section id="documents-settings-panel-requisites" role="tabpanel" aria-labelledby="documents-settings-tab-requisites" v-show="activeSettingsTab === 'requisites'">
        <DocumentLegalEntitiesPanel
          :items="legalEntities"
          :selected-id="selectedLegalEntityId"
          :loading="loadingEntities"
          :saving="savingEntity"
          @select="selectedLegalEntityId = $event"
          @create="createEntity"
          @update="updateEntity"
        />
      </section>
      <section id="documents-settings-panel-numbering" role="tabpanel" aria-labelledby="documents-settings-tab-numbering" v-show="activeSettingsTab === 'numbering'">
        <DocumentNumberPoliciesPanel
          :legal-entity-id="selectedLegalEntityId"
          :items="policies"
          :loading="loadingPolicies"
          :saving-type="savingPolicyType"
          @save="savePolicy"
        />
      </section>
    </div>

    <Transition name="fade">
      <div v-if="toast" class="fixed bottom-6 right-6 z-[100] max-w-md rounded-xl px-5 py-3 text-sm font-semibold text-white shadow-2xl" :class="toastType === 'success' ? 'bg-emerald-600' : 'bg-red-600'">{{ toast }}</div>
    </Transition>
  </main>
</template>
