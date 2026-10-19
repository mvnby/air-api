<script setup lang="ts">
import { ref } from "vue";
import MediaField from "../MediaField.vue";
import BrandShortDescriptionAiAction from "./BrandShortDescriptionAiAction.vue";
import type { BrandForm } from "./brand-form-types";
import CatalogDocumentsPanel from "../catalog/CatalogDocumentsPanel.vue";
import { useCatalogDocumentsEditor } from "../../composables/useCatalogDocumentsEditor";

const props = defineProps<{
  open: boolean;
  form: BrandForm;
  editing: boolean;
  brandId?: number;
  saving: boolean;
}>();

const emit = defineEmits<{
  close: [];
  save: [];
}>();
const { documentsBusy, saveDocuments, confirmDiscardDocuments } = useCatalogDocumentsEditor();
const savingDocuments = ref(false);
const save = async () => {
  if (props.saving || savingDocuments.value) return;
  savingDocuments.value = true;
  try {
    if (await saveDocuments()) emit("save");
  } finally {
    savingDocuments.value = false;
  }
};
const close = async () => {
  if (props.saving || savingDocuments.value || !await confirmDiscardDocuments()) return;
  emit("close");
};
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
    @click.self="close"
  >
    <div
      class="w-full max-w-2xl overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900"
    >
      <header
        class="border-b border-gray-200 bg-slate-50 px-5 py-4 dark:border-slate-700 dark:bg-slate-800/60"
      >
        <h2 class="text-lg font-bold text-gray-900 dark:text-slate-100">
          {{ editing ? "Редактирование бренда" : "Новый бренд" }}
        </h2>
      </header>
      <div class="max-h-[75vh] space-y-3 overflow-y-auto p-5">
        <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
          <label class="space-y-1 text-sm"
            ><span class="font-medium text-gray-600 dark:text-slate-300"
              >Название</span
            ><input
              v-model="form.title"
              type="text"
              class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
          /></label>
          <label class="space-y-1 text-sm"
            ><span class="font-medium text-gray-600 dark:text-slate-300"
              >Slug</span
            ><input
              v-model="form.slug"
              type="text"
              class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
          /></label>
        </div>
        <MediaField
          v-model="form.logo_url"
          label="Логотип"
          kind="brand"
          :tags="['logo', 'brand']"
          accept="image/svg+xml,image/png,image/jpeg,image/webp,.svg"
          placeholder="/media/library/original/logo.svg"
        />
        <label class="block space-y-1 text-sm">
          <span class="font-medium text-gray-600 dark:text-slate-300">Официальный сайт</span>
          <input v-model="form.official_url" type="url" maxlength="2048"
            placeholder="https://manufacturer.example"
            class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 dark:border-slate-700 dark:bg-slate-900" />
          <span class="block text-xs text-gray-500">Источник для проверки каталога и работы с материалами бренда.</span>
        </label>
        <div class="space-y-1 text-sm">
          <label class="block space-y-1"
            ><span class="font-medium text-gray-600 dark:text-slate-300"
              >Короткое описание</span
            ><textarea
              v-model="form.short_description"
              rows="2"
              maxlength="200"
              class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
            /><span class="block text-xs text-gray-500 dark:text-slate-400"
              >1–2 строки для карточки бренда.</span
            ></label
          ><BrandShortDescriptionAiAction
            :title="form.title"
            :description="form.description"
            :has-existing-content="Boolean(form.short_description.trim())"
            @draft="form.short_description = $event.short_description"
          />
        </div>
        <label class="block space-y-1 text-sm"
          ><span class="font-medium text-gray-600 dark:text-slate-300"
            >Описание</span
          ><textarea
            v-model="form.description"
            rows="4"
            class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
          /><span class="block text-xs text-gray-500 dark:text-slate-400"
            >Можно использовать Markdown: абзацы, списки, ссылки, **жирный**,
            *курсив*.</span
          ></label
        >
        <CatalogDocumentsPanel v-if="brandId" ref="documentsPanel" target-type="brand" :target-id="brandId" />
        <p v-else class="text-xs text-gray-500">Сохраните бренд, чтобы добавить документы.</p>
        <label class="flex items-center gap-2 text-sm"
          ><input
            v-model="form.is_published"
            type="checkbox"
            class="rounded border-gray-300 dark:border-slate-700"
          /><span class="font-medium text-gray-600 dark:text-slate-300"
            >Публиковать бренд</span
          ></label
        >
      </div>
      <footer
        class="flex items-center justify-end gap-2 border-t border-gray-200 bg-slate-50 px-5 py-4 dark:border-slate-700 dark:bg-slate-800/60"
      >
        <button
          type="button"
          class="rounded-lg px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-700"
          :disabled="saving || savingDocuments || documentsBusy"
          @click="close"
        >
          Отмена</button
        ><button
          type="button"
          class="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50"
          :disabled="saving || savingDocuments || documentsBusy"
          @click="save"
        >
          {{ saving || savingDocuments ? "Сохранение..." : "Сохранить" }}
        </button>
      </footer>
    </div>
  </div>
</template>
