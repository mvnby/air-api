<script setup lang="ts">
import { Package } from 'lucide-vue-next';

defineProps<{
  username: string;
  password: string;
  loading: boolean;
  error: string;
  telegramEnabled: boolean;
  telegramLoading: boolean;
}>();

const emit = defineEmits<{
  'update:username': [value: string];
  'update:password': [value: string];
  submit: [];
}>();
</script>

<template>
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
    role="dialog"
    aria-modal="true"
    aria-labelledby="manager-login-title"
  >
    <div class="mx-4 w-full max-w-md rounded-xl bg-white p-8 shadow-2xl">
      <div class="mb-6 flex justify-center">
        <div class="flex h-12 w-12 items-center justify-center rounded-xl bg-teal-600">
          <Package class="h-6 w-6 text-white" />
        </div>
      </div>
      <h2 id="manager-login-title" class="mb-6 text-center text-2xl font-bold text-gray-900">
        Вход в менеджер
      </h2>
      <form class="space-y-4" @submit.prevent="emit('submit')">
        <div>
          <label class="mb-1 block text-sm font-medium text-gray-700" for="manager-login-username">
            Логин
          </label>
          <input
            id="manager-login-username"
            :value="username"
            type="text"
            required
            autocomplete="username"
            class="w-full rounded-lg border border-gray-300 px-4 py-2.5 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-teal-500"
            placeholder="Введите логин"
            @input="emit('update:username', ($event.target as HTMLInputElement).value)"
          />
        </div>
        <div>
          <label class="mb-1 block text-sm font-medium text-gray-700" for="manager-login-password">
            Пароль
          </label>
          <input
            id="manager-login-password"
            :value="password"
            type="password"
            required
            autocomplete="current-password"
            class="w-full rounded-lg border border-gray-300 px-4 py-2.5 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-teal-500"
            placeholder="Введите пароль"
            @input="emit('update:password', ($event.target as HTMLInputElement).value)"
          />
        </div>
        <div v-if="error" class="text-sm text-red-600" role="alert">{{ error }}</div>
        <button
          type="submit"
          :disabled="loading"
          class="w-full rounded-lg bg-teal-600 py-2.5 font-medium text-white transition-colors hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {{ loading ? 'Входим...' : 'Войти' }}
        </button>
        <div v-if="telegramEnabled" class="pt-2">
          <div class="mb-3 flex items-center gap-3 text-xs uppercase tracking-[0.18em] text-gray-400">
            <span class="h-px flex-1 bg-gray-200" />
            <span>или</span>
            <span class="h-px flex-1 bg-gray-200" />
          </div>
          <div
            class="flex min-h-[44px] justify-center"
            :class="telegramLoading ? 'pointer-events-none opacity-60' : ''"
          >
            <slot name="telegram" />
          </div>
        </div>
      </form>
    </div>
  </div>
</template>
