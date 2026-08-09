<script setup lang="ts">
import { ref } from "vue";
import type { ManagerFeatureResponse } from "../../client";
import MediaField from "../MediaField.vue";
import SeriesContentAiActions from "./SeriesContentAiActions.vue";
import SeriesFeatureAssignments from "./SeriesFeatureAssignments.vue";
import type { SeriesForm } from "./brand-form-types";

const props = defineProps<{
  open: boolean;
  form: SeriesForm;
  editing: boolean;
  brandName?: string;
  features: ManagerFeatureResponse[];
  featuresLoading: boolean;
  saving: boolean;
  galleryApplying: boolean;
}>();

const emit = defineEmits<{
  close: [];
  save: [];
  applyGallery: [];
  addGallery: [url: string];
  removeGallery: [index: number];
  addContentBlock: [];
  removeContentBlock: [index: number];
}>();

const pendingGalleryImage = ref("");

const addGallery = (url = pendingGalleryImage.value) => {
  if (!url.trim()) return;
  emit("addGallery", url);
  pendingGalleryImage.value = "";
};
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
    @click.self="emit('close')"
  >
    <div
      class="w-full max-w-5xl overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900"
    >
      <header
        class="border-b border-gray-200 bg-slate-50 px-5 py-4 dark:border-slate-700 dark:bg-slate-800/60"
      >
        <h2 class="text-lg font-bold text-gray-900 dark:text-slate-100">
          {{ editing ? "Редактирование серии" : "Новая серия" }}
        </h2>
        <p v-if="brandName" class="text-sm text-gray-500 dark:text-slate-400">
          {{ brandName }}
        </p>
      </header>
      <div class="max-h-[72vh] space-y-5 overflow-y-auto p-5">
        <section class="space-y-3">
          <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
            <label class="space-y-1 text-sm"
              ><span class="font-medium text-gray-600 dark:text-slate-300"
                >Название</span
              ><input
                v-model="form.title"
                type="text"
                class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 dark:border-slate-700 dark:bg-slate-900" /></label
            ><label class="space-y-1 text-sm"
              ><span class="font-medium text-gray-600 dark:text-slate-300"
                >Slug</span
              ><input
                v-model="form.slug"
                type="text"
                class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
            /></label>
          </div>
          <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
            <label class="space-y-1 text-sm"
              ><span class="font-medium text-gray-600 dark:text-slate-300"
                >Слоган</span
              ><input
                v-model="form.tagline"
                type="text"
                class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
                placeholder="Охлаждение без прямого потока" /></label
            ><label class="space-y-1 text-sm"
              ><span class="font-medium text-gray-600 dark:text-slate-300"
                >Источник</span
              ><input
                v-model="form.source_url"
                type="url"
                class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
                placeholder="https://..."
            /></label>
          </div>
          <div class="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <label class="block space-y-1 text-sm"
              ><span class="font-medium text-gray-600 dark:text-slate-300"
                >Короткое описание</span
              ><textarea
                v-model="form.short_description"
                rows="3"
                class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
              /></label
            ><label class="block space-y-1 text-sm"
              ><span class="font-medium text-gray-600 dark:text-slate-300"
                >Описание серии</span
              ><textarea
                v-model="form.description"
                rows="3"
                class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
              />
            </label>
          </div>
          <SeriesContentAiActions
            :source-url="form.source_url"
            :description="form.description"
            :title="form.title"
            :brand-name="brandName"
            :has-existing-content="
              Boolean(
                form.tagline.trim() ||
                  form.short_description.trim() ||
                  form.description.trim() ||
                  form.seo_title.trim() ||
                  form.seo_description.trim(),
              )
            "
            @draft="
              (draft) => {
                form.tagline = draft.tagline || '';
                form.short_description = draft.short_description;
                form.description = draft.description;
                if (draft.seo_title !== undefined)
                  form.seo_title = draft.seo_title || '';
                if (draft.seo_description !== undefined)
                  form.seo_description = draft.seo_description || '';
              }
            "
          />
        </section>
        <section
          class="space-y-4 border-t border-gray-200 pt-4 dark:border-slate-700"
        >
          <div class="max-w-2xl">
            <MediaField
              v-model="form.hero_image"
              label="Hero image"
              kind="brand"
              :tags="['series', 'hero']"
              accept="image/png,image/jpeg,image/webp,image/svg+xml,.svg"
              placeholder="/media/library/original/series.webp"
            />
          </div>
          <div class="space-y-3">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3
                  class="text-sm font-medium text-gray-600 dark:text-slate-300"
                >
                  Галерея
                </h3>
                <p class="mt-1 text-xs text-gray-500 dark:text-slate-400">
                  Изображения серии для лендингов, карточек и промо-блоков.
                </p>
              </div>
              <button
                v-if="editing"
                type="button"
                class="inline-flex items-center gap-1 rounded-lg border border-teal-200 px-3 py-1.5 text-xs font-semibold text-teal-700 hover:bg-teal-50 disabled:cursor-wait disabled:opacity-50 dark:border-teal-900/60 dark:text-teal-200 dark:hover:bg-teal-950/30"
                :disabled="galleryApplying || !form.galleryImages.length"
                @click="emit('applyGallery')"
              >
                <span class="material-icons-round text-[16px]">library_add</span
                >{{
                  galleryApplying ? "Добавление..." : "Добавить товарам серии"
                }}
              </button>
            </div>
            <div
              v-if="form.galleryImages.length"
              class="grid gap-3 md:grid-cols-2 xl:grid-cols-3"
            >
              <div
                v-for="(_, index) in form.galleryImages"
                :key="`gallery-${index}`"
                class="rounded-xl border border-gray-200 p-3 dark:border-slate-700"
              >
                <div class="mb-2 flex items-center justify-between gap-3">
                  <span
                    class="text-xs font-bold uppercase tracking-[0.14em] text-gray-500 dark:text-slate-400"
                    >Изображение {{ index + 1 }}</span
                  ><button
                    type="button"
                    class="inline-flex h-8 w-8 items-center justify-center rounded-lg text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30"
                    title="Удалить из галереи"
                    aria-label="Удалить из галереи"
                    @click="emit('removeGallery', index)"
                  >
                    <span class="material-icons-round text-[18px]">delete</span>
                  </button>
                </div>
                <MediaField
                  v-model="form.galleryImages[index]"
                  :label="`URL ${index + 1}`"
                  kind="brand"
                  :tags="['series', 'gallery']"
                  accept="image/png,image/jpeg,image/webp,image/svg+xml,.svg"
                  placeholder="/media/library/original/series-gallery.webp"
                />
              </div>
            </div>
            <p
              v-else
              class="rounded-xl border border-dashed border-gray-300 px-3 py-3 text-sm text-gray-500 dark:border-slate-700 dark:text-slate-400"
            >
              Галерея пока пустая.
            </p>
            <div
              class="rounded-xl border border-teal-100 bg-teal-50/40 p-3 dark:border-teal-900/60 dark:bg-teal-950/20"
            >
              <MediaField
                v-model="pendingGalleryImage"
                label="Добавить изображение"
                kind="brand"
                :tags="['series', 'gallery']"
                accept="image/png,image/jpeg,image/webp,image/svg+xml,.svg"
                multiple
                placeholder="/media/library/original/series-gallery.webp"
                @picked="addGallery"
              /><button
                v-if="pendingGalleryImage"
                type="button"
                class="mt-3 inline-flex items-center gap-1 rounded-lg bg-teal-600 px-3 py-2 text-xs font-semibold text-white hover:bg-teal-700"
                @click="addGallery()"
              >
                <span class="material-icons-round text-[16px]">add</span
                >Добавить в галерею
              </button>
            </div>
          </div>
        </section>
        <SeriesFeatureAssignments
          v-model="form.feature_assignments"
          :features="features"
          :loading="featuresLoading"
        />
        <section
          class="space-y-3 border-t border-gray-200 pt-4 dark:border-slate-700"
        >
          <div class="flex items-center justify-between gap-3">
            <div>
              <h3
                class="text-sm font-bold uppercase tracking-[0.16em] text-gray-500 dark:text-slate-400"
              >
                Контентные блоки
              </h3>
              <p class="text-xs text-gray-500 dark:text-slate-400">
                Основа для будущих секций серии как на фирменных страницах.
              </p>
            </div>
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded-lg border border-teal-200 px-3 py-1.5 text-xs font-semibold text-teal-700 hover:bg-teal-50 dark:border-teal-900/60 dark:text-teal-200 dark:hover:bg-teal-950/30"
              @click="emit('addContentBlock')"
            >
              <span class="material-icons-round text-[16px]">add</span>Секция
            </button>
          </div>
          <div v-if="form.contentBlocks.length" class="space-y-3">
            <div
              v-for="(block, index) in form.contentBlocks"
              :key="`content-${index}`"
              class="rounded-xl border border-gray-200 p-3 dark:border-slate-700"
            >
              <div class="mb-3 flex items-center justify-between gap-3">
                <span
                  class="text-xs font-bold uppercase tracking-[0.14em] text-gray-500 dark:text-slate-400"
                  >Секция {{ index + 1 }}</span
                ><button
                  type="button"
                  class="inline-flex h-8 w-8 items-center justify-center rounded-lg text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30"
                  @click="emit('removeContentBlock', index)"
                >
                  <span class="material-icons-round text-[18px]">delete</span>
                </button>
              </div>
              <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
                <label class="space-y-1 text-sm"
                  ><span class="font-medium text-gray-600 dark:text-slate-300"
                    >Тип</span
                  ><select
                    v-model="block.kind"
                    class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
                  >
                    <option value="text">Текст</option>
                    <option value="image_text">Текст + изображение</option>
                    <option value="media">Медиа</option>
                  </select></label
                ><label class="space-y-1 text-sm"
                  ><span class="font-medium text-gray-600 dark:text-slate-300"
                    >Макет</span
                  ><select
                    v-model="block.layout"
                    class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
                  >
                    <option value="text_left">Текст слева</option>
                    <option value="text_right">Текст справа</option>
                    <option value="full">На всю ширину</option>
                  </select></label
                ><label class="space-y-1 text-sm"
                  ><span class="font-medium text-gray-600 dark:text-slate-300"
                    >Заголовок</span
                  ><input
                    v-model="block.title"
                    type="text"
                    class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 dark:border-slate-700 dark:bg-slate-900" /></label
                ><MediaField
                  v-model="block.image_url"
                  label="Изображение"
                  kind="brand"
                  :tags="['series', 'content']"
                  accept="image/png,image/jpeg,image/webp,image/svg+xml,.svg"
                  placeholder="/media/library/original/series-content.webp"
                />
              </div>
              <label class="mt-3 block space-y-1 text-sm"
                ><span class="font-medium text-gray-600 dark:text-slate-300"
                  >Текст</span
                ><textarea
                  v-model="block.text"
                  rows="4"
                  class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
                />
              </label>
            </div>
          </div>
          <p
            v-else
            class="rounded-xl border border-dashed border-gray-300 px-3 py-3 text-sm text-gray-500 dark:border-slate-700 dark:text-slate-400"
          >
            Контентных секций пока нет.
          </p>
        </section>
        <section
          class="grid grid-cols-1 gap-4 border-t border-gray-200 pt-4 dark:border-slate-700 lg:grid-cols-2"
        >
          <label class="block space-y-1 text-sm"
            ><span class="font-medium text-gray-600 dark:text-slate-300"
              >Сноски</span
            ><span class="block text-xs text-gray-500 dark:text-slate-400"
              >Мелкие примечания внизу страницы серии: условия сравнения,
              ограничения функций, ссылки на испытания. Одна сноска на
              строку.</span
            ><textarea
              v-model="form.footnotesText"
              rows="4"
              class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
              placeholder="Одна сноска на строку"
            />
          </label>
          <div class="space-y-3">
            <div>
              <h3
                class="text-sm font-semibold text-gray-700 dark:text-slate-200"
              >
                SEO
              </h3>
              <p class="text-xs text-gray-500 dark:text-slate-400">
                Поля можно отредактировать после генерации описания через AI.
              </p>
            </div>
            <label class="block space-y-1 text-sm"
              ><span class="font-medium text-gray-600 dark:text-slate-300"
                >SEO title</span
              ><input
                v-model="form.seo_title"
                type="text"
                class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 dark:border-slate-700 dark:bg-slate-900" /></label
            ><label class="block space-y-1 text-sm"
              ><span class="font-medium text-gray-600 dark:text-slate-300"
                >SEO description</span
              ><textarea
                v-model="form.seo_description"
                rows="3"
                class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
              />
            </label>
          </div>
        </section>
        <label
          class="flex items-center gap-2 border-t border-gray-200 pt-4 text-sm dark:border-slate-700"
          ><input
            v-model="form.is_published"
            type="checkbox"
            class="rounded border-gray-300 dark:border-slate-700"
          /><span class="font-medium text-gray-600 dark:text-slate-300"
            >Публиковать серию</span
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
