<script setup lang="ts">
import KitlanePlatformBrand from '../kitlane/KitlanePlatformBrand.vue';

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
    class="kitlane-login fixed inset-0 z-50 flex items-center justify-center"
    role="dialog"
    aria-modal="true"
    aria-labelledby="manager-login-title"
  >
    <div class="kitlane-login-card mx-4 w-full max-w-md rounded-xl p-6 sm:p-8">
      <div class="mb-6 flex justify-center">
        <KitlanePlatformBrand :attribution="false" />
      </div>
      <h2 id="manager-login-title" class="mb-6 text-center text-2xl font-bold text-[var(--kitlane-text)]">
        Вход в менеджер
      </h2>
      <form class="space-y-4" @submit.prevent="emit('submit')">
        <div>
          <label class="mb-1 block text-sm font-medium text-[var(--kitlane-text)]" for="manager-login-username">
            Логин
          </label>
          <input
            id="manager-login-username"
            :value="username"
            type="text"
            required
            autocomplete="username"
            class="field-input"
            placeholder="Введите логин"
            @input="emit('update:username', ($event.target as HTMLInputElement).value)"
          />
        </div>
        <div>
          <label class="mb-1 block text-sm font-medium text-[var(--kitlane-text)]" for="manager-login-password">
            Пароль
          </label>
          <input
            id="manager-login-password"
            :value="password"
            type="password"
            required
            autocomplete="current-password"
            class="field-input"
            placeholder="Введите пароль"
            @input="emit('update:password', ($event.target as HTMLInputElement).value)"
          />
        </div>
        <div v-if="error" class="text-sm text-red-600" role="alert">{{ error }}</div>
        <button
          type="submit"
          :disabled="loading"
          class="btn-mini w-full justify-center py-2.5"
        >
          {{ loading ? 'Входим...' : 'Войти' }}
        </button>
        <div v-if="telegramEnabled" class="pt-2">
          <div class="mb-3 flex items-center gap-3 text-xs uppercase tracking-[0.18em] text-[var(--kitlane-muted)]">
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

<style scoped>
.kitlane-login { background: var(--kitlane-bg); overflow-y: auto; padding-block: 24px; }
.kitlane-login-card { background: var(--kitlane-surface); color: var(--kitlane-text); border: 1px solid var(--kitlane-border); }
</style>
