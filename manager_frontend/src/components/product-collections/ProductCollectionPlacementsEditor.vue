<script setup lang="ts">
import { ref } from "vue";
import {
  Plus,
  Trash2,
  Copy,
  Check,
  LayoutGrid,
  GalleryHorizontal,
  RectangleHorizontal,
  PanelsTopLeft,
} from "lucide-vue-next";
import type { ManagerProductCollectionPlacementPayload } from "../../client";
import {
  articleCollectionSnippet,
  placementDateForInput,
  placementLabel,
  placementLocationKey,
  placementLocations,
} from "./product-collection-placements";

const props = withDefaults(
  defineProps<{
    modelValue: ManagerProductCollectionPlacementPayload[];
    disabled?: boolean;
  }>(),
  { disabled: false },
);
const emit = defineEmits<{
  "update:modelValue": [value: ManagerProductCollectionPlacementPayload[]];
}>();
const copyMessage = ref("");
const formats = [
  { value: "carousel", label: "Слайдер", icon: GalleryHorizontal },
  { value: "grid", label: "Сетка", icon: LayoutGrid },
  { value: "tiles", label: "Плитки", icon: PanelsTopLeft },
  { value: "single", label: "Один товар", icon: RectangleHorizontal },
] as const;

function update(
  index: number,
  patch: Partial<ManagerProductCollectionPlacementPayload>,
) {
  if (props.disabled) return;
  emit(
    "update:modelValue",
    props.modelValue.map((row, current) =>
      current === index ? { ...row, ...patch } : row,
    ),
  );
}

function add() {
  if (props.disabled || props.modelValue.length >= 20) return;
  const free = placementLocations.find(
    (location) =>
      !props.modelValue.some(
        (row) =>
          row.surface_key === location.surface &&
          row.slot_key === location.slot,
      ),
  );
  emit("update:modelValue", [
    ...props.modelValue,
    {
      surface_key: free?.surface ?? "article",
      slot_key: free?.slot ?? "",
      position: 0,
      is_enabled: true,
      starts_at: null,
      ends_at: null,
      display_mode: free?.slot === "product_of_day" ? "single" : free?.slot === "featured_products" ? "grid" : "carousel",
      rotation_mode: free?.slot === "product_of_day" ? "daily" : "none",
      grid_columns: free?.slot === "featured_products" ? 4 : 3,
      item_limit: null,
    },
  ]);
}

function chooseLocation(index: number, key: string) {
  const location = placementLocations.find((item) => item.key === key);
  if (location) {
    update(index, {
      surface_key: location.surface,
      slot_key: location.slot,
      ...(location.slot === "product_of_day"
        ? { display_mode: "single", rotation_mode: "daily" }
        : {}),
    });
  } else if (key === "article") {
    update(index, { surface_key: "article", slot_key: "" });
  }
}

function dateChanged(
  index: number,
  key: "starts_at" | "ends_at",
  value: string,
) {
  update(index, { [key]: value ? new Date(value).toISOString() : null });
}

function isDuplicate(index: number) {
  const row = props.modelValue[index];
  return (
    !!row &&
    props.modelValue.some(
      (other, i) =>
        i !== index &&
        row.surface_key === other.surface_key &&
        row.slot_key === other.slot_key,
    )
  );
}

async function copySnippet(slot: string) {
  try {
    await navigator.clipboard.writeText(articleCollectionSnippet(slot));
    copyMessage.value = "Код вставки скопирован";
  } catch {
    copyMessage.value =
      "Не удалось скопировать. Выделите код ниже и скопируйте его вручную.";
  }
}
</script>

