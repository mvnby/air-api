<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ExternalLink, HelpCircle, Loader2, ShieldCheck, X } from 'lucide-vue-next';

import type { AnalyticsConnectionItem, YandexMetrikaConnectionUpsertPayload } from '../../client';

const props = defineProps<{
  open: boolean;
  mode: 'configure' | 'help';
  connection: AnalyticsConnectionItem | null;
  saving: boolean;
  error: string;
}>();
const emit = defineEmits<{
  close: [];
  save: [payload: YandexMetrikaConnectionUpsertPayload];
  changeMode: [mode: 'configure' | 'help'];
}>();

const counterId = ref('');
const oauthToken = ref('');
const connected = computed(() => props.connection?.state === 'connected');

watch(
  () => [props.open, props.connection] as const,
  ([isOpen, connection]) => {
    if (!isOpen) return;
    counterId.value = connection?.counter_id || '';
    oauthToken.value = '';
  },
  { immediate: true },
);

const submit = () => {
  const payload: YandexMetrikaConnectionUpsertPayload = {
    counter_id: counterId.value.trim(),
  };
  const token = oauthToken.value.trim();
  if (token) payload.oauth_token = token;
  emit('save', payload);
};
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-[120] flex items-center justify-center bg-slate-950/55 p-4" @click.self="$emit('close')">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="metrika-dialog-title"
        class="w-full max-w-xl overflow-hidden rounded-3xl bg-white shadow-2xl dark:bg-slate-900"
      >
        <header class="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-5 dark:border-slate-800">
          <div>
            <p class="text-xs font-bold uppercase tracking-[0.16em] text-teal-600">Яндекс Метрика</p>
            <h2 id="metrika-dialog-title" class="mt-1 text-xl font-bold text-slate-950 dark:text-white">
              {{ mode === 'help' ? 'Где взять данные для подключения' : 'Подключение счётчика' }}
            </h2>
          </div>
          <button type="button" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200" aria-label="Закрыть" @click="$emit('close')">
            <X class="h-5 w-5" />
          </button>
        </header>

        <div v-if="mode === 'help'" data-testid="metrika-help" class="space-y-5 px-6 py-6">
          <ol class="space-y-4 text-sm leading-6 text-slate-600 dark:text-slate-300">
            <li class="flex gap-3"><span class="step">1</span><span>Откройте нужный счётчик в Яндекс Метрике и скопируйте его числовой ID.</span></li>
            <li class="flex gap-3"><span class="step">2</span><span>Создайте приложение в Яндекс OAuth и разрешите чтение статистики Метрики: <strong class="text-slate-900 dark:text-white">metrika:read</strong>.</span></li>
            <li class="flex gap-3"><span class="step">3</span><span>Получите OAuth-токен под аккаунтом, у которого есть доступ к этому счётчику.</span></li>
          </ol>
          <div class="rounded-2xl border border-teal-100 bg-teal-50 p-4 text-sm text-teal-900 dark:border-teal-900 dark:bg-teal-950/40 dark:text-teal-100">
            <div class="flex gap-3">
              <ShieldCheck class="mt-0.5 h-5 w-5 shrink-0" />
              <p>Токен хранится в зашифрованном виде и никогда не показывается обратно в интерфейсе.</p>
            </div>
          </div>
          <div class="flex flex-wrap gap-3">
            <a
              href="https://yandex.ru/dev/metrika/ru/intro/authorization"
              target="_blank"
              rel="noopener noreferrer"
              class="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              Инструкция Яндекса <ExternalLink class="h-4 w-4" />
            </a>
            <button type="button" class="rounded-xl bg-teal-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-teal-700" @click="$emit('changeMode', 'configure')">
              Перейти к подключению
            </button>
          </div>
        </div>

        <form v-else class="space-y-5 px-6 py-6" @submit.prevent="submit">
          <label class="block">
            <span class="text-sm font-semibold text-slate-800 dark:text-slate-200">ID счётчика</span>
            <input
              v-model="counterId"
              data-testid="metrika-counter-id"
              inputmode="numeric"
              pattern="[0-9]+"
              required
              class="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-100 dark:border-slate-700 dark:bg-slate-950 dark:text-white dark:focus:ring-teal-950"
              placeholder="Например, 12345678"
            >
          </label>
          <label class="block">
            <span class="flex items-center justify-between gap-3 text-sm font-semibold text-slate-800 dark:text-slate-200">
              OAuth-токен
              <button type="button" class="inline-flex items-center gap-1 text-xs text-teal-700 hover:text-teal-800" @click="$emit('changeMode', 'help')">
                <HelpCircle class="h-4 w-4" /> Где взять?
              </button>
            </span>
            <input
              v-model="oauthToken"
              data-testid="metrika-oauth-token"
              type="password"
              :required="!connected"
              autocomplete="new-password"
              class="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-100 dark:border-slate-700 dark:bg-slate-950 dark:text-white dark:focus:ring-teal-950"
              :placeholder="connected ? 'Оставьте пустым, чтобы сохранить текущий токен' : 'Вставьте OAuth-токен'"
            >
          </label>
          <p v-if="error" role="alert" class="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{{ error }}</p>
          <div class="flex justify-end gap-3 border-t border-slate-100 pt-5 dark:border-slate-800">
            <button type="button" class="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800" @click="$emit('close')">Отмена</button>
            <button
              data-testid="metrika-save"
              type="submit"
              class="inline-flex items-center gap-2 rounded-xl bg-teal-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="saving"
            >
              <Loader2 v-if="saving" class="h-4 w-4 animate-spin" />
              {{ saving ? 'Проверяем...' : 'Проверить и сохранить' }}
            </button>
          </div>
        </form>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.step {
  @apply flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white;
}
</style>
