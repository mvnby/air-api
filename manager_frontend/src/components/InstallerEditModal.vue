<script setup lang="ts">
import { ref, watch } from 'vue';
import { api } from '../api';
import type { ManagerInstallerResponse } from '../client';
import { getApiErrorMessage } from '../utils/api-errors';

const props = defineProps<{
    modelValue: boolean;
    installer?: ManagerInstallerResponse | null;
}>();

const emit = defineEmits<{
    (e: 'update:modelValue', value: boolean): void;
    (e: 'success'): void;
}>();

const loading = ref(false);
const error = ref('');

const formData = ref({
    name: '',
    default_rate: null as number | null,
    telegram_id: null as number | null,
    is_active: true,
});

watch(() => props.modelValue, (val) => {
    if (val) {
        if (props.installer) {
            formData.value = {
                name: props.installer.name,
                default_rate: props.installer.default_rate ?? null,
                telegram_id: props.installer.telegram_id ?? null,
                is_active: props.installer.is_active ?? true,
            };
        } else {
            formData.value = {
                name: '',
                default_rate: null,
                telegram_id: null,
                is_active: true,
            };
        }
        error.value = '';
    }
});

const close = () => {
    if (!loading.value) {
        emit('update:modelValue', false);
    }
};

const submit = async () => {
    if (!formData.value.name.trim()) {
        error.value = 'Имя обязательно';
        return;
    }
    
    loading.value = true;
    error.value = '';
    try {
        if (props.installer?.id) {
            await api.updateManagerInstaller(props.installer.id, formData.value);
        } else {
            await api.createManagerInstaller(formData.value);
        }
        emit('success');
        close();
    } catch (e) {
        error.value = getApiErrorMessage(e);
    } finally {
        loading.value = false;
    }
};
</script>

<template>
    <Teleport to="body">
        <Transition name="modal-fade">
            <div v-if="modelValue" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" @click.self="close">
                <div class="modal-content bg-white dark:bg-[#1e293b] rounded-xl shadow-xl w-full max-w-md overflow-hidden border border-gray-200 dark:border-slate-700/60 flex flex-col">
                    <div class="px-6 py-4 border-b border-gray-200 dark:border-slate-700/50 flex justify-between items-center bg-gray-50 dark:bg-slate-800/50">
                        <h3 class="text-lg font-semibold text-gray-900 dark:text-white">
                            {{ installer ? 'Редактировать сотрудника' : 'Новый сотрудник' }}
                        </h3>
                        <button @click="close" class="text-gray-400 hover:text-gray-600 dark:text-slate-400 dark:hover:text-white transition-colors" :disabled="loading">
                            <span class="material-icons-round text-xl">close</span>
                        </button>
                    </div>

                    <div class="p-6 space-y-4">
                        <div v-if="error" class="p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-500/50 rounded-lg text-sm text-red-600 dark:text-red-400">
                            {{ error }}
                        </div>

                        <div>
                            <label class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Имя сотрудника или бригады *</label>
                            <input
                                v-model="formData.name"
                                type="text"
                                class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-teal-500 transition-colors"
                                placeholder="Иван Иванов"
                                :disabled="loading"
                            />
                        </div>

                        <div>
                            <label class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Базовая ставка (BYN)</label>
                            <input
                                v-model.number="formData.default_rate"
                                type="number"
                                class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-teal-500 transition-colors"
                                placeholder="Например, 350"
                                :disabled="loading"
                            />
                        </div>

                        <div>
                            <label class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Telegram ID (опционально)</label>
                            <input
                                v-model.number="formData.telegram_id"
                                type="number"
                                class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-teal-500 transition-colors"
                                placeholder="Например, 123456789"
                                :disabled="loading"
                            />
                        </div>

                        <label class="flex items-center gap-3 cursor-pointer pt-2 group" :class="{'opacity-50': loading}">
                            <div class="relative">
                                <input type="checkbox" v-model="formData.is_active" class="sr-only" :disabled="loading" />
                                <div class="w-10 h-6 bg-gray-300 dark:bg-slate-600 rounded-full transition-colors duration-200"
                                     :class="{'bg-teal-500': formData.is_active}"></div>
                                <div class="absolute left-1 top-1 w-4 h-4 bg-white rounded-full transition-transform duration-200"
                                     :class="{'translate-x-4': formData.is_active}"></div>
                            </div>
                            <span class="text-sm font-medium text-gray-700 dark:text-slate-300 group-hover:text-gray-900 dark:group-hover:text-white transition-colors">
                                Активен (доступен для новых назначений)
                            </span>
                        </label>
                    </div>

                    <div class="px-6 py-4 border-t border-gray-200 dark:border-slate-700/50 bg-gray-50 dark:bg-slate-800/30 flex justify-end gap-3">
                        <button
                            @click="close"
                            class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-slate-300 hover:text-gray-900 dark:hover:text-white bg-transparent hover:bg-gray-200 dark:hover:bg-slate-700 transition-colors rounded-lg"
                            :disabled="loading"
                        >
                            Отмена
                        </button>
                        <button
                            @click="submit"
                            class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-teal-600 hover:bg-teal-500 active:bg-teal-700 transition-colors rounded-lg disabled:opacity-50 shadow-lg shadow-teal-900/30"
                            :disabled="loading || !formData.name.trim()"
                        >
                            <span v-if="loading" class="material-icons-round text-sm animate-spin">refresh</span>
                            <span v-else class="material-icons-round text-sm">save</span>
                            Сохранить
                        </button>
                    </div>
                </div>
            </div>
        </Transition>
    </Teleport>
</template>

<style scoped>
.modal-fade-enter-active,
.modal-fade-leave-active {
    transition: opacity 0.2s ease;
}
.modal-fade-enter-from,
.modal-fade-leave-to {
    opacity: 0;
}
.modal-fade-enter-active .modal-content,
.modal-fade-leave-active .modal-content {
    transition: transform 0.2s ease;
}
.modal-fade-enter-from .modal-content,
.modal-fade-leave-to .modal-content {
    transform: scale(0.95);
}
</style>