<template>
  <section class="placements-editor" aria-label="Размещения подборки">
    <div class="placements-heading">
      <div>
        <h3>Где показывать подборку</h3>
        <p>
          Одна подборка может выглядеть по-разному в каждом месте. Изменения
          вступят в силу после сохранения.
        </p>
      </div>
      <button
        type="button"
        class="placement-add"
        :disabled="disabled || modelValue.length >= 20"
        @click="add"
      >
        <Plus :size="18" /> Добавить размещение
      </button>
    </div>
    <p v-if="!modelValue.length" class="placement-empty">
      Места показа ещё не выбраны. Добавьте блок на главной, в каталоге или в
      статье.
    </p>
    <article
      v-for="(row, index) in modelValue"
      :key="index"
      class="placement-card"
      :data-testid="`placement-${index}`"
    >
      <header>
        <h4>{{ placementLabel(row) || "Новое размещение" }}</h4>
        <div class="placement-actions">
          <button
            type="button"
            role="switch"
            :aria-checked="row.is_enabled !== false"
            :aria-label="`Показ: ${placementLabel(row)}`"
            :class="['placement-switch', { enabled: row.is_enabled !== false }]"
            :disabled="disabled"
            @click="update(index, { is_enabled: row.is_enabled === false })"
          >
            <Check v-if="row.is_enabled !== false" :size="14" />{{
              row.is_enabled === false ? "Выключено" : "Включено"
            }}
          </button>
          <button
            type="button"
            class="placement-remove"
            :aria-label="`Удалить размещение ${placementLabel(row)}`"
            :disabled="disabled"
            @click="
              emit(
                'update:modelValue',
                modelValue.filter((_, i) => i !== index),
              )
            "
          >
            <Trash2 :size="18" />
          </button>
        </div>
      </header>
      <label class="placement-field"
        >Место показа
        <select
          :value="placementLocationKey(row)"
          :disabled="disabled"
          @change="
            chooseLocation(index, ($event.target as HTMLSelectElement).value)
          "
        >
          <option
            v-for="location in placementLocations"
            :key="location.key"
            :value="location.key"
          >
            {{ location.label }}
          </option>
          <option value="article">Статья · Вставка в текст</option>
          <option v-if="placementLocationKey(row) === 'custom'" value="custom">
            Существующее место: {{ row.surface_key }} / {{ row.slot_key }}
          </option>
        </select>
      </label>
      <label v-if="row.surface_key === 'article'" class="placement-field"
        >Название вставки
        <input
          :value="row.slot_key"
          :disabled="disabled"
          required
          pattern="[a-z0-9][a-z0-9_-]{0,79}"
          maxlength="80"
          placeholder="heating-guide"
          @input="
            update(index, {
              slot_key: ($event.target as HTMLInputElement).value.toLowerCase(),
            })
          "
        />
        <small
          >Короткое имя латиницей, например heating-guide. По нему статья найдёт
          этот блок.</small
        >
      </label>
      <p v-if="isDuplicate(index)" class="placement-error" role="alert">
        Это место уже добавлено к подборке. Выберите другое или удалите повтор.
      </p>
      <fieldset :disabled="disabled" class="placement-formats">
        <legend>Внешний вид</legend>
        <div>
          <button
            v-for="format in formats"
            :key="format.value"
            type="button"
            :aria-pressed="(row.display_mode || 'carousel') === format.value"
            @click="
              update(index, {
                display_mode: format.value,
                ...(format.value !== 'single' ? { rotation_mode: 'none' } : {}),
              })
            "
          >
            <component :is="format.icon" :size="26" /><span>{{
              format.label
            }}</span>
          </button>
        </div>
      </fieldset>
      <div class="placement-options">
        <label v-if="row.display_mode !== 'single'" class="placement-field"
          >Лимит товаров
          <input
            type="number"
            min="1"
            max="24"
            :disabled="disabled"
            :value="row.item_limit ?? ''"
            placeholder="Как в подборке"
            @input="
              update(index, {
                item_limit:
                  ($event.target as HTMLInputElement).value === ''
                    ? null
                    : Number(($event.target as HTMLInputElement).value),
              })
            "
          />
        </label>
        <label
          v-if="row.display_mode === 'grid' || row.display_mode === 'tiles'"
          class="placement-field"
          >Колонок на компьютере
          <select
            :value="row.grid_columns ?? 3"
            :disabled="disabled"
            @change="
              update(index, {
                grid_columns: Number(
                  ($event.target as HTMLSelectElement).value,
                ),
              })
            "
          >
            <option :value="2">2</option>
            <option :value="3">3</option>
            <option :value="4">4</option>
          </select>
          <small>На телефоне блок перестраивается по ширине экрана.</small>
        </label>
      </div>
      <div v-if="row.display_mode === 'single'" class="placement-rotation">
        <span>Выбор товара</span>
        <div role="group" aria-label="Выбор товара">
          <button
            type="button"
            :disabled="disabled"
            :aria-pressed="row.rotation_mode !== 'daily'"
            @click="update(index, { rotation_mode: 'none' })"
          >
            Первый по порядку</button
          ><button
            type="button"
            :disabled="disabled"
            :aria-pressed="row.rotation_mode === 'daily'"
            @click="update(index, { rotation_mode: 'daily' })"
          >
            Менять каждый день
          </button>
        </div>
        <small v-if="row.rotation_mode === 'daily'"
          >Смена в 00:00 UTC. Если здесь несколько подборок с ежедневной сменой,
          показывается одна из них.</small
        >
      </div>
      <details class="placement-details">
        <summary>Расписание и порядок</summary>
        <div class="placement-options">
          <label class="placement-field"
            >Начало показа<input
              type="datetime-local"
              :disabled="disabled"
              :value="placementDateForInput(row.starts_at)"
              @change="
                dateChanged(
                  index,
                  'starts_at',
                  ($event.target as HTMLInputElement).value,
                )
              "
          /></label>
          <label class="placement-field"
            >Окончание показа<input
              type="datetime-local"
              :disabled="disabled"
              :value="placementDateForInput(row.ends_at)"
              @change="
                dateChanged(
                  index,
                  'ends_at',
                  ($event.target as HTMLInputElement).value,
                )
              "
          /></label>
          <label class="placement-field"
            >Порядок среди подборок<input
              type="number"
              min="0"
              :disabled="disabled"
              :value="row.position ?? 0"
              @input="
                update(index, {
                  position: Number(($event.target as HTMLInputElement).value),
                })
              "
            /><small
              >Меньшее число — раньше. Даты указаны в часовом поясе
              устройства.</small
            ></label
          >
        </div>
      </details>
      <details
        v-if="
          row.surface_key === 'article' &&
          articleCollectionSnippet(row.slot_key)
        "
        class="placement-details"
      >
        <summary>Код для вставки в статью</summary>
        <p>
          Импорт добавьте в начало MDX-статьи, компонент — в нужное место
          текста. Путь импорта указан для статьи в src/content/blog; при другой
          вложенности измените путь. Состав и оформление блока управляются
          здесь.
        </p>
        <pre>{{ articleCollectionSnippet(row.slot_key) }}</pre>
        <button
          type="button"
          class="placement-copy"
          @click="copySnippet(row.slot_key)"
        >
          <Copy :size="16" /> Скопировать код
        </button>
      </details>
    </article>
    <p v-if="copyMessage" role="status">{{ copyMessage }}</p>
    <p class="placement-note">
      Включённое размещение появится на сайте, когда подборка опубликована,
      наступило время показа и достаточно подходящих товаров. Минимум товаров и
      резервная подборка задаются в настройках подборки.
    </p>
  </section>
