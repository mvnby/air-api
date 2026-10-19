<script setup lang="ts">
import { ref } from "vue";
import { api, type ManagerMediaAssetResponse } from "../../api";
import { getApiErrorMessage } from "../../utils/api-errors";
import { CATALOG_FEATURE_ICONS } from "./feature-presentation";

const emit = defineEmits<{
  selected: [asset: ManagerMediaAssetResponse];
  busy: [value: boolean];
}>();

const activeIcon = ref<string | null>(null);
const error = ref("");

const selectIcon = async (icon: (typeof CATALOG_FEATURE_ICONS)[number]) => {
  if (activeIcon.value) return;
  activeIcon.value = icon.id;
  error.value = "";
  emit("busy", true);
  try {
    const response = await fetch(icon.url);
    if (!response.ok || !response.headers.get("content-type")?.includes("image/svg+xml")) {
      throw new Error("Не удалось открыть иконку. Обновите страницу и попробуйте снова.");
    }
    const file = new File([await response.blob()], `${icon.id}.svg`, { type: "image/svg+xml" });
    const result = await api.uploadMediaAssets({
      files: [file],
      kind: "feature",
      tags_json: JSON.stringify(["feature", "icon", "kitlane", icon.id]),
    });
    const asset = result.items?.[0];
    if (!asset?.url) throw new Error("Не удалось сохранить иконку в медиатеке.");
    emit("selected", asset);
  } catch (cause) {
    error.value = getApiErrorMessage(cause);
  } finally {
    activeIcon.value = null;
    emit("busy", false);
  }
};
</script>

<template>
  <details class="rounded-xl border border-gray-200 dark:border-slate-700">
    <summary class="cursor-pointer px-3 py-2.5 text-sm font-semibold text-brand-700 dark:text-brand-300">
      Иконки Kitlane для кондиционеров
    </summary>
    <div class="px-3 pb-3">
      <p class="mb-3 text-xs text-gray-500 dark:text-slate-400">
        Выберите готовую иконку или загрузите свою выше. Иконка сохраняется в общей медиатеке.
      </p>
      <div class="grid grid-cols-3 gap-2 sm:grid-cols-4" :aria-busy="!!activeIcon">
        <button
          v-for="icon in CATALOG_FEATURE_ICONS"
          :key="icon.id"
          type="button"
          :aria-label="`Выбрать иконку: ${icon.label}`"
          :disabled="!!activeIcon"
          class="flex min-w-0 flex-col items-center gap-1.5 rounded-lg border border-gray-200 p-2 text-center text-xs text-gray-700 hover:border-brand-500 hover:bg-brand-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 disabled:cursor-wait disabled:opacity-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          @click="selectIcon(icon)"
        >
          <img :src="icon.url" alt="" class="h-12 w-12" loading="lazy" />
          <span>{{ activeIcon === icon.id ? 'Сохранение…' : icon.label }}</span>
        </button>
      </div>
      <p v-if="error" role="alert" class="mt-3 text-sm text-red-700 dark:text-red-300">{{ error }}</p>
    </div>
  </details>
</template>
