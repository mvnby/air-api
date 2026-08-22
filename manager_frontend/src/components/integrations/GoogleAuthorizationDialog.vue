<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ExternalLink, HelpCircle, Loader2, ShieldCheck, X } from 'lucide-vue-next';

import type { AnalyticsConnectionItem } from '../../client';

type GoogleProvider = 'google_analytics' | 'google_ads' | 'google_search_console';
type AuthorizationFields = {
  property_id?: string;
  customer_id?: string;
  login_customer_id?: string | null;
};

const props = defineProps<{
  open: boolean;
  mode: 'configure' | 'help';
  connection: AnalyticsConnectionItem | null;
  saving: boolean;
  error: string;
}>();
const emit = defineEmits<{
  close: [];
  changeMode: [mode: 'configure' | 'help'];
  authorize: [provider: GoogleProvider, fields: AuthorizationFields];
}>();

const propertyId = ref('');
const customerId = ref('');
const loginCustomerId = ref('');
const provider = computed<GoogleProvider | null>(() => {
  const value = props.connection?.provider;
  return value === 'google_analytics'
    || value === 'google_ads'
    || value === 'google_search_console'
    ? value
    : null;
});
const providerName = computed(() => ({
  google_analytics: 'Google Analytics 4',
  google_ads: 'Google Ads',
  google_search_console: 'Google Search Console',
}[provider.value || 'google_analytics']));
const isAnalytics = computed(() => provider.value === 'google_analytics');
const isAds = computed(() => provider.value === 'google_ads');
const isSearchConsole = computed(() => provider.value === 'google_search_console');
const helpUrl = computed(() => ({
  google_analytics: 'https://support.google.com/analytics/answer/9539598',
  google_ads: 'https://support.google.com/google-ads/answer/1704344',
  google_search_console: 'https://support.google.com/webmasters/answer/9128668',
}[provider.value || 'google_analytics']));
const resourceName = computed(() => (
  isAnalytics.value ? 'ресурсу GA4' : isAds.value ? 'рекламному аккаунту' : 'сайту'
));

watch(
  () => [props.open, props.connection] as const,
  ([isOpen, connection]) => {
    if (!isOpen) return;
    propertyId.value = connection?.configuration?.property_id || '';
    customerId.value = connection?.configuration?.customer_id || '';
    loginCustomerId.value = connection?.configuration?.login_customer_id || '';
  },
  { immediate: true },
);

const submit = () => {
  if (!provider.value) return;
  const fields: AuthorizationFields = isAnalytics.value
    ? { property_id: propertyId.value.trim() }
    : isAds.value
      ? {
        customer_id: customerId.value.trim(),
        login_customer_id: loginCustomerId.value.trim() || null,
      }
      : {};
  emit('authorize', provider.value, fields);
};
</script>

