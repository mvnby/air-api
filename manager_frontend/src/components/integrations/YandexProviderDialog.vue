<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ExternalLink, HelpCircle, Loader2, ShieldCheck, X } from 'lucide-vue-next';

import type {
  AnalyticsConnectionItem,
  YandexDirectConnectionUpsertPayload,
  YandexWebmasterConnectionUpsertPayload,
} from '../../client';

type YandexProvider = 'yandex_direct' | 'yandex_webmaster';
type SavePayload = YandexDirectConnectionUpsertPayload | YandexWebmasterConnectionUpsertPayload;

const props = defineProps<{
  open: boolean;
  mode: 'configure' | 'help';
  connection: AnalyticsConnectionItem | null;
  saving: boolean;
  error: string;
}>();
const emit = defineEmits<{
  close: [];
  save: [provider: YandexProvider, payload: SavePayload];
  changeMode: [mode: 'configure' | 'help'];
}>();

const oauthToken = ref('');
const clientLogin = ref('');
const provider = computed<YandexProvider | null>(() => {
  const value = props.connection?.provider;
  return value === 'yandex_direct' || value === 'yandex_webmaster' ? value : null;
});
const isDirect = computed(() => provider.value === 'yandex_direct');
const providerName = computed(() => isDirect.value ? 'Яндекс Директ' : 'Яндекс Вебмастер');
const helpUrl = computed(() => (
  isDirect.value
    ? 'https://yandex.ru/dev/direct/doc/ru/concepts/register'
    : 'https://yandex.ru/dev/webmaster/doc/ru/tasks/how-to-get-oauth'
));

watch(
  () => [props.open, props.connection] as const,
  ([isOpen, connection]) => {
    if (!isOpen) return;
    oauthToken.value = '';
    clientLogin.value = connection?.configuration?.client_login || '';
  },
  { immediate: true },
);

const submit = () => {
  if (!provider.value) return;
  const token = oauthToken.value.trim();
  const payload: SavePayload = isDirect.value
    ? {
      client_login: clientLogin.value.trim() || null,
      ...(token ? { oauth_token: token } : {}),
    }
    : (token ? { oauth_token: token } : {});
  emit('save', provider.value, payload);
};
</script>

<template>
  <Teleport to="body">
    <div v-if="open && provider" class="fixed inset-0 z-[120] flex items-center justify-center bg-slate-950/55 p-4" @click.self="$emit('close')">
      <section role="dialog" aria-modal="true" aria-labelledby="yandex-provider-dialog-title" class="w-full max-w-xl overflow-hidden rounded-3xl bg-white shadow-2xl dark:bg-slate-900">
        <header class="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-5 dark:border-slate-800">
          <div>
            <p class="text-xs font-bold uppercase tracking-[0.16em] text-teal-600">{{ providerName }}</p>
            <h2 id="yandex-provider-dialog-title" class="mt-1 text-xl font-bold text-slate-950 dark:text-white">{{ mode === 'help' ? 'Где взять доступ' : 'Подключение' }}</h2>
          </div>
          <button type="button" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200" aria-label="Закрыть" @click="$emit('close')"><X class="h-5 w-5" /></button>
        </header>

        <div v-if="mode === 'help'" data-testid="yandex-provider-help" class="space-y-5 px-6 py-6">
          <ol class="space-y-4 text-sm leading-6 text-slate-600 dark:text-slate-300">
            <li class="flex gap-3"><span class="step">1</span><span>Откройте Яндекс OAuth под аккаунтом, который имеет доступ к нужному {{ isDirect ? 'рекламному кабинету' : 'сайту' }}.</span></li>
            <li class="flex gap-3"><span class="step">2</span><span v-if="isDirect">Получите OAuth-токен с доступом <strong class="text-slate-900 dark:text-white">direct:api</strong>. Для реальной статистики приложению нужен одобренный полный доступ к API Директа.</span><span v-else>Получите OAuth-токен с разрешением на чтение данных Яндекс Вебмастера и убедитесь, что сайт филиала подтверждён.</span></li>
            <li v-if="isDirect" class="flex gap-3"><span class="step">3</span><span>Если работаете через агентство, укажите логин рекламодателя в поле «Логин клиента».</span></li>
          </ol>
          <div class="rounded-2xl border border-teal-100 bg-teal-50 p-4 text-sm text-teal-900 dark:border-teal-900 dark:bg-teal-950/40 dark:text-teal-100"><div class="flex gap-3"><ShieldCheck class="mt-0.5 h-5 w-5 shrink-0" /><p>Токен хранится зашифрованно и не отображается в CRM.</p></div></div>
          <div class="flex flex-wrap gap-3">
            <a :href="helpUrl" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800">Инструкция Яндекса <ExternalLink class="h-4 w-4" /></a>
            <button type="button" class="rounded-xl bg-teal-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-teal-700" @click="$emit('changeMode', 'configure')">Перейти к подключению</button>
          </div>
        </div>

        <form v-else class="space-y-5 px-6 py-6" @submit.prevent="submit">
          <label v-if="isDirect" class="block"><span class="text-sm font-semibold text-slate-800 dark:text-slate-200">Логин клиента <span class="font-normal text-slate-500">(необязательно)</span></span><input v-model="clientLogin" data-testid="direct-client-login" autocomplete="off" class="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-100 dark:border-slate-700 dark:bg-slate-950 dark:text-white dark:focus:ring-teal-950" placeholder="Например, master-vozduha"></label>
          <label class="block"><span class="flex items-center justify-between gap-3 text-sm font-semibold text-slate-800 dark:text-slate-200">OAuth-токен<button type="button" class="inline-flex items-center gap-1 text-xs text-teal-700 hover:text-teal-800" @click="$emit('changeMode', 'help')"><HelpCircle class="h-4 w-4" /> Где взять?</button></span><input v-model="oauthToken" data-testid="yandex-provider-oauth-token" type="password" :required="connection?.state !== 'connected'" autocomplete="new-password" class="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-100 dark:border-slate-700 dark:bg-slate-950 dark:text-white dark:focus:ring-teal-950" :placeholder="connection?.state === 'connected' ? 'Оставьте пустым, чтобы сохранить текущий токен' : 'Вставьте OAuth-токен'"></label>
          <p v-if="!isDirect" class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600 dark:bg-slate-800 dark:text-slate-300">Домен определится автоматически из подтверждённого сайта в Яндекс Вебмастере.</p>
          <p v-if="error" role="alert" class="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{{ error }}</p>
          <div class="flex flex-wrap justify-end gap-3 border-t border-slate-100 pt-5 dark:border-slate-800"><button type="button" class="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800" @click="$emit('close')">Отмена</button><button data-testid="yandex-provider-save" type="submit" class="inline-flex items-center gap-2 rounded-xl bg-teal-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-60" :disabled="saving"><Loader2 v-if="saving" class="h-4 w-4 animate-spin" />{{ saving ? 'Проверяем...' : 'Проверить и сохранить' }}</button></div>
        </form>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.step { @apply flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white; }
</style>
