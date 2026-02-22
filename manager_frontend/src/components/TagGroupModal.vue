<script setup lang="ts">
import { ref, watch } from 'vue';
import { api } from '../api';
import type { ManagerTagGroupResponse } from '../client';
import { getApiErrorMessage } from '../utils/api-errors';

const props = defineProps<{
  modelValue: boolean;
  tagGroup: ManagerTagGroupResponse | null;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
  (e: 'success'): void;
}>();

const loading = ref(false);
const error = ref('');

const form = ref({
  title: '',
  slug: '',
  color: 'secondary',
  is_public: true,
  allow_multiple: false,
});

const isEditing = ref(false);

watch(() => props.modelValue, (newVal) => {
  if (newVal) {
    if (props.tagGroup) {
      isEditing.value = true;
      form.value = {
        title: props.tagGroup.title,
        slug: props.tagGroup.slug,
        color: props.tagGroup.color,
        is_public: props.tagGroup.is_public,
        allow_multiple: props.tagGroup.allow_multiple,
      };
    } else {
      isEditing.value = false;
      form.value = {
        title: '',
        slug: '',
        color: 'secondary',
        is_public: true,
        allow_multiple: false,
      };
    }
    error.value = '';
  }
});

const close = () => {
  emit('update:modelValue', false);
};

const save = async () => {
  loading.value = true;
  error.value = '';
  try {
    if (isEditing.value && props.tagGroup) {
      await api.updateManagerTagGroup(props.tagGroup.id, form.value);
    } else {
      await api.createManagerTagGroup(form.value);
    }
    emit('success');
    close();
  } catch (err: any) {
    error.value = getApiErrorMessage(err);
  } finally {
    loading.value = false;
  }
};
</script>

<template>
  <div v-if="modelValue" class="fixed inset-0 z-50 flex items-center justify-center p-4">
    <div class="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" @click="close"></div>
    <div class="relative bg-white dark:bg-[#1e293b] w-full max-w-md rounded-2xl shadow-xl overflow-hidden border border-slate-200 dark:border-slate-700/50">
      <div class="p-6 border-b border-slate-100 dark:border-slate-700/50 flex justify-between items-center bg-slate-50 dark:bg-slate-800/50">
        <h3 class="text-xl font-bold text-slate-800 dark:text-white">{{ isEditing ? 'Редактировать группу' : 'Новая группа' }}</h3>
        <button @click="close" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors">
          <span class="material-icons-round">close</span>
        </button>
      </div>

      <div class="p-6 space-y-4">
        <div v-if="error" class="p-3 bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-400 text-sm rounded-lg border border-red-100 dark:border-red-500/20">
          {{ error }}
        </div>

        <div>
          <label class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Название группы *</label>
          <input 
            v-model="form.title" 
            type="text" 
            class="w-full px-4 py-2 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-600 rounded-lg text-slate-900 dark:text-white focus:ring-2 focus:ring-teal-500 focus:border-transparent outline-none transition-all placeholder-slate-400"
            placeholder="Например: Цвет"
          />
        </div>

        <div>
           <label class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Slug</label>
           <input 
             v-model="form.slug" 
             type="text" 
             class="w-full px-4 py-2 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-600 rounded-lg text-slate-900 dark:text-white focus:ring-2 focus:ring-teal-500 focus:border-transparent outline-none transition-all placeholder-slate-400"
             placeholder="Оставьте пустым для автогенерации"
           />
        </div>

        <div>
          <label class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Цвет (строка, tailwind bg/text color class or hex)</label>
          <input 
             v-model="form.color" 
             type="text" 
             class="w-full px-4 py-2 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-600 rounded-lg text-slate-900 dark:text-white focus:ring-2 focus:ring-teal-500 focus:border-transparent outline-none transition-all placeholder-slate-400"
             placeholder="secondary"
           />
        </div>

        <div class="flex items-center gap-2">
            <input type="checkbox" id="tg_public" v-model="form.is_public" class="w-4 h-4 text-teal-600" />
            <label for="tg_public" class="text-sm font-medium text-slate-700 dark:text-slate-300">Публичная группа</label>
        </div>

        <div class="flex items-center gap-2">
            <input type="checkbox" id="tg_allow_multiple" v-model="form.allow_multiple" class="w-4 h-4 text-teal-600" />
            <label for="tg_allow_multiple" class="text-sm font-medium text-slate-700 dark:text-slate-300">Множественный выбор (В фильтрах)</label>
        </div>

      </div>

      <div class="p-6 bg-slate-50 dark:bg-slate-800/50 border-t border-slate-100 dark:border-slate-700/50 flex justify-end gap-3">
        <button 
          @click="close"
          class="px-5 py-2.5 text-slate-600 dark:text-slate-300 font-medium hover:bg-slate-200 dark:hover:bg-slate-700 rounded-lg transition-colors"
        >
          Отмена
        </button>
        <button 
          @click="save"
          :disabled="loading || !form.title"
          class="px-5 py-2.5 bg-teal-600 text-white font-medium rounded-lg hover:bg-teal-500 active:bg-teal-700 transition-colors disabled:opacity-50 flex items-center gap-2"
        >
          <span v-if="loading" class="material-icons-round animate-spin text-sm">refresh</span>
          Сохранить
        </button>
      </div>
    </div>
  </div>
</template>
