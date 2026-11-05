<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { ManagerDocumentSystemService as Documents, type ManagedDocumentDraftParameters, type NativeTemplateVersionItem } from '../../../client';
import { getApiErrorMessage } from '../../../utils/api-errors';
import { useGoogleDocumentEditor } from '../composables/use-google-document-editor';
import { fetchDraftPreviewWithPage } from '../integrations/native-document-preview';
import { downloadTemplateVersion } from '../integrations/template-download';
import GoogleDocumentEditorActions from './GoogleDocumentEditorActions.vue';

const props = defineProps<{
  legalEntityId: number;
  templateId: number;
  sourceVersionId: number;
  documentType: string;
  draftId?: number;
}>();
const emit = defineEmits<{ close: []; changed: [draftId?: number] }>();
const dialog = ref<HTMLDialogElement | null>(null);
const versions = ref<NativeTemplateVersionItem[]>([]);
const templateName = ref('');
const ready = ref(false);
const source = computed(() => versions.value.find((version) => version.id === props.sourceVersionId));
const activeVersion = computed(() => versions.value.find((version) => version.status === 'active'));
const candidateId = ref<number | null>(null);
const candidate = computed(() => versions.value.find((version) => version.id === candidateId.value));
const availableVersions = computed(() => versions.value.filter((version) =>
  version.status === 'draft' || version.status === 'active' && version.id !== props.sourceVersionId));
const parameters = ref<ManagedDocumentDraftParameters | null>(null);
const replaceCopy = ref(false);
const loading = ref(true);
const saving = ref(false);
const error = ref('');
const feedback = ref('');
const editorLink = ref('');
const applied = ref(false);
const previewUrl = ref('');
const firstPageUrl = ref('');
let mounted = true;
const googleTarget = { kind: 'template-version' as const, legalEntityId: props.legalEntityId, templateId: props.templateId, versionId: props.sourceVersionId };

const selectNewVersion = (version: NativeTemplateVersionItem) => {
  versions.value = [version, ...versions.value.filter((item) => item.id !== version.id)];
  candidateId.value = version.id;
  error.value = '';
};
const editor = useGoogleDocumentEditor({
  notify: (message, type) => {
    if (!mounted) return;
    if (type === 'error') error.value = message;
    else feedback.value = message;
  },
  onPopupBlocked: (url) => { editorLink.value = url; },
  onSynced: (_target, result) => {
    if (mounted && result.newTemplateVersion) selectNewVersion(result.newTemplateVersion);
  },
});
watch(editor.connected, (connected) => { if (connected) void editor.loadSession(googleTarget); }, { immediate: true });
const busy = computed(() => saving.value || editor.isBusy(googleTarget));
const applyToDraft = computed(() => !!props.draftId && (!parameters.value?.has_editable_copy || replaceCopy.value));
const canSave = computed(() => !!candidate.value && !busy.value && !loading.value && !applied.value
  && (candidate.value.status !== 'active' || applyToDraft.value));

onMounted(async () => {
  dialog.value?.showModal();
  try {
    const [definitions, list, draft] = await Promise.all([
      Documents.listManagerNativeDocumentTemplates(props.legalEntityId, props.documentType),
      Documents.listManagerNativeTemplateVersions(props.templateId, props.legalEntityId),
      props.draftId ? Documents.getManagerManagedDocumentDraftParameters(props.draftId) : null,
    ]);
    if (!mounted) return;
    const template = definitions.items.find((item) => item.id === props.templateId);
    if (!template) throw new Error('Шаблон недоступен в выбранной организации.');
    templateName.value = template.name;
    if (!template.is_active) throw new Error('Шаблон отключён. Проверьте его статус в настройках документов.');
    versions.value = list.items;
    if (draft && draft.template_version_id !== props.sourceVersionId) {
      throw new Error('В этом черновике уже применили другую версию. Обновите заказ.');
    }
    parameters.value = draft;
    if (!source.value) throw new Error('Версия шаблона недоступна. Откройте заказ заново.');
    if (activeVersion.value?.id !== props.sourceVersionId) candidateId.value = activeVersion.value?.id || null;
    ready.value = true;
  } catch (failure) {
    error.value = getApiErrorMessage(failure);
  } finally {
    loading.value = false;
  }
});
onBeforeUnmount(() => {
  mounted = false;
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value);
  if (firstPageUrl.value) URL.revokeObjectURL(firstPageUrl.value);
});

