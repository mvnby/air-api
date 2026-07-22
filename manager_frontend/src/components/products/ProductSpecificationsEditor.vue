<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { CircleAlert, CircleHelp, Hash, Plus, Trash2, Wrench } from 'lucide-vue-next';
import SpecKeyCombobox from '../SpecKeyCombobox.vue';
import SpecValueInput from '../SpecValueInput.vue';
import { useSpecRegistry } from '../../composables/useSpecRegistry';
import { getLegacySpecSuggestion, isTechnicalSpecKey, type EditableSpec } from '../../utils/product-spec-safety';
import { messageDialog } from '../../services/ui-feedback';

type FilterMode = 'filled' | 'problems' | 'all';

const props = defineProps<{
  modelValue: EditableSpec[];
  expertMode: boolean;
}>();

const emit = defineEmits<{
  (event: 'update:modelValue', value: EditableSpec[]): void;
}>();

const filterMode = ref<FilterMode>('filled');
const {
  getSpecConfig,
  getSpecGroup,
  getSpecGroupLabel,
  getSpecHelpText,
  knownSpecKeys,
  loadSpecRegistry,
  specGroupOrder,
} = useSpecRegistry();

onMounted(() => void loadSpecRegistry());

const isFilled = (row: EditableSpec): boolean => String(row.value || '').trim().length > 0;
const hasProblem = (row: EditableSpec): boolean => Boolean(getLegacySpecSuggestion(row.key, row.value));

const visibleEntries = computed(() => props.modelValue
  .map((row, index) => ({ row, index }))
  .filter(({ row }) => props.expertMode || !isTechnicalSpecKey(row.key))
  .filter(({ row }) => {
    if (filterMode.value === 'problems') return hasProblem(row);
    if (filterMode.value === 'filled') return isFilled(row);
    return true;
  }));

const groupedRows = computed(() => {
  const groups = new Map<string, {
    group: string;
    label: string;
    total: number;
    filled: number;
    entries: Array<{ row: EditableSpec; index: number }>;
  }>();
  const source = props.modelValue.filter((row) => props.expertMode || !isTechnicalSpecKey(row.key));
  for (const row of source) {
    const group = row.key.trim() ? getSpecGroup(row.key) : 'other';
    if (!groups.has(group)) {
      groups.set(group, { group, label: getSpecGroupLabel(group), total: 0, filled: 0, entries: [] });
    }
    const target = groups.get(group)!;
    target.total += 1;
    if (isFilled(row)) target.filled += 1;
  }
  for (const entry of visibleEntries.value) {
    const group = entry.row.key.trim() ? getSpecGroup(entry.row.key) : 'other';
    groups.get(group)?.entries.push(entry);
  }
  return Array.from(groups.values())
    .filter((group) => group.entries.length > 0)
    .sort((a, b) => {
      const aIndex = specGroupOrder.indexOf(a.group as never);
      const bIndex = specGroupOrder.indexOf(b.group as never);
      return (aIndex < 0 ? 999 : aIndex) - (bIndex < 0 ? 999 : bIndex)
        || a.label.localeCompare(b.label, 'ru');
    });
});

const problemCount = computed(() => props.modelValue.filter(hasProblem).length);

const replaceRow = (index: number, patch: Partial<EditableSpec>) => {
  const next = props.modelValue.map((row, rowIndex) => rowIndex === index ? { ...row, ...patch } : row);
  emit('update:modelValue', next);
};

const addRow = () => emit('update:modelValue', [...props.modelValue, { key: '', value: '' }]);
const removeRow = (index: number) => emit('update:modelValue', props.modelValue.filter((_, rowIndex) => rowIndex !== index));

const showHelp = async (key: string) => {
  const text = getSpecHelpText(key);
  if (text) await messageDialog({ title: 'Подсказка по характеристике', description: text });
};
</script>

