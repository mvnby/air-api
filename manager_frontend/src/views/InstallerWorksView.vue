<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { ArrowLeft, CalendarDays, ChevronLeft, ChevronRight, ClipboardList, Loader2, MapPin, Phone, RefreshCw } from 'lucide-vue-next';
import InstallerMaterials from '../components/installer/InstallerMaterials.vue';
import InstallerEquipmentCard from '../components/installer/InstallerEquipmentCard.vue';
import InstallerCollectionInstruction from '../components/installer/InstallerCollectionInstruction.vue';
import { installerWorkspaceApi, type InstallerWorkBucket, type InstallerWorkDetail, type InstallerWorkSummary } from '../services/installer-workspace';
import { managerSession } from '../services/manager-session';
import { managerStorefrontSelection } from '../services/manager-storefront-selection';
import { getApiErrorMessage } from '../utils/api-errors';

const items = ref<InstallerWorkSummary[]>([]); const total = ref(0); const page = ref(1); const bucket = ref<InstallerWorkBucket>('all');
const detail = ref<InstallerWorkDetail | null>(null); const loading = ref(false); const error = ref('');
let generation = 0;
const initialId = /^\/manager\/my-work\/([1-9]\d*)\/?$/.exec(window.location.pathname)?.[1];
const selectedId = ref<number | null>(initialId && Number.isSafeInteger(Number(initialId)) ? Number(initialId) : null);
let initialContext = true;
const invalidWorkLink = window.location.pathname.replace(/\/$/, '') !== '/manager/my-work' && (!initialId || !Number.isSafeInteger(Number(initialId)));
const pages = computed(() => Math.max(1, Math.ceil(total.value / 30)));
const buckets: { value: InstallerWorkBucket; label: string }[] = [{ value: 'all', label: 'Все работы' }, { value: 'today', label: 'Сегодня' }, { value: 'upcoming', label: 'Предстоящие' }, { value: 'unscheduled', label: 'Без даты' }];
const context = computed(() => `${managerSession.auth.value?.staff_user_id ?? ''}:${managerStorefrontSelection.selectedTenantId.value}:${managerStorefrontSelection.selectedSlug.value}`);
const dateLabel = (value: string | null) => value ? new Intl.DateTimeFormat('ru', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) : 'Дата пока не назначена';
const phoneHref = (phone: string) => `tel:${phone.replace(/[^+\d]/g, '')}`;
const load = async () => {
  const requestId = ++generation; loading.value = true; error.value = '';
  if (invalidWorkLink) { error.value = 'Некорректная ссылка на работу'; loading.value = false; return; }
  try {
    if (selectedId.value !== null) { const result = await installerWorkspaceApi.detail(selectedId.value); if (requestId === generation) detail.value = result; }
    else { const result = await installerWorkspaceApi.works(page.value, bucket.value); if (requestId === generation) { items.value = result.items; total.value = result.total; } }
  } catch (cause) { if (requestId === generation) { items.value = []; detail.value = null; total.value = 0; error.value = getApiErrorMessage(cause) || 'Не удалось загрузить работы'; } }
  finally { if (requestId === generation) loading.value = false; }
};
const open = (id: number) => { selectedId.value = id; detail.value = null; void load(); };
const back = () => { selectedId.value = null; detail.value = null; void load(); };
const selectBucket = (value: InstallerWorkBucket) => { if (bucket.value === value) return; bucket.value = value; page.value = 1; void load(); };
watch(context, () => { ++generation; if (!initialContext) selectedId.value = null; initialContext = false; detail.value = null; items.value = []; total.value = 0; page.value = 1; if (managerSession.isAuthenticated.value) void load(); }, { immediate: true });
onBeforeUnmount(() => { ++generation; });
</script>
<template>
  <main class="mx-auto w-full max-w-5xl p-4 pb-12 sm:p-6" data-testid="installer-works">
    <header class="mb-5 flex items-start justify-between gap-3"><div><h1 class="text-2xl font-bold text-gray-900 dark:text-white">Мои работы</h1><p class="mt-1 text-sm text-gray-500">Назначенные вам работы и указания менеджера</p></div><button type="button" class="rounded-lg border border-gray-200 p-2 text-gray-500 hover:bg-gray-50 disabled:opacity-50" aria-label="Обновить работы" :disabled="loading" @click="load"><RefreshCw class="h-5 w-5" aria-hidden="true" /></button></header>
    <button v-if="selectedId !== null" type="button" class="mb-4 inline-flex items-center gap-2 text-sm font-medium text-brand-600" @click="back"><ArrowLeft class="h-4 w-4" aria-hidden="true" />Все работы</button>
    <nav v-else class="mb-5 flex flex-wrap gap-2" aria-label="Период работ"><button v-for="tab in buckets" :key="tab.value" type="button" class="rounded-full px-4 py-2 text-sm font-medium" :class="bucket === tab.value ? 'bg-brand-600 text-white' : 'bg-gray-100 text-gray-600 dark:bg-slate-800 dark:text-slate-300'" :aria-pressed="bucket === tab.value" @click="selectBucket(tab.value)">{{ tab.label }}</button></nav>
    <div v-if="loading" class="flex justify-center gap-2 py-12 text-gray-500" role="status"><Loader2 class="h-5 w-5 animate-spin" aria-hidden="true" />Загружаем работы…</div>
    <div v-else-if="error" class="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800" role="alert">{{ error }}<button type="button" class="ml-2 underline" @click="load">Повторить</button></div>
    <article v-else-if="detail" class="space-y-5">
      <div class="rounded-2xl border border-gray-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900"><p class="text-xs text-gray-500">Заказ №{{ detail.order_id }}</p><h2 class="mt-1 text-xl font-semibold">{{ detail.title }}</h2><p class="mt-3 flex items-center gap-2 text-sm"><CalendarDays class="h-4 w-4 shrink-0 text-gray-400" aria-hidden="true" />{{ dateLabel(detail.start_time) }}</p><p v-if="detail.address" class="mt-2 flex items-start gap-2 text-sm"><MapPin class="h-4 w-4 shrink-0 text-gray-400" aria-hidden="true" />{{ detail.address }}</p><p class="mt-3 font-medium">{{ detail.customer_name }}</p><a v-if="detail.customer_phone" class="mt-1 inline-flex min-h-11 items-center gap-2 text-sm text-brand-600" :href="phoneHref(detail.customer_phone)"><Phone class="h-4 w-4" aria-hidden="true" />{{ detail.customer_phone }}</a></div>
      <InstallerCollectionInstruction :collection="detail.collection" />
      <section v-if="detail.instructions"><h2 class="mb-2 font-semibold">Указания по работе</h2><p class="whitespace-pre-wrap break-words rounded-xl bg-white p-4 text-sm dark:bg-slate-900">{{ detail.instructions }}</p></section>
      <section v-if="detail.equipment.length"><h2 class="mb-3 font-semibold">Оборудование</h2><div class="grid gap-3 md:grid-cols-2"><InstallerEquipmentCard v-for="equipment in detail.equipment" :key="equipment.key" :equipment="equipment" /></div></section>
      <InstallerMaterials :key="detail.id" :materials="detail.materials" />
    </article>
    <template v-else>
      <div v-if="!items.length" class="rounded-2xl border border-dashed border-gray-200 px-5 py-14 text-center text-gray-500"><ClipboardList class="mx-auto mb-3 h-9 w-9 text-gray-300" aria-hidden="true" /><h2 class="font-semibold text-gray-700 dark:text-slate-200">Пока нет назначенных работ</h2><p class="mt-1 text-sm">Новые работы появятся здесь после назначения менеджером.</p></div>
      <div v-else class="grid gap-4 md:grid-cols-2"><button v-for="work in items" :key="work.id" type="button" class="rounded-2xl border border-gray-200 bg-white p-5 text-left transition hover:border-brand-300 hover:shadow-sm dark:border-slate-700 dark:bg-slate-900" :aria-label="`Открыть работу: ${work.title}`" @click="open(work.id)"><p class="text-xs text-gray-500">Заказ №{{ work.order_id }}</p><h2 class="mt-1 break-words text-lg font-semibold">{{ work.title }}</h2><p class="mt-3 flex items-center gap-2 text-sm text-gray-600 dark:text-slate-300"><CalendarDays class="h-4 w-4 shrink-0" aria-hidden="true" />{{ dateLabel(work.start_time) }}</p><p v-if="work.address" class="mt-2 flex items-start gap-2 text-sm text-gray-600 dark:text-slate-300"><MapPin class="h-4 w-4 shrink-0" aria-hidden="true" />{{ work.address }}</p><p class="my-3 text-sm">{{ work.customer_name }}</p><InstallerCollectionInstruction :collection="work.collection" /><span class="mt-3 block text-sm font-medium text-brand-600">Открыть работу →</span></button></div>
      <nav v-if="pages > 1" aria-label="Страницы работ" class="mt-5 flex items-center justify-center gap-4"><button type="button" aria-label="Предыдущая страница" :disabled="page <= 1" class="rounded-lg border p-2 disabled:opacity-40" @click="page--; load()"><ChevronLeft class="h-5 w-5" aria-hidden="true" /></button><span class="text-sm">{{ page }} / {{ pages }}</span><button type="button" aria-label="Следующая страница" :disabled="page >= pages" class="rounded-lg border p-2 disabled:opacity-40" @click="page++; load()"><ChevronRight class="h-5 w-5" aria-hidden="true" /></button></nav>
    </template>
  </main>
</template>
