<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { ManagerTenderModuleService, type TenderMarketItem, type TenderMarketResults } from '../client';
import TenderMarketEvidencePanel from '../features/tenders/TenderMarketEvidencePanel.vue';
import { openManagerChild, replaceManagerLocation, returnToManager } from '../services/manager-navigation-history';
import { orderPageUrl } from '../services/order-navigation';
import { getApiErrorMessage } from '../utils/api-errors';

defineProps<{ canManageSettings?: boolean }>();
const params = new URLSearchParams(window.location.search);
const fromInbox = params.get('from') === 'inbox';
const inboxReturn = window.history.state?.managerReturn?.href;
const inboxPath = typeof inboxReturn === 'string' && inboxReturn.split('?')[0] === '/manager/leads' ? inboxReturn : '/manager/leads?source=belzakupki';
const mode = ref<'match' | 'review'>(params.get('show') === 'review' ? 'review' : 'match');
const profile = ref((params.get('profile') || '').slice(0, 96));
const rows = ref<TenderMarketItem[]>([]);
const result = ref<TenderMarketResults | null>(null);
const loading = ref(false);
const error = ref('');
const openEvidenceId = ref<number | null>(null);
const nextId = computed(() => result.value?.next_before_id);
const portalName: Record<string, string> = {
  goszakupki_by: 'Госзакупки',
  gias_by: 'ГИАС',
  icetrade_by: 'ICETRADE',
  butb_by: 'БУТБ',
};
const crmPath = (link: NonNullable<TenderMarketItem['crm_link']>) => link.kind === 'incoming'
  ? `/manager/leads?kind=order&itemId=${link.id}&from=market` : orderPageUrl(link.id, window.location.pathname + window.location.search);
const formatDate = (value: string) => new Intl.DateTimeFormat('ru-BY', {
  timeZone: 'Europe/Minsk', dateStyle: 'medium',
}).format(new Date(value));
const formatSync = (value: string) => new Intl.DateTimeFormat('ru-BY', {
  timeZone: 'Europe/Minsk', dateStyle: 'short', timeStyle: 'short',
}).format(new Date(value));
const publicationUrl = (value: string) => {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' ? url.href : undefined;
  } catch { return undefined; }
};
let version = 0;

async function load(more = false) {
  if (more && (loading.value || !nextId.value)) return;
  const requestVersion = ++version;
  loading.value = true;
  error.value = '';
  if (!more) {
    rows.value = [];
    openEvidenceId.value = null;
  }
  try {
    const page = await ManagerTenderModuleService.listManagerTenderMarket(
      mode.value, profile.value || undefined, more ? nextId.value ?? undefined : undefined,
      more ? result.value?.settings_version : undefined,
    );
    if (requestVersion !== version) return;
    rows.value = more ? [...rows.value, ...page.items] : page.items;
    result.value = page;
  } catch (reason) {
    if (requestVersion === version) error.value = getApiErrorMessage(reason);
  } finally {
    if (requestVersion === version) loading.value = false;
  }
}

watch([mode, profile], () => {
  const url = new URL(window.location.href);
  if (url.pathname === '/manager/tenders') {
    if (mode.value === 'review') url.searchParams.set('show', 'review'); else url.searchParams.delete('show');
    if (profile.value) url.searchParams.set('profile', profile.value); else url.searchParams.delete('profile');
    replaceManagerLocation(url.pathname + url.search);
  }
  void load();
});
onMounted(() => void load());
onBeforeUnmount(() => { version++; });
</script>

<template>
  <main class="mx-auto max-w-5xl space-y-5 p-4 sm:p-8">
    <header class="flex flex-wrap items-baseline justify-between gap-3">
      <div><a v-if="fromInbox" :href="inboxPath" class="text-sm font-semibold text-brand-700 underline" @click.exact.prevent="returnToManager(inboxPath)">Ко входящим</a><h1 class="text-2xl font-bold">Мониторинг тендеров</h1></div>
      <a v-if="canManageSettings" href="/manager/settings?tab=modules" @click.exact.prevent="openManagerChild('/manager/settings?tab=modules')" class="text-sm font-semibold text-brand-700 underline">Настройки поиска</a>
    </header>
    <div class="flex flex-wrap items-end gap-3">
      <div class="flex gap-2" aria-label="Выдача тендеров">
        <button type="button" class="btn-mini-outline" :aria-pressed="mode === 'match'" @click="mode = 'match'">Подходят</button>
        <button type="button" class="btn-mini-outline" :aria-pressed="mode === 'review'" @click="mode = 'review'">На проверке</button>
      </div>
      <label v-if="result?.profile_names.length" class="min-w-[12rem] text-sm">Профиль
        <select v-model="profile" class="field-input mt-1">
          <option value="">Все профили</option>
          <option v-for="name in result.profile_names" :key="name" :value="name">{{ name }}</option>
        </select>
      </label>
    </div>
    <p v-if="loading" role="status" class="text-sm text-slate-500">Проверяем публикации по профилю…</p>
    <p v-if="error" role="alert" class="text-sm text-red-700">{{ error }}</p>
    <button v-if="error" type="button" class="btn-mini-outline" @click="load()">Обновить</button>
    <p v-if="result?.syncing" class="text-xs text-slate-500">Обновляется лента источников.</p>
    <p v-if="result?.last_sync_at" class="text-xs text-slate-500">Лента сверена {{ formatSync(result.last_sync_at) }}</p>
    <div v-if="!error && !loading && !rows.length" class="text-sm text-slate-500">
      {{ result?.last_sync_at ? 'В этой части выдачи нет подходящих публикаций.' : 'Публикации появятся после синхронизации источника.' }}
    </div>
    <ul v-if="rows.length" class="space-y-2">
      <li v-for="row in rows" :key="row.id" class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <a v-if="publicationUrl(row.source_url)" :href="publicationUrl(row.source_url)" target="_blank" rel="noopener noreferrer" class="break-words font-semibold text-brand-700 underline">{{ row.title }}</a>
        <p v-else class="break-words font-semibold">{{ row.title }}</p>
        <p class="mt-1 text-xs text-slate-500">
          {{ portalName[row.source] || row.source }}<span v-if="row.deadline_at"> · До {{ formatDate(row.deadline_at) }}</span>
        </p>
        <p class="mt-2 text-xs">{{ row.profiles.map((item) => item.name).join(' · ') }}</p>
        <a v-if="row.crm_link" :href="crmPath(row.crm_link)" class="mr-3 inline-flex min-h-11 items-center text-sm font-semibold text-brand-700 underline" @click.exact.prevent="openManagerChild(crmPath(row.crm_link))">{{ row.crm_link.kind === 'incoming' ? 'Открыть во входящих' : 'Открыть заказ' }} №{{ row.crm_link.id }}</a>
        <button type="button" class="btn-mini-outline mt-2"
          :aria-expanded="openEvidenceId === row.id" @click="openEvidenceId = openEvidenceId === row.id ? null : row.id"
        >ТЗ и оригиналы</button>
        <TenderMarketEvidencePanel v-if="openEvidenceId === row.id" :publication-id="row.id" />
      </li>
    </ul>
    <button v-if="nextId && !error" type="button" class="btn-mini-outline" :disabled="loading" @click="load(true)">Следующие публикации</button>
  </main>
</template>
