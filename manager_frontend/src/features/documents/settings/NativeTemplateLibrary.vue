<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import {
  ManagerDocumentSystemService,
  OpenAPI,
  type NativeDocumentTemplateItem,
  type NativePlaceholderDescriptorItem,
  type NativePlaceholderCatalogResponse,
  type NativeTemplateVersionItem,
} from '../../../client';
import { getApiErrorMessage } from '../../../utils/api-errors';
import { NATIVE_DOCUMENT_TYPES, documentTypeName } from '../model/native-document-options';

const props = defineProps<{ legalEntityId: number | null }>();
const emit = defineEmits<{ toast: [payload: { message: string; type: 'success' | 'error' }] }>();

const documentType = ref('contract');
const templates = ref<NativeDocumentTemplateItem[]>([]);
const selectedTemplateId = ref<number | null>(null);
const versions = ref<NativeTemplateVersionItem[]>([]);
const catalog = ref<NativePlaceholderCatalogResponse | null>(null);
const templateName = ref('');
const templateDescription = ref('');
const changeNote = ref('');
const uploadFile = ref<File | null>(null);
const uploadInput = ref<HTMLInputElement | null>(null);
const loading = ref(false);
const saving = ref(false);
const activatingId = ref<number | null>(null);
const downloadingId = ref<number | null>(null);
let loadId = 0;

const selectedTemplate = computed(() => templates.value.find((item) => item.id === selectedTemplateId.value) || null);
const groupedFields = computed(() => {
  const groups = new Map<string, NativePlaceholderDescriptorItem[]>();
  for (const item of catalog.value?.fields || []) {
    const items = groups.get(item.group) || [];
    groups.set(item.group, [...items, item]);
  }
  return [...groups.entries()];
});

const notify = (message: string, type: 'success' | 'error' = 'success') => emit('toast', { message, type });
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
  if (!legalEntityId || !templateId) {
    versions.value = [];
    return;
  }
  try {
    versions.value = (await ManagerDocumentSystemService.listManagerNativeTemplateVersions(templateId, legalEntityId)).items;
  } catch (error) {
    notify(`Не удалось загрузить версии: ${getApiErrorMessage(error)}`, 'error');
  }
};

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
  void Promise.all([loadTemplates(), loadCatalog()]);
}, { immediate: true });
watch(selectedTemplateId, () => void loadVersions());

const createTemplate = async () => {
  if (!props.legalEntityId || !templateName.value.trim()) return;
  saving.value = true;
  try {
    const created = await ManagerDocumentSystemService.createManagerNativeDocumentTemplate({
      legal_entity_id: props.legalEntityId,
      name: templateName.value.trim(),
      doc_type: documentType.value,
      description: templateDescription.value.trim() || null,
    });
    templateName.value = '';
    templateDescription.value = '';
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
  downloadingId.value = version.id;
  try {
    const query = new URLSearchParams({ legal_entity_id: String(props.legalEntityId) });
    const response = await fetch(
      `${OpenAPI.BASE}/api/manager/document-system/templates/${selectedTemplateId.value}/versions/${version.id}/source?${query}`,
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
</script>

<template>
  <section class="settings-card">
    <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
      <div>
        <h2 class="settings-title">DOCX-шаблоны</h2>
        <p class="settings-help">Меняйте Word-файл как обычно. CRM сама найдёт <code v-text="'{{ seller.legal_name }}'" /> и другие поля, проверит их и создаст новую неизменяемую версию.</p>
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
          >{{ template.name }}</button>
        </div>

        <form v-if="selectedTemplate" class="rounded-xl bg-slate-50 p-4 dark:bg-slate-800/70" @submit.prevent="uploadVersion">
          <h3 class="font-semibold text-slate-900 dark:text-white">Новая версия · {{ selectedTemplate.name }}</h3>
          <div class="mt-3 grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-end">
            <label class="settings-field"><span>DOCX до 5 МБ</span><input ref="uploadInput" class="settings-input py-2" type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" @change="selectUploadFile" /></label>
            <label class="settings-field"><span>Что изменилось</span><input v-model="changeNote" class="settings-input" placeholder="Добавлен пунк 4.3" /></label>
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
                <button v-if="version.status !== 'active'" class="settings-button-secondary" type="button" :disabled="activatingId === version.id" @click="activate(version.id)">Сделать активной</button>
              </div>
            </div>
            <div v-if="versionFields(version).length" class="mt-3 flex flex-wrap gap-1.5">
              <code v-for="field in versionFields(version)" :key="String(field)" class="rounded bg-slate-100 px-2 py-1 text-[11px] text-slate-700 dark:bg-slate-800 dark:text-slate-300" v-text="'{{ ' + field + ' }}'" />
            </div>
          </article>
          <p v-if="selectedTemplate && !versions.length && !loading" class="text-sm text-amber-700 dark:text-amber-300">У шаблона ещё нет DOCX-версий.</p>
        </div>
      </div>

      <aside class="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
        <h3 class="font-semibold text-slate-900 dark:text-white">Каталог плейсхолдеров</h3>
        <p class="mt-1 text-xs text-slate-500">Вставляйте синтаксис в Word обычным текстом. Для таблицы добавьте строку с <code v-text="'{{ lines }}'" />.</p>
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
        </div>
      </aside>
    </div>
    <p v-else class="mt-5 text-sm text-slate-500">Шаблоны привязаны к юрлицу. Сначала создайте его выше.</p>
  </section>
</template>