</template>

<style scoped>
.placements-editor {
  display: grid;
  gap: 1rem;
  color: var(--mv-text);
}
.placements-heading,
.placement-card header,
.placement-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}
h3,
h4 {
  font-weight: 650;
  margin: 0;
  overflow-wrap: anywhere;
}
h3 {
  font-size: 1.05rem;
}
.placements-heading p,
.placement-note,
.placement-details p {
  font-size: 0.85rem;
  opacity: 0.7;
  margin: 0.35rem 0 0;
  line-height: 1.55;
}
.placement-card {
  border: 1px solid var(--mv-border);
  border-radius: 14px;
  padding: 1.1rem;
  display: grid;
  gap: 1rem;
  min-width: 0;
}
button,
select,
input {
  font: inherit;
}
button {
  cursor: pointer;
}
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
button:focus-visible,
summary:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 3px;
}
.placement-add,
.placement-copy {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  border: 1px solid #2563eb;
  border-radius: 8px;
  padding: 0.65rem 0.8rem;
  color: #2563eb;
  background: transparent;
  white-space: nowrap;
  font-size: 0.85rem;
}
.placement-switch {
  display: flex;
  gap: 0.3rem;
  align-items: center;
  min-height: 40px;
  padding: 0.35rem 0.6rem;
  border: 1px solid #94a3b8;
  border-radius: 20px;
  background: transparent;
  font-size: 0.8rem;
}
.placement-switch.enabled {
  color: #047857;
  background: #ecfdf5;
  border-color: #a7f3d0;
}
.placement-remove {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border: 0;
  background: transparent;
  color: #dc2626;
}
.placement-field {
  display: grid;
  gap: 0.35rem;
  min-width: 0;
  font-size: 0.85rem;
}
.placement-field input,
.placement-field select {
  width: 100%;
  min-width: 0;
  border: 1px solid var(--mv-border);
  border-radius: 8px;
  padding: 0.65rem;
  background: var(--mv-surface);
  color: inherit;
  box-sizing: border-box;
}
.placement-field small,
.placement-rotation small {
  font-size: 0.75rem;
  opacity: 0.7;
  line-height: 1.5;
}
.placement-formats {
  border: 0;
  padding: 0;
  margin: 0;
  min-width: 0;
}
.placement-formats legend {
  font-size: 0.85rem;
  margin-bottom: 0.45rem;
}
.placement-formats > div {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.5rem;
}
.placement-formats button {
  display: grid;
  justify-items: center;
  gap: 0.5rem;
  padding: 0.8rem 0.3rem;
  border: 1px solid var(--mv-border);
  border-radius: 10px;
  background: transparent;
  color: inherit;
  font-size: 0.8rem;
}
.placement-formats button[aria-pressed="true"],
.placement-rotation button[aria-pressed="true"] {
  border-color: #2563eb;
  background: #eff6ff;
  color: #1d4ed8;
}
.placement-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.9rem;
}
.placement-rotation {
  display: grid;
  gap: 0.5rem;
  font-size: 0.85rem;
}
.placement-rotation > div {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.placement-rotation button {
  border: 1px solid var(--mv-border);
  border-radius: 8px;
  background: transparent;
  color: inherit;
  padding: 0.6rem;
}
.placement-details {
  font-size: 0.85rem;
}
.placement-details summary {
  cursor: pointer;
  padding: 0.3rem 0;
}
.placement-details > div {
  margin-top: 0.8rem;
}
.placement-details pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 0.75rem;
  line-height: 1.6;
  background: rgba(148, 163, 184, 0.12);
  padding: 0.8rem;
  border-radius: 8px;
  margin: 0.8rem 0;
}
.placement-empty {
  padding: 2rem 1rem;
  text-align: center;
  border: 1px dashed #94a3b8;
  border-radius: 14px;
  line-height: 1.6;
}
.placement-error {
  color: #dc2626;
  font-size: 0.85rem;
}
@media (max-width: 600px) {
  .placements-heading {
    align-items: stretch;
    flex-direction: column;
  }
  .placement-card {
    padding: 0.85rem;
  }
  .placement-card header {
    align-items: flex-start;
    flex-direction: column;
  }
  .placement-actions {
    width: 100%;
  }
  .placement-options {
    grid-template-columns: 1fr;
  }
  .placement-formats > div {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
