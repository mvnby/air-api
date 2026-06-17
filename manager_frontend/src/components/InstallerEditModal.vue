<script setup lang="ts">
import { ref, watch } from 'vue';
import { api, type ManagerStaffCreatePayload, type ManagerStaffResponse, type ManagerStaffUpdatePayload } from '../api';
import { getApiErrorMessage } from '../utils/api-errors';

const props = defineProps<{
    modelValue: boolean;
    staffUser?: ManagerStaffResponse | null;
}>();

const emit = defineEmits<{
    (e: 'update:modelValue', value: boolean): void;
    (e: 'success'): void;
}>();

const loading = ref(false);
const error = ref('');

const formData = ref({
    display_name: '',
    primary_role: 'installer',
    status: 'active',
    username: '',
    password: '',
    phone: '',
    email: '',
    telegram_id: null as number | null,
    telegram_username: '',
    is_assignable_installer: false,
    default_rate: null as number | null,
});

watch(() => props.modelValue, (val) => {
    if (!val) return;
    if (props.staffUser) {
        formData.value = {
            display_name: props.staffUser.display_name,
            primary_role: props.staffUser.primary_role || 'installer',
            status: props.staffUser.status || 'active',
            username: props.staffUser.username || '',
            password: '',
            phone: props.staffUser.phone || '',
            email: props.staffUser.email || '',
            telegram_id: props.staffUser.telegram_id ?? null,
            telegram_username: props.staffUser.telegram_username || '',
            is_assignable_installer: props.staffUser.is_assignable_installer ?? false,
            default_rate: props.staffUser.default_rate ?? null,
        };
    } else {
        formData.value = {
            display_name: '',
            primary_role: 'installer',
            status: 'active',
            username: '',
            password: '',
            phone: '',
            email: '',
            telegram_id: null,
            telegram_username: '',
            is_assignable_installer: false,
            default_rate: null,
        };
    }
    error.value = '';
});

const close = () => {
    if (!loading.value) emit('update:modelValue', false);
};

const nullableText = (value: string) => {
    const trimmed = value.trim();
    return trimmed ? trimmed : null;
};

const buildPayload = (): ManagerStaffCreatePayload | ManagerStaffUpdatePayload => ({
    display_name: formData.value.display_name.trim(),
    primary_role: formData.value.primary_role,
    status: formData.value.status,
    username: nullableText(formData.value.username),
    password: formData.value.password.trim() || null,
    phone: nullableText(formData.value.phone),
    email: nullableText(formData.value.email),
    telegram_id: formData.value.telegram_id,
    telegram_username: nullableText(formData.value.telegram_username.replace(/^@/, '')),
    is_assignable_installer: formData.value.is_assignable_installer,
    default_rate: formData.value.default_rate,
});