const upload = async (event: Event) => {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file || busy.value) return;
  saving.value = true;
  error.value = feedback.value = '';
  try {
    const version = await Documents.uploadManagerNativeTemplateVersion(props.templateId, { legal_entity_id: props.legalEntityId, file });
    if (mounted) selectNewVersion(version);
  } catch (failure) {
    error.value = getApiErrorMessage(failure);
  } finally {
    input.value = '';
    saving.value = false;
  }
};
const download = async () => {
  if (!source.value || busy.value) return;
  saving.value = true;
  try { await downloadTemplateVersion(props.legalEntityId, source.value); }
  catch (failure) { error.value = getApiErrorMessage(failure); }
  finally { saving.value = false; }
};
const loadPreview = async () => {
  if (!props.draftId) return;
  error.value = '';
  try {
    const result = await fetchDraftPreviewWithPage(props.draftId);
    if (!mounted) return;
    previewUrl.value = URL.createObjectURL(result.pdf);
    if (result.firstPage) firstPageUrl.value = URL.createObjectURL(result.firstPage);
  } catch (failure) {
    if (mounted) error.value = `Черновик обновлён. Не удалось загрузить предпросмотр: ${getApiErrorMessage(failure)}`;
  }
};
const save = async () => {
  const chosen = candidate.value;
  if (!canSave.value || !chosen) return;
  saving.value = true;
  error.value = feedback.value = '';
  try {
    if (chosen.status !== 'active') {
      const activated = await Documents.activateManagerNativeTemplateVersion(
        props.templateId, chosen.id, props.legalEntityId, activeVersion.value?.id,
      );
      if (!mounted) return;
      versions.value = versions.value.map((version) => version.id === activated.id ? activated
        : version.status === 'active' ? { ...version, status: 'retired' } : version);
      emit('changed');
    }
    if (props.draftId && applyToDraft.value && parameters.value) {
      await Documents.updateManagerManagedDocumentDraftParameters(props.draftId, {
        expected_revision: parameters.value.revision,
        template_version_id: chosen.id,
        reset_editable_copy: replaceCopy.value,
      });
      if (!mounted) return;
      emit('changed', props.draftId);
      applied.value = true;
      await loadPreview();
    } else {
      dialog.value?.close();
      emit('close');
    }
  } catch (failure) {
    error.value = getApiErrorMessage(failure);
  } finally {
    saving.value = false;
  }
};
const pageUnavailable = () => {
  URL.revokeObjectURL(firstPageUrl.value);
  firstPageUrl.value = '';
};
const close = () => {
  if (busy.value && !applied.value) return;
  dialog.value?.close();
  emit('close');
};
</script>

