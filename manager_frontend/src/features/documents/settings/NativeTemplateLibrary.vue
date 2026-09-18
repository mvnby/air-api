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
import {
  BUSINESS_NATIVE_DOCUMENT_TYPES,
  CONSUMER_NATIVE_DOCUMENT_TYPES,
  documentTypeName,
} from '../model/native-document-options';
import { CONTRACT_SCENARIOS } from '../model/business-document-terms';
import { DOCUMENT_ROLE_OPTIONS } from '../model/document-constants';
import type { DocumentRoleType } from '../model/document-types';
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
const templateDocumentRoleType = ref<DocumentRoleType | ''>('');
const metadataName = ref('');
const metadataDescription = ref('');
const metadataContractScenario = ref<string>('');
const metadataBusinessRole = ref<string>('');
const metadataDocumentRoleType = ref<DocumentRoleType | ''>('');
const changeNote = ref('');
const uploadFile = ref<File | null>(null);
const uploadInput = ref<HTMLInputElement | null>(null);
const loading = ref(false);
const saving = ref(false);
const activatingId = ref<number | null>(null);
const downloadingId = ref<number | null>(null);
const showCreateTemplate = ref(false);
const showVersionHistory = ref(false);
const showPlaceholderCatalog = ref(false);
let loadId = 0;
let versionLoadId = 0;