const submit = async () => {
    if (!formData.value.display_name.trim()) {
        error.value = 'Имя сотрудника обязательно';
        return;
    }

    loading.value = true;
    error.value = '';
    try {
        const payload = buildPayload();
        if (props.staffUser?.id) {
            await api.patchManagerStaff(props.staffUser.id, payload);
        } else {
            await api.createManagerStaff(payload as ManagerStaffCreatePayload);
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
                <div class="modal-content bg-white dark:bg-[#1e293b] rounded-xl shadow-xl w-full max-w-3xl max-h-[92vh] overflow-hidden border border-gray-200 dark:border-slate-700/60 flex flex-col">
                    <div class="px-6 py-4 border-b border-gray-200 dark:border-slate-700/50 flex justify-between items-center bg-gray-50 dark:bg-slate-800/50">
                        <div>
                            <h3 class="text-lg font-semibold text-gray-900 dark:text-white">
                                {{ staffUser ? 'Редактировать сотрудника' : 'Новый сотрудник' }}
                            </h3>
                            <p class="text-xs text-gray-500 dark:text-slate-400">Профиль, доступ в менеджер и Telegram</p>
                        </div>
                        <button @click="close" class="text-gray-400 hover:text-gray-600 dark:text-slate-400 dark:hover:text-white transition-colors" :disabled="loading">
                            <span class="material-icons-round text-xl">close</span>
                        </button>
                    </div>

                    <div class="p-6 space-y-6 overflow-y-auto">
                        <div v-if="error" class="p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-500/50 rounded-lg text-sm text-red-600 dark:text-red-400">
                            {{ error }}
                        </div>

                        <section class="space-y-3">
                            <h4 class="text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">Профиль</h4>
                            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <label class="block">
                                    <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Имя сотрудника *</span>
                                    <input v-model="formData.display_name" type="text" class="field-input" placeholder="Иван Иванов" :disabled="loading" />
                                </label>

                                <label class="block">
                                    <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Роль</span>
                                    <select v-model="formData.primary_role" class="field-input" :disabled="loading">
                                        <option value="owner">Владелец</option>
                                        <option value="manager">Менеджер</option>
                                        <option value="installer">Монтажник</option>
                                    </select>
                                </label>

                                <label class="block">
                                    <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Телефон</span>
                                    <input v-model="formData.phone" type="text" class="field-input" placeholder="+375... или +7..." :disabled="loading" />
                                </label>

                                <label class="block">
                                    <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Email</span>
                                    <input v-model="formData.email" type="email" class="field-input" placeholder="name@example.com" :disabled="loading" />
                                </label>
                            </div>
                        </section>

                        <section class="space-y-3">
                            <h4 class="text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">Доступ в менеджер</h4>
                            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <label class="block">
                                    <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Логин</span>
                                    <input v-model="formData.username" type="text" autocomplete="username" class="field-input" placeholder="ivan" :disabled="loading" />
                                </label>

                                <label class="block">
                                    <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Новый пароль</span>
                                    <input v-model="formData.password" type="password" autocomplete="new-password" class="field-input" :placeholder="staffUser?.has_password ? 'Оставьте пустым, чтобы не менять' : 'Минимум 6 символов'" :disabled="loading" />
                                </label>
                            </div>
                        </section>

                        <section class="space-y-3">
                            <h4 class="text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">Telegram</h4>
                            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <label class="block">
                                    <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Telegram ID</span>
                                    <input v-model.number="formData.telegram_id" type="number" class="field-input" placeholder="123456789" :disabled="loading" />
                                </label>

                                <label class="block">
                                    <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Username</span>
                                    <input v-model="formData.telegram_username" type="text" class="field-input" placeholder="@username" :disabled="loading" />
                                </label>
                            </div>
                        </section>

                        <section class="space-y-3">
                            <h4 class="text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">Работы и статус</h4>
                            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <label class="block">
                                    <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Статус</span>
                                    <select v-model="formData.status" class="field-input" :disabled="loading">
                                        <option value="active">Активен</option>
                                        <option value="inactive">В архиве</option>
                                        <option value="blocked">Заблокирован</option>
                                    </select>
                                </label>

                                <label class="block">
                                    <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Базовая ставка, BYN</span>
                                    <input v-model.number="formData.default_rate" type="number" class="field-input" placeholder="Например, 350" :disabled="loading || !formData.is_assignable_installer" />
                                </label>
                            </div>

                            <label class="flex items-start gap-3 cursor-pointer pt-1 group" :class="{ 'opacity-50': loading }">
                                <input type="checkbox" v-model="formData.is_assignable_installer" class="mt-1 h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500" :disabled="loading" />
                                <span>
                                    <span class="block text-sm font-medium text-gray-700 dark:text-slate-300">Можно назначать на работы</span>
                                    <span class="block text-xs text-gray-500 dark:text-slate-500">Для такого сотрудника сохраняется совместимость с монтажниками в заказах и календаре.</span>
                                </span>
                            </label>
                        </section>
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
                            :disabled="loading || !formData.display_name.trim()"
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
.field-input {
    width: 100%;
    border-radius: 0.5rem;
    border: 1px solid rgb(209 213 219);
    background: rgb(255 255 255);
    padding: 0.5rem 0.75rem;
    color: rgb(17 24 39);
    outline: none;
    transition: border-color 0.15s ease, box-shadow 0.15s ease, opacity 0.15s ease;
}
.field-input:focus {
    border-color: rgb(20 184 166);
    box-shadow: 0 0 0 3px rgb(20 184 166 / 0.12);
}
.field-input:disabled {
    opacity: 0.6;
}
:global(.dark) .field-input {
    border-color: rgb(71 85 105);
    background: rgb(15 23 42);
    color: rgb(226 232 240);
}
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
