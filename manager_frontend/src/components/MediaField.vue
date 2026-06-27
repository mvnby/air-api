<script setup lang="ts">
import { computed, ref } from 'vue';
import {
    ClipboardPaste,
    Download,
    Image as ImageIcon,
    Images,
    Search,
    Trash2,
    UploadCloud,
    X,
} from 'lucide-vue-next';
import { api, type ManagerMediaAssetResponse } from '../api';
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
    picked: [url: string];
}>();

type ClipboardImageItem = {
    types: readonly string[];
    getType: (type: string) => Promise<Blob>;
};

const fileInput = ref<HTMLInputElement | null>(null);
const uploading = ref(false);
const error = ref('');
const pickerOpen = ref(false);
const assets = ref<ManagerMediaAssetResponse[]>([]);
const assetsLoading = ref(false);
const pickerQuery = ref('');
const pickerPage = ref(1);
const pickerPages = ref(1);
const pickerTotal = ref(0);
const remoteUrl = ref('');

const value = computed({
    get: () => props.modelValue || '',
    set: (next: string) => emit('update:modelValue', next),
});

const normalizedUrl = computed(() => value.value.trim());
const canImportCurrentUrl = computed(() => /^https?:\/\//i.test(normalizedUrl.value));

const imageUrl = (path?: string | null) => {
    if (!path) return '';
    if (path.startsWith('http')) return path;
    return path.startsWith('/') ? path : `/${path}`;
};

const mediaErrorMessage = (err: unknown, fallback: string) => {
    const message = getApiErrorMessage(err);
    if (!message) return fallback;
    if (/permission|notallowed|denied/i.test(message)) {
        return 'Браузер не дал прямой доступ к буферу. Нажмите Ctrl+V или Cmd+V на странице.';
    }
    if (/fetch/i.test(message)) {
        return 'API медиатеки недоступен. Проверьте backend и повторите действие.';
    }
    return message;
};

const chooseFile = () => {
    fileInput.value?.click();
};

const pickedUrl = (url: string) => {
    value.value = url;
    emit('picked', url);
};

const rememberUploadedAsset = (asset: ManagerMediaAssetResponse) => {
    assets.value = [asset, ...assets.value.filter((item) => item.id !== asset.id)];
    pickerTotal.value = Math.max(pickerTotal.value + 1, assets.value.length);
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
        pickedUrl(uploaded.url);
        emit('uploaded', uploaded.url);
        rememberUploadedAsset(uploaded);
    } catch (err) {
        error.value = mediaErrorMessage(err, 'Не удалось загрузить файл');
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

const loadAssets = async (page = pickerPage.value) => {
    assetsLoading.value = true;
    error.value = '';
    try {
        pickerPage.value = page;
        const response = await api.listMediaAssets({
            page: pickerPage.value,
            limit: 24,
            q: pickerQuery.value.trim() || null,
            kind: null,
            status: null,
        });
        assets.value = response.items || [];
        pickerTotal.value = response.meta.total;
        pickerPages.value = response.meta.pages || 1;
    } catch (err) {
        error.value = mediaErrorMessage(err, 'Не удалось загрузить медиатеку');
    } finally {
        assetsLoading.value = false;
    }
};

const openPicker = async () => {
    pickerOpen.value = true;
    if (!assets.value.length) {
        await loadAssets(1);
    }
};

const selectAsset = (asset: ManagerMediaAssetResponse) => {
    pickedUrl(asset.url);
    pickerOpen.value = false;
};

const uploadFromUrl = async (urlValue = remoteUrl.value.trim() || normalizedUrl.value) => {
    const url = urlValue.trim();
    if (!url) {
        error.value = 'Укажите URL изображения';
        return;
    }
    if (!/^https?:\/\//i.test(url)) {
        error.value = 'Для скачивания нужна внешняя ссылка http или https';
        return;
    }
    uploading.value = true;
    error.value = '';
    try {
        const response = await api.uploadMediaAssetFromUrl({
            url,
            kind: props.kind,
            tags: props.tags,
        });
        const uploaded = response.items?.[0];
        if (!uploaded?.url) {
            throw new Error('Загрузка завершилась без URL файла');
        }
        pickedUrl(uploaded.url);
        emit('uploaded', uploaded.url);
        remoteUrl.value = '';
        rememberUploadedAsset(uploaded);
    } catch (err) {
        error.value = mediaErrorMessage(err, 'Не удалось загрузить изображение по URL');
    } finally {
        uploading.value = false;
    }
};

const extensionFromMime = (mimeType: string) => mimeType.split('/')[1]?.replace('jpeg', 'jpg') || 'png';

const pasteFromClipboard = async () => {
    const clipboard = navigator.clipboard as Clipboard & { read?: () => Promise<ClipboardImageItem[]> };
    if (!clipboard?.read) {
        error.value = 'Вставьте изображение через Ctrl+V или Cmd+V на странице.';
        return;
    }
    try {
        const items = await clipboard.read();
        for (const item of items) {
            const imageType = item.types.find((type) => type.startsWith('image/'));
            if (!imageType) continue;
            const blob = await item.getType(imageType);
            await uploadFile(new File([blob], `clipboard-${Date.now()}.${extensionFromMime(imageType)}`, { type: imageType }));
            return;
        }
        error.value = 'В буфере нет изображения';
    } catch (err) {
        error.value = mediaErrorMessage(err, 'Не удалось прочитать изображение из буфера');
    }
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
                    title="Выбрать из медиатеки"
                    aria-label="Выбрать из медиатеки"
                    @click="openPicker"
                >
                    <Images class="h-4 w-4" />
                </button>
                <button
                    type="button"
                    class="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-gray-200 text-gray-600 transition-colors hover:bg-gray-50 hover:text-teal-700 disabled:cursor-wait disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-teal-200"
                    :disabled="uploading"
                    title="Загрузить файл"
                    aria-label="Загрузить файл"
                    @click="chooseFile"
                >
                    <UploadCloud class="h-4 w-4" />
                </button>
                <button
                    type="button"
                    class="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-gray-200 text-gray-600 transition-colors hover:bg-gray-50 hover:text-teal-700 disabled:cursor-wait disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-teal-200"
                    :disabled="uploading"
                    title="Вставить из буфера"
                    aria-label="Вставить из буфера"
                    @click="pasteFromClipboard"
                >
                    <ClipboardPaste class="h-4 w-4" />
                </button>
                <button
                    v-if="normalizedUrl"
                    type="button"
                    class="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-gray-200 text-gray-500 transition-colors hover:bg-gray-50 hover:text-red-600 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-800"
                    title="Очистить"
                    aria-label="Очистить"
                    @click="clearValue"
                >
                    <Trash2 class="h-4 w-4" />
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
                    :src="imageUrl(normalizedUrl)"
                    :alt="label"
                    class="max-h-full max-w-full object-contain"
                />
                <ImageIcon v-else class="h-8 w-8 text-gray-300 dark:text-slate-600" />
            </div>
            <label class="min-w-0 text-sm">
                <span class="relative block">
                    <input
                        v-model="value"
                        type="text"
                        :placeholder="placeholder"
                        class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 pr-10 dark:border-slate-700 dark:bg-slate-900"
                        @keydown.enter.prevent="canImportCurrentUrl ? uploadFromUrl() : undefined"
                    />
                    <button
                        v-if="canImportCurrentUrl"
                        type="button"
                        class="absolute right-1 top-1/2 inline-flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md text-teal-700 transition hover:bg-teal-50 disabled:cursor-wait disabled:opacity-50 dark:text-teal-200 dark:hover:bg-teal-950/40"
                        :disabled="uploading"
                        title="Скачать URL в медиатеку"
                        aria-label="Скачать URL в медиатеку"
                        @click="uploadFromUrl()"
                    >
                        <Download class="h-4 w-4" />
                    </button>
                </span>
                <span v-if="uploading" class="mt-1 block text-xs font-medium text-teal-700 dark:text-teal-300">
                    Загрузка...
                </span>
                <span v-if="error" class="mt-1 block text-xs font-medium text-red-600 dark:text-red-300">
                    {{ error }}
                </span>
            </label>
        </div>

        <div
            v-if="pickerOpen"
            class="fixed inset-0 z-[95] flex items-center justify-center bg-slate-950/55 p-3 backdrop-blur-sm"
            @click.self="pickerOpen = false"
        >
            <div class="flex max-h-[88vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900">
                <header class="flex items-center justify-between gap-3 border-b border-gray-200 px-4 py-3 dark:border-slate-700">
                    <div class="min-w-0">
                        <h3 class="text-base font-bold text-gray-900 dark:text-slate-100">Выбор изображения</h3>
                        <p class="text-xs text-gray-500 dark:text-slate-400">Медиатека, загрузка, URL и буфер обмена в одном месте.</p>
                    </div>
                    <button
                        type="button"
                        class="inline-flex h-9 w-9 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-800"
                        aria-label="Закрыть"
                        @click="pickerOpen = false"
                    >
                        <X class="h-5 w-5" />
                    </button>
                </header>

                <div class="space-y-3 border-b border-gray-200 p-4 dark:border-slate-700">
                    <div class="grid grid-cols-1 gap-2 md:grid-cols-[minmax(0,1fr)_auto_auto]">
                        <label class="relative block">
                            <Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                            <input
                                v-model="pickerQuery"
                                type="search"
                                class="w-full rounded-lg border border-gray-200 bg-slate-100 py-2 pl-9 pr-3 text-sm dark:border-slate-700 dark:bg-slate-950"
                                placeholder="Поиск по медиатеке"
                                @keydown.enter.prevent="loadAssets(1)"
                            />
                        </label>
                        <button
                            type="button"
                            class="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-200 px-3 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                            :disabled="assetsLoading"
                            @click="loadAssets(1)"
                        >
                            <Search class="h-4 w-4" />
                            Найти
                        </button>
                        <button
                            type="button"
                            class="inline-flex items-center justify-center gap-2 rounded-lg bg-teal-600 px-3 py-2 text-sm font-semibold text-white hover:bg-teal-700 disabled:cursor-wait disabled:opacity-60"
                            :disabled="uploading"
                            @click="chooseFile"
                        >
                            <UploadCloud class="h-4 w-4" />
                            Загрузить
                        </button>
                    </div>

                    <div class="grid grid-cols-1 gap-2 md:grid-cols-[minmax(0,1fr)_auto_auto]">
                        <input
                            v-model="remoteUrl"
                            type="url"
                            class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
                            placeholder="https://site.by/image.webp"
                            @keydown.enter.prevent="uploadFromUrl(remoteUrl)"
                        />
                        <button
                            type="button"
                            class="inline-flex items-center justify-center gap-2 rounded-lg border border-teal-200 px-3 py-2 text-sm font-semibold text-teal-700 hover:bg-teal-50 disabled:cursor-wait disabled:opacity-60 dark:border-teal-900/70 dark:text-teal-200 dark:hover:bg-teal-950/30"
                            :disabled="uploading"
                            @click="uploadFromUrl(remoteUrl)"
                        >
                            <Download class="h-4 w-4" />
                            Скачать URL
                        </button>
                        <button
                            type="button"
                            class="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-200 px-3 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:cursor-wait disabled:opacity-60 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                            :disabled="uploading"
                            @click="pasteFromClipboard"
                        >
                            <ClipboardPaste class="h-4 w-4" />
                            Вставить
                        </button>
                    </div>
                </div>

                <div class="min-h-0 flex-1 overflow-y-auto p-4">
                    <div v-if="assetsLoading" class="grid grid-cols-2 gap-3 md:grid-cols-4">
                        <div v-for="idx in 8" :key="idx" class="h-40 animate-pulse rounded-xl bg-gray-100 dark:bg-slate-800" />
                    </div>
                    <div v-else-if="!assets.length" class="flex min-h-[260px] items-center justify-center rounded-xl border border-dashed border-gray-300 text-center dark:border-slate-700">
                        <div>
                            <ImageIcon class="mx-auto h-10 w-10 text-gray-300 dark:text-slate-600" />
                            <p class="mt-2 text-sm font-semibold text-gray-900 dark:text-slate-100">Изображений не найдено</p>
                            <p class="mt-1 text-xs text-gray-500 dark:text-slate-400">Загрузите файл или скачайте картинку по URL.</p>
                        </div>
                    </div>
                    <div v-else class="grid grid-cols-2 gap-3 md:grid-cols-4">
                        <button
                            v-for="asset in assets"
                            :key="asset.id"
                            type="button"
                            class="group overflow-hidden rounded-xl border bg-white text-left shadow-sm transition hover:-translate-y-0.5 hover:border-teal-400 hover:shadow-md dark:bg-slate-950"
                            :class="asset.url === normalizedUrl ? 'border-teal-500 ring-2 ring-teal-500/20' : 'border-gray-200 dark:border-slate-700'"
                            @click="selectAsset(asset)"
                        >
                            <span class="flex aspect-[4/3] items-center justify-center bg-gray-100 dark:bg-slate-900">
                                <img :src="imageUrl(asset.url)" :alt="asset.alt_text || asset.title" class="h-full w-full object-contain" loading="lazy" />
                            </span>
                            <span class="block space-y-1 p-2">
                                <span class="block truncate text-xs font-semibold text-gray-900 dark:text-slate-100">{{ asset.title || asset.source_filename || asset.url }}</span>
                                <span class="block truncate text-[11px] text-gray-500 dark:text-slate-400">{{ asset.width || 0 }}×{{ asset.height || 0 }} · {{ asset.kind }}</span>
                            </span>
                        </button>
                    </div>
                </div>

                <footer class="flex items-center justify-between gap-3 border-t border-gray-200 px-4 py-3 text-sm text-gray-500 dark:border-slate-700 dark:text-slate-400">
                    <span>Найдено: {{ pickerTotal }}</span>
                    <div class="flex items-center gap-2">
                        <button
                            type="button"
                            class="rounded-lg border border-gray-200 px-3 py-1.5 disabled:opacity-50 dark:border-slate-700"
                            :disabled="pickerPage <= 1 || assetsLoading"
                            @click="loadAssets(pickerPage - 1)"
                        >
                            Назад
                        </button>
                        <span>{{ pickerPage }} / {{ pickerPages }}</span>
                        <button
                            type="button"
                            class="rounded-lg border border-gray-200 px-3 py-1.5 disabled:opacity-50 dark:border-slate-700"
                            :disabled="pickerPage >= pickerPages || assetsLoading"
                            @click="loadAssets(pickerPage + 1)"
                        >
                            Вперёд
                        </button>
                    </div>
                </footer>
            </div>
        </div>
    </div>
</template>