<template>
  <Teleport to="body">
    <div v-if="open && provider" class="fixed inset-0 z-[120] flex items-center justify-center bg-slate-950/55 p-4" @click.self="$emit('close')">
      <section role="dialog" aria-modal="true" aria-labelledby="google-provider-dialog-title" class="w-full max-w-xl overflow-hidden rounded-3xl bg-white shadow-2xl dark:bg-slate-900">
        <header class="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-5 dark:border-slate-800">
          <div>
            <p class="text-xs font-bold uppercase tracking-[0.16em] text-teal-600">{{ providerName }}</p>
            <h2 id="google-provider-dialog-title" class="mt-1 text-xl font-bold text-slate-950 dark:text-white">{{ mode === 'help' ? 'Где найти данные' : 'Авторизация Google' }}</h2>
          </div>
          <button type="button" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200" aria-label="Закрыть" @click="$emit('close')"><X class="h-5 w-5" /></button>
        </header>

        <div v-if="mode === 'help'" data-testid="google-provider-help" class="space-y-5 px-6 py-6">
          <ol class="space-y-4 text-sm leading-6 text-slate-600 dark:text-slate-300">
            <li class="flex gap-3"><span class="step">1</span><span>Войдите в Google под аккаунтом, у которого есть доступ к нужному {{ resourceName }}.</span></li>
            <li v-if="isAnalytics" class="flex gap-3"><span class="step">2</span><span>Откройте «Администратор → Сведения о ресурсе» и скопируйте числовой идентификатор ресурса.</span></li>
            <li v-else-if="isAds" class="flex gap-3"><span class="step">2</span><span>Customer ID указан в правом верхнем углу Google Ads. MCC нужен только при подключении через управляющий аккаунт.</span></li>
            <li v-else class="flex gap-3"><span class="step">2</span><span>Заранее подтвердите сайт в Search Console. CRM сама выберет ресурс, который точно совпадает с доменом текущего филиала.</span></li>
            <li class="flex gap-3"><span class="step">3</span><span>Вернитесь в CRM, нажмите «Продолжить с Google» и подтвердите доступ только на чтение.</span></li>
          </ol>
          <div class="flex flex-wrap gap-3">
            <a :href="helpUrl" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800">Инструкция Google <ExternalLink class="h-4 w-4" /></a>
            <button type="button" class="rounded-xl bg-teal-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-teal-700" @click="$emit('changeMode', 'configure')">Перейти к подключению</button>
          </div>
        </div>

        <form v-else class="space-y-5 px-6 py-6" @submit.prevent="submit">
          <p class="text-sm leading-6 text-slate-600 dark:text-slate-300">Google попросит войти под аккаунтом с доступом к нужному {{ isSearchConsole ? 'сайту' : 'ресурсу' }}. CRM не получает и не хранит ваш пароль Google.</p>
          <label v-if="isAnalytics" class="block">
            <span class="flex items-center justify-between gap-3 text-sm font-semibold text-slate-800 dark:text-slate-200">Property ID <button type="button" class="inline-flex items-center gap-1 text-xs text-teal-700 hover:text-teal-800" @click="$emit('changeMode', 'help')"><HelpCircle class="h-4 w-4" /> Где найти?</button></span>
            <input v-model="propertyId" data-testid="ga-property-id" required inputmode="numeric" class="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-100 dark:border-slate-700 dark:bg-slate-950 dark:text-white dark:focus:ring-teal-950" placeholder="Например, 123456789">
          </label>
          <template v-if="isAds">
            <label class="block">
              <span class="flex items-center justify-between gap-3 text-sm font-semibold text-slate-800 dark:text-slate-200">Customer ID <button type="button" class="inline-flex items-center gap-1 text-xs text-teal-700 hover:text-teal-800" @click="$emit('changeMode', 'help')"><HelpCircle class="h-4 w-4" /> Где найти?</button></span>
              <input v-model="customerId" data-testid="google-ads-customer-id" required inputmode="numeric" class="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-100 dark:border-slate-700 dark:bg-slate-950 dark:text-white dark:focus:ring-teal-950" placeholder="123-456-7890">
            </label>
            <label class="block">
              <span class="text-sm font-semibold text-slate-800 dark:text-slate-200">Login customer ID <span class="font-normal text-slate-500">(необязательно)</span></span>
              <input v-model="loginCustomerId" data-testid="google-ads-login-customer-id" inputmode="numeric" class="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-100 dark:border-slate-700 dark:bg-slate-950 dark:text-white dark:focus:ring-teal-950" placeholder="Для управляющего аккаунта MCC">
            </label>
          </template>
          <div v-if="isSearchConsole" class="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200">Домен CRM определит автоматически из подтверждённого ресурса Search Console. <button type="button" class="ml-1 inline-flex items-center gap-1 font-semibold text-teal-700" @click="$emit('changeMode', 'help')"><HelpCircle class="h-4 w-4" /> Как подготовить?</button></div>
          <div class="rounded-2xl border border-teal-100 bg-teal-50 p-4 text-sm text-teal-900 dark:border-teal-900 dark:bg-teal-950/40 dark:text-teal-100"><div class="flex gap-3"><ShieldCheck class="mt-0.5 h-5 w-5 shrink-0" /><p>Подключение использует защищённую авторизацию OAuth. Доступ можно отозвать в настройках Google.</p></div></div>
          <p v-if="error" role="alert" class="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{{ error }}</p>
          <div class="flex flex-wrap items-center justify-end gap-3 border-t border-slate-100 pt-5 dark:border-slate-800">
            <button type="button" class="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800" @click="$emit('close')">Отмена</button>
            <button data-testid="google-authorize" type="submit" class="inline-flex items-center gap-2 rounded-xl bg-teal-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-60" :disabled="saving"><Loader2 v-if="saving" class="h-4 w-4 animate-spin" />Продолжить с Google</button>
          </div>
        </form>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.step { @apply flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white; }
</style>