const selectedTemplate = computed(() => templates.value.find((item) => item.id === selectedTemplateId.value) || null);
const activeVersion = computed(() => versions.value.find((item) => item.status === 'active') || null);
const supportsDocumentRoleType = computed(() => ['offer', 'invoice', 'contract', 'act'].includes(documentType.value));
const documentTypeGroups = [
  { label: 'Для бизнеса', items: BUSINESS_NATIVE_DOCUMENT_TYPES },
  { label: 'Для частных клиентов', items: CONSUMER_NATIVE_DOCUMENT_TYPES },
];
const documentTypeIcon = (type: string) => ({
  offer: 'description',
  invoice: 'receipt_long',
  contract: 'handshake',
  act: 'fact_check',
  tn2: 'inventory_2',
  ttn1: 'local_shipping',
  b2c_supply_installation_act: 'construction',
  b2c_customer_equipment_installation_act: 'build',
  b2c_maintenance_repair_act: 'handyman',
  b2c_route_laying_act: 'route',
}[type] || 'description');
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
  templateDocumentRoleType.value = '';
  showCreateTemplate.value = false;
  showVersionHistory.value = false;
  showPlaceholderCatalog.value = false;
  void Promise.all([loadTemplates(), loadCatalog()]);
}, { immediate: true });
watch(selectedTemplateId, () => {
  showVersionHistory.value = false;
  void loadVersions();
});
watch(googleEditor.connected, (connected) => {
  if (connected) loadGoogleSessions();
});
watch(selectedTemplate, (template) => {
  metadataName.value = template?.name || '';
  metadataDescription.value = template?.description || '';
  metadataContractScenario.value = template?.contract_scenario || '';
  metadataBusinessRole.value = template?.business_role || '';
  metadataDocumentRoleType.value = template?.document_role_type || '';
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
      document_role_type: supportsDocumentRoleType.value ? templateDocumentRoleType.value || null : null,
    });
    templateName.value = '';
    templateDescription.value = '';
    templateContractScenario.value = '';
    templateBusinessRole.value = '';
    templateDocumentRoleType.value = '';
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
      document_role_type: supportsDocumentRoleType.value
        ? metadataDocumentRoleType.value || null
        : selectedTemplate.value.document_role_type || null,
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
    <header class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h2 class="settings-title">Шаблоны документов</h2>
        <p class="settings-help">Выберите вид документа и нужный шаблон.</p>
        <p v-if="googleEditor.connectionState.value === 'connected'" class="mt-1 text-xs font-semibold text-emerald-700 dark:text-emerald-300" data-testid="template-google-connected">
          Google подключён<span v-if="googleEditor.accountLabel.value">: {{ googleEditor.accountLabel.value }}</span>. Изменения вернутся в CRM новой версией.
        </p>
        <p v-else-if="googleEditor.connectionState.value === 'disconnected'" class="mt-1 text-xs text-slate-500" data-testid="template-google-disconnected">
          <template v-if="googleEditor.canConnect.value">Для онлайн-редактирования <button class="font-semibold text-brand-700 underline underline-offset-2" type="button" @click="googleEditor.connect">подключите Google</button>.</template>
          <template v-else>Для онлайн-редактирования обратитесь к владельцу аккаунта.</template>
        </p>
      </div>
      <button class="settings-button-primary shrink-0" type="button" :aria-expanded="showCreateTemplate" aria-controls="native-template-create" @click="showCreateTemplate = !showCreateTemplate">
        <span class="material-icons-round text-[18px]" aria-hidden="true">add</span>
        Новый шаблон
      </button>
    </header>

    <div v-if="legalEntityId" class="mt-5 space-y-5">
      <nav aria-label="Вид документа" class="space-y-3">
        <div v-for="group in documentTypeGroups" :key="group.label">
          <p class="mb-2 text-xs font-bold uppercase tracking-wide text-slate-400">{{ group.label }}</p>
          <div class="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
            <button
              v-for="type in group.items"
              :key="type.value"
              type="button"
              class="template-library-type-option"
              :class="{ 'template-library-type-option--selected': documentType === type.value }"
              :aria-pressed="documentType === type.value"
              @click="documentType = type.value"
            >
              <span class="material-icons-round text-[20px]" aria-hidden="true">{{ documentTypeIcon(type.value) }}</span>
              <span>{{ type.label }}</span>
            </button>
          </div>
        </div>
      </nav>

      <form v-if="showCreateTemplate" id="native-template-create" class="grid gap-3 border-t border-dashed border-slate-300 pt-5 dark:border-slate-700 sm:grid-cols-2" @submit.prevent="createTemplate">
        <h3 class="font-semibold text-slate-900 dark:text-white sm:col-span-2">Новый шаблон · {{ documentTypeName(documentType) }}</h3>
        <label class="settings-field"><span>Название</span><input v-model="templateName" class="settings-input" :placeholder="`Основной: ${documentTypeName(documentType)}`" /></label>
        <label class="settings-field"><span>Заметка</span><input v-model="templateDescription" class="settings-input" placeholder="Для B2B-клиентов" /></label>
        <label v-if="documentType === 'contract'" class="settings-field sm:col-span-2"><span>Сценарий договора</span><select v-model="templateContractScenario" class="settings-input"><option value="">Универсальный шаблон</option><option v-for="scenario in CONTRACT_SCENARIOS" :key="scenario.value" :value="scenario.value">{{ scenario.label }}</option></select></label>
        <label v-if="documentType === 'invoice'" class="settings-field sm:col-span-2"><span>Роль счёта</span><select v-model="templateBusinessRole" class="settings-input"><option value="">Для обеих ролей</option><option value="payment_request">Документ для оплаты</option><option value="offer">Счёт-оферта</option></select></label>
        <label v-if="supportsDocumentRoleType" class="settings-field"><span>Названия сторон</span><select v-model="templateDocumentRoleType" class="settings-input"><option value="">По тексту шаблона</option><option v-for="option in DOCUMENT_ROLE_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
        <div class="flex gap-2 sm:col-span-2">
          <button class="settings-button-primary" type="submit" :disabled="saving || !templateName.trim()">Создать шаблон</button>
          <button class="settings-button-secondary" type="button" @click="showCreateTemplate = false">Отмена</button>
        </div>
      </form>

      <div class="grid gap-5 lg:grid-cols-[minmax(220px,0.38fr)_minmax(0,1fr)]">
        <section aria-labelledby="template-list-title" class="min-w-0">
          <div class="flex items-baseline justify-between gap-2">
            <h3 id="template-list-title" class="font-semibold text-slate-900 dark:text-white">{{ documentTypeName(documentType) }}</h3>
            <span class="text-xs text-slate-500">{{ templates.length }} {{ templates.length === 1 ? 'шаблон' : 'шаблонов' }}</span>
          </div>
          <div v-if="templates.length" class="mt-3 space-y-2" aria-label="Шаблоны выбранного вида документа">
            <button
              v-for="template in templates"
              :key="template.id"
              type="button"
              class="template-library-template-option"
              :class="{ 'template-library-template-option--selected': template.id === selectedTemplateId }"
              :aria-pressed="template.id === selectedTemplateId"
              @click="selectedTemplateId = template.id"
            >
              <span class="material-icons-round shrink-0 text-[20px]" aria-hidden="true">{{ documentTypeIcon(documentType) }}</span>
              <span class="min-w-0 text-left">
                <span class="block truncate font-semibold">{{ template.name }}</span>
                <span v-if="template.contract_scenario || template.business_role || template.description" class="mt-0.5 block truncate text-xs font-normal opacity-75">
                  {{ template.contract_scenario ? CONTRACT_SCENARIOS.find((item) => item.value === template.contract_scenario)?.label : template.business_role === 'offer' ? 'Счёт-оферта' : template.business_role === 'payment_request' ? 'Для оплаты' : template.description }}
                </span>
              </span>
              <span v-if="template.is_active" class="ml-auto text-[11px] font-bold text-emerald-700 dark:text-emerald-300">Активен</span>
            </button>
          </div>
          <p v-else-if="!loading" class="mt-3 text-sm leading-6 text-slate-500">Для этого вида документа шаблонов ещё нет.</p>
        </section>

        <section v-if="selectedTemplate" class="min-w-0 border-t border-slate-200 pt-5 dark:border-slate-700 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0" aria-labelledby="selected-template-title">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="flex min-w-0 items-center gap-3">
              <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-700 dark:bg-brand-950/40 dark:text-brand-300"><span class="material-icons-round text-[23px]" aria-hidden="true">{{ documentTypeIcon(documentType) }}</span></span>
              <div class="min-w-0">
                <h3 id="selected-template-title" class="truncate font-semibold text-slate-900 dark:text-white">{{ selectedTemplate.name }}</h3>
                <p class="mt-0.5 text-xs text-slate-500">{{ activeVersion ? `Активна версия ${activeVersion.version}` : 'DOCX ещё не загружен' }}</p>
              </div>
            </div>
            <button class="settings-button-secondary" type="button" :aria-expanded="showPlaceholderCatalog" aria-controls="native-placeholder-catalog" @click="showPlaceholderCatalog = !showPlaceholderCatalog">
              <span class="material-icons-round text-[17px]" aria-hidden="true">data_object</span>
              Поля шаблона
              <span class="material-icons-round text-[17px]" aria-hidden="true">{{ showPlaceholderCatalog ? 'expand_less' : 'expand_more' }}</span>
            </button>
          </div>

          <form class="mt-5 grid gap-3 sm:grid-cols-2" data-testid="native-template-metadata" @submit.prevent="saveTemplateMetadata">
            <label class="settings-field"><span>Название</span><input v-model="metadataName" class="settings-input" data-testid="native-template-metadata-name" /></label>
            <label class="settings-field"><span>Заметка</span><input v-model="metadataDescription" class="settings-input" data-testid="native-template-metadata-description" /></label>
            <label v-if="documentType === 'contract'" class="settings-field sm:col-span-2"><span>Сценарий договора</span><select v-model="metadataContractScenario" class="settings-input" data-testid="native-template-metadata-contract-scenario"><option value="">Универсальный шаблон</option><option v-for="scenario in CONTRACT_SCENARIOS" :key="scenario.value" :value="scenario.value">{{ scenario.label }}</option></select></label>
            <label v-if="documentType === 'invoice'" class="settings-field sm:col-span-2"><span>Роль счёта</span><select v-model="metadataBusinessRole" class="settings-input"><option value="">Для обеих ролей</option><option value="payment_request">Документ для оплаты</option><option value="offer">Счёт-оферта</option></select></label>
            <label v-if="supportsDocumentRoleType" class="settings-field"><span>Названия сторон</span><select v-model="metadataDocumentRoleType" class="settings-input" data-testid="native-template-metadata-document-role-type"><option value="">По тексту шаблона</option><option v-for="option in DOCUMENT_ROLE_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
            <button class="settings-button-secondary justify-self-start" data-testid="native-template-metadata-save" type="submit" :disabled="saving || !metadataName.trim()">Сохранить карточку</button>
          </form>

          <form class="mt-5 border-t border-slate-200 pt-5 dark:border-slate-700" @submit.prevent="uploadVersion">
            <h4 class="font-semibold text-slate-900 dark:text-white">Загрузить новую версию</h4>
            <div class="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] xl:items-end">
              <label class="settings-field"><span>DOCX до 5 МБ</span><input ref="uploadInput" class="settings-input py-2" type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" @change="selectUploadFile" /></label>
              <label class="settings-field"><span>Что изменилось</span><input v-model="changeNote" class="settings-input" placeholder="Добавлен пункт 4.3" /></label>
              <button class="settings-button-primary" type="submit" :disabled="saving || !uploadFile">Загрузить</button>
            </div>
          </form>

          <div class="mt-5 border-t border-slate-200 pt-5 dark:border-slate-700">
            <button class="flex w-full items-center justify-between gap-3 text-left font-semibold text-slate-900 dark:text-white" type="button" :aria-expanded="showVersionHistory" aria-controls="native-template-version-history" @click="showVersionHistory = !showVersionHistory">
              <span>История версий <span class="ml-1 text-sm font-normal text-slate-500">{{ versions.length }}</span></span>
              <span class="material-icons-round text-[20px]" aria-hidden="true">{{ showVersionHistory ? 'expand_less' : 'expand_more' }}</span>
            </button>
            <p v-if="!showVersionHistory" class="mt-1 text-xs text-slate-500">Показывается по запросу, чтобы не перегружать библиотеку.</p>
            <div v-if="showVersionHistory" id="native-template-version-history" class="mt-4 space-y-3">
              <article v-for="version in versions" :key="version.id" class="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
                <div class="flex flex-wrap items-start justify-between gap-3">
                  <div class="min-w-0">
                    <div class="flex flex-wrap items-center gap-2"><span class="font-bold text-slate-900 dark:text-white">Версия {{ version.version }}</span><span class="rounded-full px-2 py-0.5 text-xs font-bold" :class="version.status === 'active' ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'">{{ version.status === 'active' ? 'Активна' : 'Черновик' }}</span></div>
                    <p class="mt-1 break-words text-xs text-slate-500">{{ version.source_filename }}<span v-if="version.change_note"> · {{ version.change_note }}</span></p>
                  </div>
                  <div class="flex flex-wrap gap-2">
                    <button class="settings-button-secondary" type="button" :disabled="downloadingId === version.id" @click="downloadVersion(version)">Скачать DOCX</button>
                    <GoogleDocumentEditorActions v-if="googleEditor.connected.value" :session="googleSession(version)" :busy="googleBusy(version)" :editable="googleSession(version)?.can_edit !== false" @open="openGoogleTemplate(version)" @sync="syncGoogleTemplate(version)" />
                    <button v-if="version.status !== 'active'" class="settings-button-secondary" type="button" :disabled="activatingId === version.id" @click="activate(version.id)">Сделать активной</button>
                  </div>
                </div>
                <div v-if="versionFields(version).length" class="mt-3 flex flex-wrap gap-1.5"><code v-for="field in versionFields(version)" :key="String(field)" class="rounded bg-slate-100 px-2 py-1 text-[11px] text-slate-700 dark:bg-slate-800 dark:text-slate-300" v-text="'{{ ' + field + ' }}'" /></div>
                <div v-if="versionConditions(version).length" class="mt-2 flex flex-wrap gap-1.5"><code v-for="condition in versionConditions(version)" :key="String(condition)" class="rounded bg-violet-100 px-2 py-1 text-[11px] text-violet-800 dark:bg-violet-950/50 dark:text-violet-200" v-text="'{{#if ' + condition + '}} … {{/if ' + condition + '}}'" /></div>
              </article>
              <p v-if="!versions.length && !loading" class="text-sm text-amber-700 dark:text-amber-300">У шаблона ещё нет DOCX-версий.</p>
            </div>
          </div>

          <aside v-if="showPlaceholderCatalog" id="native-placeholder-catalog" class="mt-5 border-t border-slate-200 pt-5 dark:border-slate-700">
            <h4 class="font-semibold text-slate-900 dark:text-white">Поля и условия</h4>
            <p class="mt-1 text-xs leading-5 text-slate-500">Вставляйте синтаксис в Word обычным текстом. Условие внутри текста открывайте и закрывайте в одном абзаце.</p>
            <div class="mt-4 max-h-[560px] space-y-4 overflow-auto pr-1">
              <div v-for="[group, fields] in groupedFields" :key="group"><h5 class="text-xs font-bold uppercase tracking-wide text-slate-400">{{ group }}</h5><div class="mt-2 space-y-1.5"><div v-for="field in fields" :key="field.name" class="rounded-lg bg-slate-50 p-2 dark:bg-slate-800"><code class="text-xs font-semibold text-brand-700 dark:text-brand-300">{{ field.syntax }}</code><p class="mt-0.5 text-xs text-slate-500">{{ field.label }}</p></div></div></div>
              <div v-for="table in catalog?.tables || []" :key="table.name"><h5 class="text-xs font-bold uppercase tracking-wide text-slate-400">Таблица · {{ table.anchor_syntax }}</h5><div class="mt-2 flex flex-wrap gap-1.5"><code v-for="field in table.row_fields" :key="field.name" class="rounded bg-slate-100 px-2 py-1 text-[11px] dark:bg-slate-800">{{ field.syntax }}</code></div></div>
              <div v-for="[group, conditions] in groupedConditions" :key="group"><h5 class="text-xs font-bold uppercase tracking-wide text-slate-400">{{ group }}</h5><div class="mt-2 space-y-2"><div v-for="condition in conditions" :key="condition.name" class="rounded-lg bg-violet-50 p-2 dark:bg-violet-950/30"><code class="block text-xs font-semibold text-violet-800 dark:text-violet-200">{{ condition.start_syntax }}</code><code class="block text-xs font-semibold text-violet-800 dark:text-violet-200">{{ condition.end_syntax }}</code><p class="mt-1 text-xs text-slate-500">{{ condition.label }}. Можно использовать внутри одного абзаца или выделять целые абзацы и строки таблицы.</p></div></div></div>
            </div>
          </aside>
        </section>
        <p v-else class="border-t border-slate-200 pt-5 text-sm text-slate-500 dark:border-slate-700 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0">Создайте шаблон, чтобы загрузить в него DOCX и настроить поля.</p>
      </div>
    </div>
    <p v-else class="mt-5 text-sm text-slate-500">Шаблоны привязаны к организации или ИП. Сначала добавьте продавца выше.</p>
  </section>
</template>
