<script setup lang="ts">
import MediaField from "../MediaField.vue";
import type { BrandForm } from "./brand-form-types";

defineProps<{
  open: boolean;
  form: BrandForm;
  editing: boolean;
  saving: boolean;
}>();

const emit = defineEmits<{
  close: [];
  save: [];
}>();
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
    @click.self="emit('close')"
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
      <div class="space-y-3 p-5">
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
          @click="emit('close')"
        >
          Отмена</button
        ><button
          type="button"
          class="rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700 disabled:opacity-50"
          :disabled="saving"
          @click="emit('save')"
        >
          {{ saving ? "Сохранение..." : "Сохранить" }}
        </button>
      </footer>
    </div>
  </div>
</template>
