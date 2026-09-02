<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import {
  ManagerDocumentSystemService,
  OpenAPI,
  type NativeDocumentTemplateItem,
  type NativePlaceholderConditionItem,
  type NativePlaceholderDescriptorItem,
  type NativePlaceholderCatalogResponse,
  type NativeTemplateVersionItem,
} from '../../../client';
import { getApiErrorMessage } from '../../../utils/api-errors';
import { NATIVE_DOCUMENT_TYPES, documentTypeName } from '../model/native-document-options';
import { CONTRACT_SCENARIOS } from '../model/business-document-terms';
import GoogleDocumentEditorActions from '../components/GoogleDocumentEditorActions.vue';
import { useGoogleDocumentEditor } from '../composables/use-google-document-editor';
import type { GoogleDocumentEditTarget } from '../integrations/google-document-editor-api';

const props = defineProps<{ legalEntityId: number | null }>();
const emit = defineEmits<{ toast: [payload: { message: string; type: 'success' | 'error' }] }>();

const documentType = ref('contract');
const templates = ref<NativeDocumentTemplateItem[]>([]);
const selectedTemplateId = ref<number | null>(null);
const versions = ref<NativeTemplateVersionItem[]>([]);
const catalog = ref<NativePlaceholderCatalogResponse | null>(null);
const templateName = ref('');
const templateDescription = ref('');
const templateContractScenario = ref<string>('');
const templateBusinessRole = ref<string>('');
const metadataName = ref('');
const metadataDescription = ref('');
const metadataContractScenario = ref<string>('');
const metadataBusinessRole = ref<string>('');
const changeNote = ref('');
const uploadFile = ref<File | null>(null);
const uploadInput = ref<HTMLInputElement | null>(null);
const loading = ref(false);
const saving = ref(false);
const activatingId = ref<number | null>(null);
const downloadingId = ref<number | null>(null);
let loadId = 0;
let versionLoadId = 0;

const selectedTemplate = computed(() => templates.value.find((item) => item.id === selectedTemplateId.value) || null);
const groupedFields = computed(() => {
  const groups = new Map<string, NativePlaceholderDescriptorItem[]>();
  for (const item of catalog.value?.fields || []) {
    const items = groups.get(item.group) || [];
    groups.set(item.group, [...items, item]);
  }
  return [...groups.entries()];
});
const groupedConditions = computed(() => {
  const groups = new Map<string, NativePlaceholderConditionItem[]>();
  for (const item of catalog.value?.conditions || []) {
    const items = groups.get(item.group) || [];
    groups.set(item.group, [...items, item]);
  }
  return [...groups.entries()];
});

const notify = (message: string, type: 'success' | 'error' = 'success') => emit('toast', { message, type });
let reloadTemplateVersions: (() => Promise<void>) | null = null;
const googleEditor = useGoogleDocumentEditor({
  notify,
  onSynced: async (target) => {
    if (target.kind === 'template-version') await reloadTemplateVersions?.();
  },
});
const googleTarget = (version: NativeTemplateVersionItem): GoogleDocumentEditTarget | null => {
  if (!props.legalEntityId || !selectedTemplateId.value) return null;
  return {
    kind: 'template-version',
    templateId: selectedTemplateId.value,
    versionId: version.id,
    legalEntityId: props.legalEntityId,
  };
};
const loadGoogleSessions = () => {
  if (!googleEditor.connected.value) return;
  for (const version of versions.value) {
    const target = googleTarget(version);
    if (target) void googleEditor.loadSession(target);
  }
};
const selectUploadFile = (event: Event) => {
  uploadFile.value = (event.target as HTMLInputElement).files?.[0] || null;
};

const loadCatalog = async () => {
  try {
    catalog.value = await ManagerDocumentSystemService.getManagerNativePlaceholderCatalog(documentType.value);
  } catch (error) {
    notify(`Не удалось загрузить каталог полей: ${getApiErrorMessage(error)}`, 'error');
  }
};

const loadVersions = async () => {
  const legalEntityId = props.legalEntityId;
  const templateId = selectedTemplateId.value;
  const requestId = ++versionLoadId;
  if (!legalEntityId || !templateId) {
    versions.value = [];
    return;
  }
  try {
    const response = await ManagerDocumentSystemService.listManagerNativeTemplateVersions(templateId, legalEntityId);
    if (
      requestId !== versionLoadId
      || props.legalEntityId !== legalEntityId
      || selectedTemplateId.value !== templateId
    ) return;
    versions.value = response.items;
    loadGoogleSessions();
  } catch (error) {
    notify(`Не удалось загрузить версии: ${getApiErrorMessage(error)}`, 'error');
  }
};
reloadTemplateVersions = loadVersions;