<template>
  <section class="space-y-4">
    <header class="flex flex-col gap-3 border-b border-gray-100 pb-4 dark:border-slate-800 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p class="text-xs font-bold uppercase tracking-[0.16em] text-teal-700 dark:text-teal-300">Характеристики</p>
        <h2 class="mt-1 text-xl font-bold text-gray-950 dark:text-white">Технические данные товара</h2>
        <p class="mt-1 text-sm text-gray-500 dark:text-slate-400">
          {{ expertMode ? 'Экспертный режим: доступны ключи схемы и удаление полей.' : 'Безопасный режим: редактируются только значения.' }}
        </p>
      </div>
      <button v-if="expertMode" type="button" class="inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-gray-200 px-3 text-sm font-semibold text-gray-700 hover:bg-gray-50 dark:border-slate-700 dark:text-slate-200" @click="addRow">
        <Plus class="h-4 w-4" /> Добавить поле
      </button>
    </header>

    <div class="flex flex-wrap items-center gap-2">
      <button v-for="option in ([['filled', 'Заполненные'], ['problems', `Проблемные${problemCount ? ` · ${problemCount}` : ''}`], ['all', 'Все поля']] as const)" :key="option[0]" type="button" class="h-9 rounded-lg border px-3 text-sm font-semibold transition" :class="filterMode === option[0] ? 'border-teal-300 bg-teal-50 text-teal-800 dark:border-teal-800 dark:bg-teal-950 dark:text-teal-200' : 'border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-slate-700 dark:text-slate-300'" @click="filterMode = option[0]">
        {{ option[1] }}
      </button>
    </div>

    <div v-if="groupedRows.length" class="space-y-3">
      <details v-for="group in groupedRows" :key="group.group" open class="rounded-lg border border-gray-200 bg-gray-50/60 dark:border-slate-700 dark:bg-slate-950/30">
        <summary class="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
          <span class="font-bold text-gray-800 dark:text-slate-100">{{ group.label }}</span>
          <span class="rounded-full bg-white px-2 py-0.5 text-xs font-semibold text-gray-500 shadow-sm dark:bg-slate-800 dark:text-slate-300">{{ group.filled }} / {{ group.total }}</span>
        </summary>
        <div class="space-y-2 border-t border-gray-200 p-3 dark:border-slate-700">
          <div v-for="{ row, index } in group.entries" :key="`${row.key}-${index}`" class="rounded-lg border border-gray-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
            <div class="grid gap-3" :class="expertMode ? 'lg:grid-cols-[minmax(200px,.8fr)_minmax(260px,1.2fr)_auto]' : 'lg:grid-cols-[minmax(220px,.8fr)_minmax(260px,1.2fr)_auto]'">
              <div class="min-w-0">
                <SpecKeyCombobox v-if="expertMode" :model-value="row.key" :known-keys="knownSpecKeys" @update:model-value="replaceRow(index, { key: $event })" />
                <template v-else>
                  <p class="text-sm font-semibold text-gray-800 dark:text-slate-100">{{ getSpecConfig(row.key)?.label || row.key }}</p>
                  <p v-if="getSpecConfig(row.key)?.unit" class="mt-0.5 text-xs text-gray-400">Единица: {{ getSpecConfig(row.key)?.unit }}</p>
                </template>
              </div>
              <SpecValueInput :model-value="row.value" :spec-key="row.key" compact @update:model-value="replaceRow(index, { value: $event })" />
              <div class="flex items-start justify-end gap-1">
                <button v-if="getSpecHelpText(row.key)" type="button" class="rounded-full p-2 text-slate-400 hover:bg-teal-50 hover:text-teal-700 dark:hover:bg-slate-800" title="Пояснение" @click="showHelp(row.key)"><CircleHelp class="h-4 w-4" /></button>
                <button v-if="expertMode" type="button" class="rounded-lg p-2 text-gray-300 hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-950/30" title="Удалить поле" @click="removeRow(index)"><Trash2 class="h-4 w-4" /></button>
              </div>
            </div>
            <div v-if="getLegacySpecSuggestion(row.key, row.value)" class="mt-3 flex flex-col gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100 sm:flex-row sm:items-center sm:justify-between">
              <span class="flex items-start gap-2"><CircleAlert class="mt-0.5 h-4 w-4 shrink-0" />{{ getLegacySpecSuggestion(row.key, row.value)?.message }}</span>
              <button type="button" class="shrink-0 rounded-md border border-amber-300 bg-white px-2.5 py-1 font-bold dark:border-amber-800 dark:bg-slate-900" @click="replaceRow(index, { value: getLegacySpecSuggestion(row.key, row.value)?.value || row.value })">Преобразовать</button>
            </div>
          </div>
        </div>
      </details>
    </div>

    <div v-else class="flex min-h-48 flex-col items-center justify-center rounded-lg border border-dashed border-gray-300 bg-gray-50 px-5 text-center dark:border-slate-700 dark:bg-slate-950/30">
      <Hash v-if="filterMode !== 'problems'" class="h-7 w-7 text-gray-300" />
      <Wrench v-else class="h-7 w-7 text-emerald-500" />
      <p class="mt-2 font-semibold text-gray-700 dark:text-slate-200">{{ filterMode === 'problems' ? 'Подозрительных legacy-значений не найдено' : 'Нет характеристик для выбранного фильтра' }}</p>
    </div>
  </section>
</template>
