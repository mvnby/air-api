<script setup lang="ts">
import { ref } from "vue";
import {
  contentAiApi,
  type SeriesContentDraft,
} from "../content-ai/content-ai-api";
import { confirmDialog } from "../../services/ui-feedback";
import { getApiErrorMessage } from "../../utils/api-errors";

const props = defineProps<{
  sourceUrl: string;
  description: string;
  title: string;
  brandName?: string;
  hasExistingContent?: boolean;
}>();
const emit = defineEmits<{ draft: [value: SeriesContentDraft] }>();
const loading = ref(false);
const error = ref("");

const generate = async (mode: "from_source" | "polish_text") => {
  const sourceUrl = props.sourceUrl.trim();
  const description = props.description.trim();
  if (mode === "from_source" && !sourceUrl) {
    error.value = "Сначала укажите источник.";
    return;
  }
  if (mode === "polish_text" && !description) {
    error.value = "Сначала вставьте описание серии.";
    return;
  }
  if (
    props.hasExistingContent &&
    !(await confirmDialog({
      title: "Заменить заполненное описание?",
      description:
        "AI подготовит новый черновик. Изменения останутся только в форме до сохранения.",
      confirmText: "Заменить",
      variant: "warning",
    }))
  )
    return;
  loading.value = true;
  error.value = "";
  try {
    const draft = await contentAiApi.seriesDraft(
      mode === "from_source"
        ? {
            mode,
            source_url: sourceUrl,
            title: props.title.trim() || undefined,
            brand_name: props.brandName,
          }
        : {
            mode,
            full_description: description,
            title: props.title.trim() || undefined,
            brand_name: props.brandName,
          },
    );
    emit("draft", draft);
  } catch (cause) {
    error.value = getApiErrorMessage(cause);
  } finally {
    loading.value = false;
  }
};
</script>

<template>
  <div class="flex flex-wrap items-center gap-3">
    <button
      type="button"
      class="text-xs text-teal-700 hover:underline disabled:opacity-50 dark:text-teal-300"
      :disabled="loading"
      @click="generate('from_source')"
    >
      Взять из источника
    </button>
    <button
      type="button"
      class="text-xs text-teal-700 hover:underline disabled:opacity-50 dark:text-teal-300"
      :disabled="loading"
      @click="generate('polish_text')"
    >
      {{ loading ? "Подготовка…" : "Оформить и сократить" }}
    </button>
    <p
      v-if="error"
      class="basis-full rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20"
    >
      {{ error }}
    </p>
  </div>
</template>