const loadTemplates = async () => {
  const legalEntityId = props.legalEntityId;
  const requestId = ++loadId;
  if (!legalEntityId) {
    templates.value = [];
    selectedTemplateId.value = null;
    return;
  }
  loading.value = true;
  try {
    const response = await ManagerDocumentSystemService.listManagerNativeDocumentTemplates(legalEntityId, documentType.value);
    if (requestId !== loadId) return;
    templates.value = response.items;
    if (!templates.value.some((item) => item.id === selectedTemplateId.value)) {
      selectedTemplateId.value = templates.value[0]?.id || null;
    }
    await loadVersions();
  } catch (error) {
    notify(`Не удалось загрузить шаблоны: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    if (requestId === loadId) loading.value = false;
  }
};

watch(() => [props.legalEntityId, documentType.value], () => {
  templateContractScenario.value = '';
  templateBusinessRole.value = '';
  void Promise.all([loadTemplates(), loadCatalog()]);
}, { immediate: true });
watch(selectedTemplateId, () => void loadVersions());
watch(googleEditor.connected, (connected) => {
  if (connected) loadGoogleSessions();
});
watch(selectedTemplate, (template) => {
  metadataName.value = template?.name || '';
  metadataDescription.value = template?.description || '';
  metadataContractScenario.value = template?.contract_scenario || '';
  metadataBusinessRole.value = template?.business_role || '';
}, { immediate: true });

const createTemplate = async () => {
  if (!props.legalEntityId || !templateName.value.trim()) return;
  saving.value = true;
  try {
    const created = await ManagerDocumentSystemService.createManagerNativeDocumentTemplate({
      legal_entity_id: props.legalEntityId,
      name: templateName.value.trim(),
      doc_type: documentType.value,
      description: templateDescription.value.trim() || null,
      contract_scenario: documentType.value === 'contract'
        ? templateContractScenario.value || null
        : null,
      business_role: documentType.value === 'invoice'
        ? templateBusinessRole.value || null
        : null,
    });
    templateName.value = '';
    templateDescription.value = '';
    templateContractScenario.value = '';
    templateBusinessRole.value = '';
    await loadTemplates();
    selectedTemplateId.value = created.id;
    notify('Карточка шаблона создана. Теперь загрузите DOCX.');
  } catch (error) {
    notify(`Ошибка создания: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    saving.value = false;
  }
};

const uploadVersion = async () => {
  if (!props.legalEntityId || !selectedTemplateId.value || !uploadFile.value) return;
  saving.value = true;
  try {
    await ManagerDocumentSystemService.uploadManagerNativeTemplateVersion(selectedTemplateId.value, {
      legal_entity_id: props.legalEntityId,
      change_note: changeNote.value.trim() || null,
      file: uploadFile.value,
    });
    uploadFile.value = null;
    if (uploadInput.value) uploadInput.value.value = '';
    changeNote.value = '';
    await loadVersions();
    notify('Версия проверена и сохранена черновиком. Активируйте её после проверки полей.');
  } catch (error) {
    notify(`Шаблон не принят: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    saving.value = false;
  }
};

const saveTemplateMetadata = async () => {
  if (!props.legalEntityId || !selectedTemplate.value || !metadataName.value.trim()) return;
  saving.value = true;
  try {
    const templateId = selectedTemplate.value.id;
    await ManagerDocumentSystemService.updateManagerNativeDocumentTemplate(templateId, {
      legal_entity_id: props.legalEntityId,
      name: metadataName.value.trim(),
      description: metadataDescription.value.trim() || null,
      contract_scenario: documentType.value === 'contract'
        ? metadataContractScenario.value || null
        : null,
      business_role: documentType.value === 'invoice'
        ? metadataBusinessRole.value || null
        : null,
    });
    await loadTemplates();
    selectedTemplateId.value = templateId;
    notify('Карточка шаблона обновлена');
  } catch (error) {
    notify(`Не удалось обновить карточку: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    saving.value = false;
  }
};

const activate = async (versionId: number) => {
  if (!props.legalEntityId || !selectedTemplateId.value) return;
  activatingId.value = versionId;
  try {
    await ManagerDocumentSystemService.activateManagerNativeTemplateVersion(selectedTemplateId.value, versionId, props.legalEntityId);
    await loadVersions();
    notify('Версия шаблона активирована');
  } catch (error) {
    notify(`Не удалось активировать версию: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    activatingId.value = null;
  }
};

const downloadVersion = async (version: NativeTemplateVersionItem) => {
  if (!props.legalEntityId || !selectedTemplateId.value) return;
  const legalEntityId = props.legalEntityId;
  const templateId = selectedTemplateId.value;
  downloadingId.value = version.id;
  try {
    const query = new URLSearchParams({ legal_entity_id: String(legalEntityId) });
    const response = await fetch(
      `${OpenAPI.BASE}/api/manager/document-system/templates/${templateId}/versions/${version.id}/source?${query}`,
      {
        credentials: OpenAPI.WITH_CREDENTIALS ? OpenAPI.CREDENTIALS : 'same-origin',
        headers: { Accept: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' },
      },
    );
    if (!response.ok) throw new Error(`Не удалось скачать DOCX (${response.status})`);
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = url;
    link.download = version.source_filename || `template-v${version.version}.docx`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    notify(getApiErrorMessage(error), 'error');
  } finally {
    downloadingId.value = null;
  }
};

const versionFields = (version: NativeTemplateVersionItem) => (
  Array.isArray(version.placeholder_schema?.fields) ? version.placeholder_schema.fields : []
);
const versionConditions = (version: NativeTemplateVersionItem) => (
  Array.isArray(version.placeholder_schema?.conditions) ? version.placeholder_schema.conditions : []
);
const syncGoogleTemplate = async (version: NativeTemplateVersionItem) => {
  const target = googleTarget(version);
  if (target) await googleEditor.sync(target);
};
const openGoogleTemplate = (version: NativeTemplateVersionItem) => {
  const target = googleTarget(version);
  if (target) void googleEditor.open(target);
};
const googleSession = (version: NativeTemplateVersionItem) => {
  const target = googleTarget(version);
  return target ? googleEditor.getSession(target) : null;
};
const googleBusy = (version: NativeTemplateVersionItem) => {
  const target = googleTarget(version);
  return target ? googleEditor.isBusy(target) : false;
};
</script>

<template>
  <section class="settings-card">
    <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
      <div>
        <h2 class="settings-title">DOCX-шаблоны</h2>
        <p class="settings-help">Меняйте Word-файл как обычно. CRM найдёт поля и безопасные условные секции, проверит их и создаст новую неизменяемую версию.</p>
        <p v-if="googleEditor.connectionState.value === 'connected'" class="mt-1 text-xs font-semibold text-emerald-700 dark:text-emerald-300" data-testid="template-google-connected">
          Google подключён<span v-if="googleEditor.accountLabel.value">: {{ googleEditor.accountLabel.value }}</span>. После возвращения изменения сохраняются в CRM новой версией шаблона.
        </p>
        <p v-else-if="googleEditor.connectionState.value === 'disconnected'" class="mt-1 text-xs text-slate-500" data-testid="template-google-disconnected">
          <template v-if="googleEditor.canConnect.value">Для онлайн-редактирования <button class="font-semibold text-teal-700 underline underline-offset-2" type="button" @click="googleEditor.connect">подключите Google</button>.</template>
          <template v-else>Для онлайн-редактирования обратитесь к владельцу аккаунта.</template>
          Загрузка DOCX вручную останется доступна.
        </p>
      </div>
      <select v-model="documentType" class="settings-input w-full lg:w-72">
        <option v-for="type in NATIVE_DOCUMENT_TYPES" :key="type.value" :value="type.value">{{ type.label }}</option>
      </select>
    </div>

    <div v-if="legalEntityId" class="mt-5 grid gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(300px,.75fr)]">
      <div class="space-y-5">
        <form class="grid gap-3 rounded-xl border border-dashed border-slate-300 p-4 dark:border-slate-700 sm:grid-cols-2" @submit.prevent="createTemplate">
          <label class="settings-field"><span>Название</span><input v-model="templateName" class="settings-input" :placeholder="`Основной: ${documentTypeName(documentType)}`" /></label>
          <label class="settings-field"><span>Заметка</span><input v-model="templateDescription" class="settings-input" placeholder="Для B2B-клиентов" /></label>
          <label v-if="documentType === 'contract'" class="settings-field sm:col-span-2"><span>Сценарий договора</span><select v-model="templateContractScenario" class="settings-input"><option value="">Универсальный шаблон</option><option v-for="scenario in CONTRACT_SCENARIOS" :key="scenario.value" :value="scenario.value">{{ scenario.label }}</option></select></label>
          <label v-if="documentType === 'invoice'" class="settings-field sm:col-span-2"><span>Роль счёта</span><select v-model="templateBusinessRole" class="settings-input"><option value="">Для обеих ролей</option><option value="payment_request">Документ для оплаты</option><option value="offer">Счёт-оферта</option></select></label>
          <button class="settings-button-secondary sm:col-span-2 sm:justify-self-start" type="submit" :disabled="saving || !templateName.trim()">Создать шаблон</button>
        </form>

        <div v-if="templates.length" class="flex flex-wrap gap-2">
          <button
            v-for="template in templates"
            :key="template.id"
            type="button"
            class="rounded-xl border px-3 py-2 text-sm font-semibold"
            :class="template.id === selectedTemplateId ? 'border-teal-500 bg-teal-50 text-teal-900 dark:bg-teal-950/40 dark:text-teal-200' : 'border-slate-200 text-slate-600 dark:border-slate-700 dark:text-slate-300'"
            @click="selectedTemplateId = template.id"
          >
            {{ template.name }}
            <span v-if="template.contract_scenario" class="ml-1 text-[10px] opacity-70">{{ CONTRACT_SCENARIOS.find((item) => item.value === template.contract_scenario)?.label }}</span>
            <span v-if="template.business_role" class="ml-1 text-[10px] opacity-70">{{ template.business_role === 'offer' ? 'счёт-оферта' : 'для оплаты' }}</span>
          </button>
        </div>

        <form v-if="selectedTemplate" class="grid gap-3 rounded-xl border border-slate-200 p-4 dark:border-slate-700 sm:grid-cols-2" data-testid="native-template-metadata" @submit.prevent="saveTemplateMetadata">
          <h3 class="font-semibold text-slate-900 dark:text-white sm:col-span-2">Карточка шаблона</h3>
          <label class="settings-field"><span>Название</span><input v-model="metadataName" class="settings-input" data-testid="native-template-metadata-name" /></label>
          <label class="settings-field"><span>Заметка</span><input v-model="metadataDescription" class="settings-input" data-testid="native-template-metadata-description" /></label>
          <label v-if="documentType === 'contract'" class="settings-field sm:col-span-2"><span>Сценарий договора</span><select v-model="metadataContractScenario" class="settings-input" data-testid="native-template-metadata-contract-scenario"><option value="">Универсальный шаблон</option><option v-for="scenario in CONTRACT_SCENARIOS" :key="scenario.value" :value="scenario.value">{{ scenario.label }}</option></select></label>
          <label v-if="documentType === 'invoice'" class="settings-field sm:col-span-2"><span>Роль счёта</span><select v-model="metadataBusinessRole" class="settings-input"><option value="">Для обеих ролей</option><option value="payment_request">Документ для оплаты</option><option value="offer">Счёт-оферта</option></select></label>
          <button class="settings-button-secondary sm:col-span-2 sm:justify-self-start" data-testid="native-template-metadata-save" type="submit" :disabled="saving || !metadataName.trim()">Сохранить карточку</button>
        </form>

        <form v-if="selectedTemplate" class="rounded-xl bg-slate-50 p-4 dark:bg-slate-800/70" @submit.prevent="uploadVersion">
          <h3 class="font-semibold text-slate-900 dark:text-white">Новая версия · {{ selectedTemplate.name }}</h3>
          <div class="mt-3 grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-end">
            <label class="settings-field"><span>DOCX до 5 МБ</span><input ref="uploadInput" class="settings-input py-2" type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" @change="selectUploadFile" /></label>
            <label class="settings-field"><span>Что изменилось</span><input v-model="changeNote" class="settings-input" placeholder="Добавлен пункт 4.3" /></label>
            <button class="settings-button-primary" type="submit" :disabled="saving || !uploadFile">Загрузить</button>
          </div>
        </form>

        <div class="space-y-3">
          <article v-for="version in versions" :key="version.id" class="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <span class="font-bold text-slate-900 dark:text-white">Версия {{ version.version }}</span>
                <span class="ml-2 rounded-full px-2 py-0.5 text-xs font-bold" :class="version.status === 'active' ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'">{{ version.status === 'active' ? 'Активна' : 'Черновик' }}</span>
                <p class="mt-1 text-xs text-slate-500">{{ version.source_filename }}<span v-if="version.change_note"> · {{ version.change_note }}</span></p>
              </div>
              <div class="flex flex-wrap gap-2">
                <button class="settings-button-secondary" type="button" :disabled="downloadingId === version.id" @click="downloadVersion(version)">Скачать DOCX</button>
                <GoogleDocumentEditorActions
                  v-if="googleEditor.connected.value"
                  :session="googleSession(version)"
                  :busy="googleBusy(version)"
                  :editable="googleSession(version)?.can_edit !== false"
                  @open="openGoogleTemplate(version)"
                  @sync="syncGoogleTemplate(version)"
                />
                <button v-if="version.status !== 'active'" class="settings-button-secondary" type="button" :disabled="activatingId === version.id" @click="activate(version.id)">Сделать активной</button>
              </div>
            </div>
            <div v-if="versionFields(version).length" class="mt-3 flex flex-wrap gap-1.5">
              <code v-for="field in versionFields(version)" :key="String(field)" class="rounded bg-slate-100 px-2 py-1 text-[11px] text-slate-700 dark:bg-slate-800 dark:text-slate-300" v-text="'{{ ' + field + ' }}'" />
            </div>
            <div v-if="versionConditions(version).length" class="mt-2 flex flex-wrap gap-1.5">
              <code v-for="condition in versionConditions(version)" :key="String(condition)" class="rounded bg-violet-100 px-2 py-1 text-[11px] text-violet-800 dark:bg-violet-950/50 dark:text-violet-200" v-text="'{{#if ' + condition + '}} … {{/if ' + condition + '}}'" />
            </div>
          </article>
          <p v-if="selectedTemplate && !versions.length && !loading" class="text-sm text-amber-700 dark:text-amber-300">У шаблона ещё нет DOCX-версий.</p>
        </div>
      </div>

      <aside class="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
        <h3 class="font-semibold text-slate-900 dark:text-white">Каталог плейсхолдеров</h3>
        <p class="mt-1 text-xs text-slate-500">Вставляйте синтаксис в Word обычным текстом. Условные маркеры ставьте отдельными абзацами или строками таблицы.</p>
        <div class="mt-4 max-h-[560px] space-y-4 overflow-auto pr-1">
          <div v-for="[group, fields] in groupedFields" :key="group">
            <h4 class="text-xs font-bold uppercase tracking-wide text-slate-400">{{ group }}</h4>
            <div class="mt-2 space-y-1.5">
              <div v-for="field in fields" :key="field.name" class="rounded-lg bg-slate-50 p-2 dark:bg-slate-800">
                <code class="text-xs font-semibold text-teal-700 dark:text-teal-300">{{ field.syntax }}</code>
                <p class="mt-0.5 text-xs text-slate-500">{{ field.label }}</p>
              </div>
            </div>
          </div>
          <div v-for="table in catalog?.tables || []" :key="table.name">
            <h4 class="text-xs font-bold uppercase tracking-wide text-slate-400">Таблица · {{ table.anchor_syntax }}</h4>
            <div class="mt-2 flex flex-wrap gap-1.5"><code v-for="field in table.row_fields" :key="field.name" class="rounded bg-slate-100 px-2 py-1 text-[11px] dark:bg-slate-800">{{ field.syntax }}</code></div>
          </div>
          <div v-for="[group, conditions] in groupedConditions" :key="group">
            <h4 class="text-xs font-bold uppercase tracking-wide text-slate-400">{{ group }}</h4>
            <div class="mt-2 space-y-2">
              <div v-for="condition in conditions" :key="condition.name" class="rounded-lg bg-violet-50 p-2 dark:bg-violet-950/30">
                <code class="block text-xs font-semibold text-violet-800 dark:text-violet-200">{{ condition.start_syntax }}</code>
                <code class="block text-xs font-semibold text-violet-800 dark:text-violet-200">{{ condition.end_syntax }}</code>
                <p class="mt-1 text-xs text-slate-500">{{ condition.label }}. Маркеры ставятся отдельными абзацами или строками таблицы.</p>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </div>
    <p v-else class="mt-5 text-sm text-slate-500">Шаблоны привязаны к организации или ИП. Сначала добавьте продавца выше.</p>
  </section>
</template>