<template>
  <Teleport to="body">
    <dialog ref="dialog" class="template-editor" :class="{ 'template-editor--preview': applied }" aria-labelledby="order-template-editor-title" @cancel.prevent="close">
      <div class="space-y-4 p-4 sm:p-5">
        <header class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <h2 id="order-template-editor-title" class="text-base font-bold">{{ applied ? 'Предпросмотр черновика' : 'Редактировать шаблон' }}</h2>
            <p class="break-words text-sm text-slate-500">{{ templateName || source?.source_filename }}<template v-if="source && !applied"> · версия {{ source.version }}</template></p>
          </div>
          <button type="button" class="editor-action shrink-0" aria-label="Вернуться к заказу" :disabled="busy && !applied" @click="close">Закрыть</button>
        </header>
        <p v-if="error" role="alert" class="text-sm text-rose-700 dark:text-rose-300">{{ error }}</p>
        <p v-if="feedback && !applied && !candidate" role="status" class="text-sm text-emerald-700 dark:text-emerald-300">{{ feedback }}</p>
        <p v-if="loading" role="status" class="text-sm">Загружаем шаблон…</p>
        <template v-else-if="applied">
          <p v-if="!previewUrl && !error" role="status" class="text-sm">Готовим PDF…</p>
          <template v-if="previewUrl">
            <a :href="previewUrl" target="_blank" rel="noopener" class="editor-action">Открыть весь PDF</a>
            <figure v-if="firstPageUrl" class="space-y-1.5">
              <figcaption class="text-xs font-semibold text-slate-500">Первая страница</figcaption>
              <img :src="firstPageUrl" alt="Первая страница обновлённого черновика" class="block h-auto w-full rounded-lg border border-slate-200" @error="pageUnavailable" />
            </figure>
            <p v-else class="text-sm text-slate-500">Для просмотра откройте файл PDF.</p>
          </template>
          <button v-else-if="error" type="button" class="editor-action" @click="loadPreview">Повторить предпросмотр</button>
        </template>
        <template v-else-if="ready && source">
          <GoogleDocumentEditorActions v-if="editor.connected.value" :session="editor.getSession(googleTarget)"
            :busy="busy" @open="editor.open(googleTarget)" @sync="editor.sync(googleTarget)" />
          <a v-if="editorLink" class="editor-action" :href="editorLink" target="_blank" rel="noopener">Открыть редактор в новой вкладке</a>
          <div class="flex flex-wrap gap-2">
            <button class="editor-action" type="button" :disabled="busy" @click="download">Скачать DOCX</button>
            <label class="editor-action cursor-pointer focus-within:ring-2 focus-within:ring-brand-500">
              Загрузить исправленный DOCX
              <input class="sr-only" type="file" accept=".docx" :disabled="busy" @change="upload" />
            </label>
          </div>
          <label v-if="availableVersions.length > 1 || (availableVersions.length && !candidate)" class="block text-sm font-semibold">
            Применить версию
            <select v-model="candidateId" class="mt-1 block w-full rounded-lg border bg-white p-2 text-sm dark:bg-slate-900" :disabled="busy">
              <option :value="null" disabled>Выберите версию</option>
              <option v-for="version in availableVersions" :key="version.id" :value="version.id">
                Версия {{ version.version }} · {{ version.status === 'active' ? 'активна' : 'черновик шаблона' }}
              </option>
            </select>
          </label>
          <div v-if="candidate" data-testid="apply-template-version" class="space-y-3 border-t border-slate-200 pt-3 dark:border-slate-700">
            <p v-if="candidate.status !== 'active'" class="text-sm">Версия {{ candidate.version }} станет основной для новых документов по этому шаблону.</p>
            <p v-else class="text-sm">Активна версия {{ candidate.version }}. Её можно применить к этому черновику.</p>
            <label v-if="parameters?.has_editable_copy" class="flex items-start gap-2 text-sm">
              <input v-model="replaceCopy" type="checkbox" class="mt-1" :disabled="busy" />
              Пересобрать этот черновик и заменить ручные правки в рабочей копии.
            </label>
            <button type="button" class="editor-primary" :disabled="!canSave" @click="save">
              {{ applyToDraft ? 'Применить и посмотреть черновик' : 'Сохранить для новых документов' }}
            </button>
          </div>
        </template>
      </div>
    </dialog>
  </Teleport>
</template>

<style scoped>
.template-editor { @apply fixed m-auto max-w-full overflow-y-auto rounded-2xl border-0 bg-white text-slate-900 shadow-xl dark:bg-slate-900 dark:text-white; width: min(32rem, calc(100% - 1rem)); max-height: calc(100dvh - 1rem); }
.template-editor--preview { width: min(56rem, calc(100% - 1rem)); }
.template-editor::backdrop { background: rgb(15 23 42 / .5); }
.editor-action, .editor-primary { @apply inline-flex min-h-9 items-center justify-center rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-semibold disabled:opacity-50 dark:border-slate-600; }
.editor-primary { @apply border-brand-600 bg-brand-600 text-white; }
</style>
