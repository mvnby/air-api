<script setup lang="ts">
import { computed, ref } from 'vue';
import { api } from '../api';
import { getApiErrorMessage } from '../utils/api-errors';

const props = withDefaults(defineProps<{
    modelValue?: string;
    label: string;
    kind?: string;
    tags?: string[];
    accept?: string;
    placeholder?: string;
}>(), {
    modelValue: '',
    kind: 'misc',
    tags: () => [],
    accept: 'image/*,.svg',
    placeholder: '/media/library/original/logo.svg',
});

const emit = defineEmits<{
    'update:modelValue': [value: string];
    uploaded: [url: string];
}>();

const fileInput = ref<HTMLInputElement | null>(null);
const uploading = ref(false);
const error = ref('');

const value = computed({
    get: () => props.modelValue || '',
    set: (next: string) => emit('update:modelValue', next),
});

const normalizedUrl = computed(() => value.value.trim());

const chooseFile = () => {
    fileInput.value?.click();
};

const uploadFile = async (file: File) => {
    uploading.value = true;
    error.value = '';
    try {
        const response = await api.uploadMediaAssets({
            files: [file],
            kind: props.kind,
            tags_json: JSON.stringify(props.tags || []),
        });
        const uploaded = response.items?.[0];
        if (!uploaded?.url) {
            throw new Error('Загрузка завершилась без URL файла');
        }
        value.value = uploaded.url;
        emit('uploaded', uploaded.url);
    } catch (err) {
        error.value = getApiErrorMessage(err);
    } finally {
        uploading.value = false;
        if (fileInput.value) fileInput.value.value = '';
    }
};

const onFileChange = async (event: Event) => {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    await uploadFile(file);
};

const clearValue = () => {
    value.value = '';
    error.value = '';
};
</script>

<template>
    <div class="space-y-2">
        <div class="flex items-center justify-between gap-3">
            <span class="text-sm font-medium text-gray-600 dark:text-slate-300">{{ label }}</span>
            <div class="inline-flex items-center gap-1">
                <button
                    type="button"
                    class="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-gray-200 text-gray-600 transition-colors hover:bg-gray-50 hover:text-teal-700 disabled:cursor-wait disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-teal-200"
                    :disabled="uploading"
                    title="Загрузить файл"
                    aria-label="Загрузить файл"
                    @click="chooseFile"
                >
                    <span class="material-icons-round text-[18px]">upload</span>
                </button>
                <button
                    v-if="normalizedUrl"
                    type="button"
                    class="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-gray-200 text-gray-500 transition-colors hover:bg-gray-50 hover:text-red-600 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-800"
                    title="Очистить"
                    aria-label="Очистить"
                    @click="clearValue"
                >
                    <span class="material-icons-round text-[18px]">close</span>
                </button>
            </div>
        </div>

        <input
            ref="fileInput"
            type="file"
            class="hidden"
            :accept="accept"
            @change="onFileChange"
        />

        <div class="grid grid-cols-1 gap-3 sm:grid-cols-[96px_1fr]">
            <div class="flex h-24 w-full items-center justify-center overflow-hidden rounded-lg border border-gray-200 bg-white dark:border-slate-700 dark:bg-slate-950 sm:w-24">
                <img
                    v-if="normalizedUrl"
                    :src="normalizedUrl"
                    :alt="label"
                    class="max-h-full max-w-full object-contain"
                />
                <span v-else class="material-icons-round text-[28px] text-gray-300 dark:text-slate-600">image</span>
            </div>
            <label class="min-w-0 text-sm">
                <input
                    v-model="value"
                    type="text"
                    :placeholder="placeholder"
                    class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
                />
                <span v-if="uploading" class="mt-1 block text-xs font-medium text-teal-700 dark:text-teal-300">
                    Загрузка...
                </span>
                <span v-if="error" class="mt-1 block text-xs font-medium text-red-600 dark:text-red-300">
                    {{ error }}
                </span>
            </label>
        </div>
    </div>
</template>
