<script setup lang="ts">
import { ref } from 'vue';

const labels = defineModel<string[]>({ required: true });
const draft = ref('');
const editing = ref(false);

const addLabel = () => {
  const label = draft.value.trim().replace(/\s+/g, ' ');
  if (!label) return;
  const exists = labels.value.some((item) => (
    item.toLocaleLowerCase('ru-RU') === label.toLocaleLowerCase('ru-RU')
  ));
  if (!exists) labels.value = [...labels.value, label];
  draft.value = '';
  editing.value = false;
};

const removeLabel = (label: string) => {
  labels.value = labels.value.filter((item) => item !== label);
};
</script>

<template>
  <div v-if="labels.length || editing" class="mt-3 flex flex-wrap items-center gap-1.5">
    <span v-for="label in labels" :key="label" class="inline-flex items-center gap-1 rounded-full border border-teal-200 bg-teal-50 px-2 py-1 text-xs font-medium text-teal-800 dark:border-teal-500/30 dark:bg-teal-500/10 dark:text-teal-200">
      {{ label }}
      <button type="button" class="rounded-full p-0.5 hover:bg-teal-100 dark:hover:bg-teal-800" :aria-label="`Удалить метку ${label}`" @click="removeLabel(label)">
        <span class="material-icons-round block text-[13px]">close</span>
      </button>
    </span>
    <button v-if="!editing" type="button" data-testid="add-manager-label" class="inline-flex items-center gap-1 rounded-full border border-dashed border-slate-300 px-2 py-1 text-xs font-medium text-slate-500 hover:border-teal-300 hover:text-teal-700 dark:border-slate-700 dark:text-slate-400" @click="editing = true">
      <span class="material-icons-round text-[13px]">add</span> Добавить метку
    </button>
    <div v-else class="flex min-w-[190px] gap-1.5">
      <input v-model="draft" data-testid="manager-label-draft" class="field-input h-8 text-xs" placeholder="Новая метка" @keydown.enter.prevent="addLabel" @keydown.esc.prevent="editing = false" />
      <button type="button" class="btn-mini h-8 px-2 text-xs" @click="addLabel">Добавить</button>
    </div>
  </div>
  <button v-else type="button" data-testid="add-manager-label" class="mt-2 inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-teal-700 dark:text-slate-400 dark:hover:text-teal-300" @click="editing = true">
    <span class="material-icons-round text-[14px]">add</span> Добавить метку
  </button>
</template>
