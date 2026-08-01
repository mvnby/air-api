<script setup lang="ts">
import { ref } from 'vue';

import {
  loginManagerWithPassword,
  managerSession,
  requireManagerSessionRecovery,
} from '../../services/manager-session';

const props = defineProps<{ reloadPage?: () => void }>();
const { recoveryRequired } = managerSession;

const username = ref('');
const password = ref('');
const loading = ref(false);
const error = ref('');

const reloadPage = () => {
  const reload = props.reloadPage ?? (() => window.location.reload());
  reload();
};

const handleLogin = async () => {
  if (loading.value) return;
  loading.value = true;
  error.value = '';
  try {
    await loginManagerWithPassword(username.value, password.value);
  } catch {
    requireManagerSessionRecovery();
    error.value = 'Неверный логин или пароль';
    loading.value = false;
    return;
  }
  reloadPage();
};
</script>

<template>
  <div
    v-if="recoveryRequired"
    class="fixed inset-0 z-[120] flex items-center justify-center bg-black/70 p-4"
    role="dialog"
    aria-modal="true"
    aria-labelledby="manager-session-recovery-title"
  >
    <form
      class="w-full max-w-sm rounded-[2rem] border border-gray-200 bg-white p-6 text-gray-700 shadow-2xl"
      @submit.prevent="handleLogin"
    >
      <h2 id="manager-session-recovery-title" class="mb-2 text-xl font-semibold">
        Сессия завершилась
      </h2>
      <p class="mb-4 text-sm text-gray-500">
        Войдите снова. Данные предыдущей сессии уже очищены.
      </p>
      <div class="space-y-3">
        <label class="block">
          <span class="sr-only">Логин</span>
          <input
            v-model="username"
            class="field-input"
            placeholder="Логин"
            autocomplete="username"
            autofocus
          />
        </label>
        <label class="block">
          <span class="sr-only">Пароль</span>
          <input
            v-model="password"
            type="password"
            class="field-input"
            placeholder="Пароль"
            autocomplete="current-password"
          />
        </label>
        <p v-if="error" class="text-sm text-red-600" role="alert">{{ error }}</p>
        <button class="btn-mini w-full justify-center" type="submit" :disabled="loading">
          {{ loading ? 'Входим...' : 'Войти' }}
        </button>
      </div>
    </form>
  </div>
</template>
