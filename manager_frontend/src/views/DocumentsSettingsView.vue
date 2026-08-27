<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
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
const toast = ref('');
const toastType = ref<'success' | 'error'>('success');
let toastTimer: ReturnType<typeof window.setTimeout> | null = null;

const selectedEntity = computed(() => legalEntities.value.find((item) => item.id === selectedLegalEntityId.value) || null);

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
          <p class="text-xs font-bold uppercase tracking-[0.18em] text-teal-600">Документный контур</p>
          <h1 class="mt-1 font-['Space_Grotesk'] text-3xl font-bold text-slate-950 dark:text-white">Документы внутри CRM</h1>
          <p class="mt-2 max-w-3xl text-sm leading-6 text-slate-500">Нативная генерация DOCX/PDF и версии шаблонов. Google Docs остаётся доступным в заказе как отдельный провайдер.</p>
        </div>
        <div class="rounded-xl border px-4 py-3 text-sm" :class="runtime?.available ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-amber-200 bg-amber-50 text-amber-900'">
          <div class="font-bold">PDF: {{ runtime?.available ? 'готов' : 'недоступен' }}</div>
          <div class="mt-0.5 max-w-sm text-xs opacity-80">{{ runtime?.detail || 'Проверяем runtime…' }}</div>
        </div>
      </header>

      <div v-if="selectedEntity" class="rounded-xl border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-900 dark:border-teal-900 dark:bg-teal-950/30 dark:text-teal-200">
        Сейчас настраиваем: <strong>{{ selectedEntity.display_name }}</strong>
      </div>

      <DocumentLegalEntitiesPanel
        :items="legalEntities"
        :selected-id="selectedLegalEntityId"
        :loading="loadingEntities"
        :saving="savingEntity"
        @select="selectedLegalEntityId = $event"
        @create="createEntity"
        @update="updateEntity"
      />
      <DocumentNumberPoliciesPanel
        :legal-entity-id="selectedLegalEntityId"
        :items="policies"
        :loading="loadingPolicies"
        :saving-type="savingPolicyType"
        @save="savePolicy"
      />
      <NativeTemplateLibrary :legal-entity-id="selectedLegalEntityId" @toast="notify($event.message, $event.type)" />
    </div>

    <Transition name="fade">
      <div v-if="toast" class="fixed bottom-6 right-6 z-[100] max-w-md rounded-xl px-5 py-3 text-sm font-semibold text-white shadow-2xl" :class="toastType === 'success' ? 'bg-teal-600' : 'bg-red-600'">{{ toast }}</div>
    </Transition>
  </main>
</template>
