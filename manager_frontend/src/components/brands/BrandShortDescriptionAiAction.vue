<script setup lang="ts">
import { ref } from "vue";
import {
  contentAiApi,
  type BrandShortDescriptionDraft,
} from "../content-ai/content-ai-api";
import { confirmDialog } from "../../services/ui-feedback";
import { getApiErrorMessage } from "../../utils/api-errors";

const props = defineProps<{
  title: string;
  description: string;
  hasExistingContent?: boolean;
}>();
const emit = defineEmits<{ draft: [value: BrandShortDescriptionDraft] }>();

const loading = ref(false);
const error = ref("");

const generate = async () => {
  const description = props.description.trim();
  if (!description) {
    error.value = "Сначала заполните полное описание бренда.";
    return;
  }
  if (
    props.hasExistingContent &&
    !(await confirmDialog({
      title: "Заменить короткое описание?",
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
    emit(
      "draft",
      await contentAiApi.brandShortDescriptionDraft({
        brand_name: props.title.trim() || undefined,
        full_description: description,
      }),
    );
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
      :disabled="loading || !description.trim()"
      @click="generate"
    >
      {{ loading ? "Подготовка…" : "Сократить с AI" }}
    </button>
    <p
      v-if="error"
      class="basis-full rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20"
    >
      {{ error }}
    </p>
  </div>
</template>
