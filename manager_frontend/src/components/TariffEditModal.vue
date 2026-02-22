<script setup lang="ts">
import { ref, watch } from 'vue';
import { api } from '../api';
import type { ManagerTariffResponse, ManagerTariffCreatePayload, ManagerTariffUpdatePayload } from '../client';
import { getApiErrorMessage } from '../utils/api-errors';

const props = defineProps<{
    modelValue: boolean;
    tariff?: ManagerTariffResponse | null;
}>();

const emit = defineEmits<{
    (e: 'update:modelValue', value: boolean): void;
    (e: 'success'): void;
}>();

const loading = ref(false);
const error = ref('');

const formData = ref<ManagerTariffCreatePayload>({
    category: '',
    power_range: '',
    base_price: 0,
    extra_pipe_price: 0,
    included_pipe_meters: 3,
    is_fixed: true,
    comment: null
});

watch(() => props.modelValue, (val) => {
    if (val) {
        if (props.tariff) {
            formData.value = {
                category: props.tariff.category,
                power_range: props.tariff.power_range,
                base_price: props.tariff.base_price,
                extra_pipe_price: props.tariff.extra_pipe_price,
                included_pipe_meters: props.tariff.included_pipe_meters,
                is_fixed: props.tariff.is_fixed,
                comment: props.tariff.comment || null,
            };
        } else {
            formData.value = {
                category: '',
                power_range: '',
                base_price: 0,
                extra_pipe_price: 0,
                included_pipe_meters: 3,
                is_fixed: true,
                comment: null
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
    if (!formData.value.category.trim()) {
        error.value = 'Категория обязательна';
        return;
    }
    
    loading.value = true;
    error.value = '';
    try {
        if (props.tariff?.id) {
            const updatePayload: ManagerTariffUpdatePayload = { ...formData.value };
            await api.updateManagerTariff(props.tariff.id, updatePayload);
        } else {
            await api.createManagerTariff(formData.value);
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
                            {{ tariff ? 'Редактировать Тариф' : 'Новый Тариф' }}
                        </h3>
                        <button @click="close" class="text-gray-400 hover:text-gray-600 dark:text-slate-400 dark:hover:text-white transition-colors" :disabled="loading">
                            <span class="material-icons-round text-xl">close</span>
                        </button>
                    </div>

                    <div class="p-6 space-y-4 max-h-[70vh] overflow-y-auto custom-scrollbar">
                        <div v-if="error" class="p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-500/50 rounded-lg text-sm text-red-600 dark:text-red-400">
                            {{ error }}
                        </div>

                        <div>
                            <label class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Категория (например, Установка сплит-системы) *</label>
                            <input
                                v-model="formData.category"
                                type="text"
                                class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-teal-500 transition-colors"
                                placeholder="..."
                                :disabled="loading"
                            />
                        </div>

                        <div>
                            <label class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Диапазон мощности (например, 7-9 BTU)</label>
                            <input
                                v-model="formData.power_range"
                                type="text"
                                class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-teal-500 transition-colors"
                                placeholder="Оставьте пустым если для всех"
                                :disabled="loading"
                            />
                        </div>

                        <div class="grid grid-cols-2 gap-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Базовая цена (BYN)</label>
                                <input
                                    v-model.number="formData.base_price"
                                    type="number"
                                    class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-teal-500 transition-colors"
                                    :disabled="loading"
                                />
                            </div>
                            
                            <div>
                                <label class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Цена доп. метра (BYN)</label>
                                <input
                                    v-model.number="formData.extra_pipe_price"
                                    type="number"
                                    class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-teal-500 transition-colors"
                                    :disabled="loading"
                                />
                            </div>
                        </div>

                        <div>
                            <label class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Включено метров трассы</label>
                            <input
                                v-model.number="formData.included_pipe_meters"
                                type="number"
                                class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-teal-500 transition-colors"
                                :disabled="loading"
                            />
                        </div>

                        <div>
                            <label class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Комментарий (опционально)</label>
                            <textarea
                                v-model="formData.comment"
                                rows="2"
                                class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-teal-500 transition-colors resize-none"
                                placeholder="..."
                                :disabled="loading"
                            ></textarea>
                        </div>

                        <label class="flex items-center gap-3 cursor-pointer pt-2 group" :class="{'opacity-50': loading}">
                            <div class="relative">
                                <input type="checkbox" v-model="formData.is_fixed" class="sr-only" :disabled="loading" />
                                <div class="w-10 h-6 bg-gray-300 dark:bg-slate-600 rounded-full transition-colors duration-200"
                                     :class="{'bg-teal-500': formData.is_fixed}"></div>
                                <div class="absolute left-1 top-1 w-4 h-4 bg-white rounded-full transition-transform duration-200"
                                     :class="{'translate-x-4': formData.is_fixed}"></div>
                            </div>
                            <span class="text-sm font-medium text-gray-700 dark:text-slate-300 group-hover:text-gray-900 dark:group-hover:text-white transition-colors">
                                Фиксированная цена на трассы меньше {{formData.included_pipe_meters}}м
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
                            :disabled="loading || !formData.category.trim()"
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

.custom-scrollbar::-webkit-scrollbar {
    width: 6px;
}
.custom-scrollbar::-webkit-scrollbar-track {
    background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
    background-color: #475569;
    border-radius: 10px;
}
</style>
