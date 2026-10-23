<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { Mail, Plus, RefreshCw } from 'lucide-vue-next';
import MailDraftEditor from '../components/mail/MailDraftEditor.vue';
import MailMessageContent from '../components/mail/MailMessageContent.vue';
import { mailApi, type MailAccount, type MailDraftFields, type MailFolder, type MailMessage, mailStatusLabel } from '../services/mail-workspace-api';
import { getApiErrorMessage } from '../utils/api-errors';

const params = new URLSearchParams(window.location.search);
const folder = ref<MailFolder>(window.location.pathname.endsWith('/outbox') ? 'outbox' : window.location.pathname.endsWith('/drafts') ? 'drafts' : 'inbox');
const filters = ref({ q: params.get('q') || '', status: params.get('status') || '', order_id: params.get('orderId') || '' });
const page = ref(1);
const limit = 30;
const total = ref(0);
const items = ref<MailMessage[]>([]);
const selected = ref<MailMessage | null>(null);
const editor = ref<{ save: () => Promise<boolean> } | null>(null);
const accounts = ref<MailAccount[]>([]);
const loading = ref(false);
const actionBusy = ref(false);
const error = ref('');
const accountsError = ref('');
const notice = ref('');
const pages = computed(() => Math.max(1, Math.ceil(total.value / limit)));
const folders: { value: MailFolder; label: string }[] = [{ value: 'inbox', label: 'Входящие' }, { value: 'outbox', label: 'Исходящие' }, { value: 'drafts', label: 'Черновики' }];
let listRequest = 0;

const rememberSelection = (message: MailMessage | null) => {
  const url = new URL(window.location.href);
  if (message) url.searchParams.set('emailId', String(message.id));
  else url.searchParams.delete('emailId');
  window.history.replaceState({}, '', url.pathname + url.search);
};
const leaveEditor = async () => !editor.value || await editor.value.save();
const load = async () => {
  const requestId = ++listRequest;
  loading.value = true;
  error.value = '';
  try {
    const result = await mailApi.list({ folder: folder.value, page: page.value, limit, q: filters.value.q.trim() || undefined, status: filters.value.status || undefined, order_id: filters.value.order_id ? Number(filters.value.order_id) : undefined });
    if (requestId !== listRequest) return;
    items.value = result.items;
    total.value = result.total;
  } catch (cause) { if (requestId === listRequest) error.value = getApiErrorMessage(cause); }
  finally { if (requestId === listRequest) loading.value = false; }
};
const sync = async () => {
  if (actionBusy.value) return;
  actionBusy.value = true;
  error.value = '';
  notice.value = '';
  try { const result = await mailApi.sync(); await load(); notice.value = `Загружено новых писем: ${result.captured || 0}.` + (result.has_more ? ' Остались письма — нажмите «Обновить почту» ещё раз.' : ' Почта обновлена.'); }
  catch (cause) { error.value = getApiErrorMessage(cause); }
  finally { actionBusy.value = false; }
};
const open = async (id: number) => {
  if (actionBusy.value || !await leaveEditor()) return;
  actionBusy.value = true;
  error.value = '';
  try {
    selected.value = await mailApi.get(id);
    rememberSelection(selected.value);
    if (selected.value.folder !== folder.value) {
      folder.value = selected.value.folder;
      filters.value.status = '';
      page.value = 1;
      await load();
    }
  }
  catch (cause) { error.value = getApiErrorMessage(cause); }
  finally { actionBusy.value = false; }
};
const close = () => { selected.value = null; rememberSelection(null); void load(); };
const create = async (fields: MailDraftFields = {}) => {
  if (actionBusy.value || !await leaveEditor()) return;
  actionBusy.value = true;
  error.value = '';
  try {
    selected.value = await mailApi.create({ account_id: accounts.value[0]?.id || 'system', ...fields });
    folder.value = 'drafts';
    filters.value = { q: '', status: '', order_id: fields.order_id ? String(fields.order_id) : '' };
    page.value = 1;
    rememberSelection(selected.value);
    await load();
  } catch (cause) { error.value = getApiErrorMessage(cause); }
  finally { actionBusy.value = false; }
};
const reply = () => {
  const original = selected.value;
  if (!original) return;
  const quoted = original.body_text.split('\n').map(line => `> ${line}`).join('\n');
  void create({
    to: original.folder === 'inbox' ? (original.reply_to?.length ? original.reply_to : original.sender_email ? [original.sender_email] : []) : original.to,
    in_reply_to: original.message_id || undefined,
    references: [...(original.references || []), ...(original.message_id ? [original.message_id] : [])].slice(-50),
    subject: /^re:/i.test(original.subject) ? original.subject : `Re: ${original.subject}`,
    body_text: `\n\n${original.sender_email || ''} писал(а):\n${quoted}`,
    order_id: original.order_id,
    customer_id: original.customer_id,
  });
};
const copy = async () => {
  if (!selected.value || actionBusy.value || !await leaveEditor()) return;
  actionBusy.value = true;
  error.value = '';
  try { selected.value = await mailApi.copy(selected.value.id, selected.value.version); folder.value = 'drafts'; filters.value = { q: '', status: '', order_id: selected.value.order_id ? String(selected.value.order_id) : '' }; page.value = 1; rememberSelection(selected.value); await load(); }
  catch (cause) { error.value = getApiErrorMessage(cause); }
  finally { actionBusy.value = false; }
};
const switchFolder = async (value: MailFolder) => {
  if (!await leaveEditor()) return;
  folder.value = value;
  filters.value.status = '';
  page.value = 1;
  selected.value = null;
  window.history.replaceState({}, '', `/manager/mail/${value}`);
  await load();
};
const search = () => { page.value = 1; void load(); };
const paginate = (value: number) => { page.value = value; void load(); };
const saved = (message: MailMessage) => {
  selected.value = message;
  const index = items.value.findIndex(item => item.id === message.id);
  if (index >= 0) items.value[index] = message;
};
const sent = (message: MailMessage) => { selected.value = message; folder.value = 'outbox'; filters.value.status = ''; page.value = 1; void load(); };

onMounted(async () => {
  try { accounts.value = (await mailApi.accounts()).items; }
  catch (cause) { accountsError.value = getApiErrorMessage(cause); }
  await load();
  const emailId = Number(params.get('emailId') || params.get('message'));
  if (emailId) await open(emailId);
  else if (params.get('compose') === '1') await create({ order_id: filters.value.order_id ? Number(filters.value.order_id) : null, customer_id: params.get('customerId') ? Number(params.get('customerId')) : null });
});
</script>

<template>
  <main class="min-h-screen bg-slate-50 p-4 text-slate-900 dark:bg-slate-950 dark:text-slate-100 sm:p-6">
    <div class="mx-auto max-w-7xl space-y-5">
      <header class="flex flex-wrap items-center justify-between gap-3"><div><h1 class="flex items-center gap-2 text-2xl font-bold"><Mail class="h-6 w-6 text-brand-600" />Почта</h1><p class="mt-1 text-sm text-slate-500">Деловая переписка вашей компании. Заказ и карточка клиента необязательны.</p></div><div class="flex gap-2"><button type="button" class="rounded-xl border border-slate-300 p-2 dark:border-slate-700" aria-label="Обновить письма" :disabled="loading" @click="load"><RefreshCw class="h-5 w-5" :class="loading ? 'animate-spin' : ''" /></button><button type="button" class="inline-flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" :disabled="actionBusy" @click="create()"><Plus class="h-4 w-4" />Новое письмо</button></div></header>
      <nav class="flex flex-wrap gap-2" aria-label="Папки почты"><button v-for="item in folders" :key="item.value" type="button" class="rounded-xl px-4 py-2 text-sm font-semibold" :class="folder === item.value ? 'bg-brand-600 text-white' : 'border border-slate-300 bg-white dark:border-slate-700 dark:bg-slate-900'" :aria-current="folder === item.value ? 'page' : undefined" @click="switchFolder(item.value)">{{ item.label }}</button></nav>
      <div v-if="folder === 'inbox'" class="flex flex-wrap items-center gap-3"><button type="button" class="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold disabled:opacity-50 dark:border-slate-700" :disabled="actionBusy" @click="sync">{{ actionBusy ? 'Обновляем почту…' : 'Обновить почту' }}</button><p class="text-xs text-slate-500">Загрузить новые письма из настроенного аккаунта.</p></div>
      <p v-if="notice" role="status" class="text-sm text-emerald-700 dark:text-emerald-300">{{ notice }}</p>
      <form class="flex flex-wrap gap-3" @submit.prevent="search"><input v-model="filters.q" aria-label="Поиск писем" placeholder="Тема, адрес или текст" class="min-w-48 flex-1 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900" /><select v-if="folder !== 'inbox'" v-model="filters.status" aria-label="Статус письма" class="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"><option value="">Все статусы</option><option v-for="status in ['draft', 'pending', 'sending', 'sent', 'failed', 'unknown']" :key="status" :value="status">{{ mailStatusLabel(status) }}</option></select><input v-model="filters.order_id" type="number" min="1" aria-label="Фильтр по заказу" placeholder="Заказ (необязательно)" class="w-52 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900" /><button type="submit" class="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold dark:border-slate-700">Найти</button></form>
      <p v-if="error || accountsError" role="alert" class="rounded-xl bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">{{ error || accountsError }}</p>
      <div class="grid items-start gap-5" :class="selected ? 'lg:grid-cols-[minmax(280px,1fr)_minmax(0,2fr)]' : ''">
        <section class="overflow-hidden rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900" aria-label="Список писем">
          <p v-if="loading" class="p-5 text-sm text-slate-500">Загружаем письма…</p><p v-else-if="!items.length" class="p-5 text-sm text-slate-500">Писем не найдено.</p>
          <ul v-else class="divide-y divide-slate-200 dark:divide-slate-800"><li v-for="message in items" :key="message.id"><button type="button" class="w-full space-y-1 px-4 py-3 text-left hover:bg-slate-50 disabled:opacity-50 dark:hover:bg-slate-800" :class="selected?.id === message.id ? 'bg-brand-50 dark:bg-brand-950/30' : ''" :disabled="actionBusy" @click="open(message.id)"><span class="flex flex-wrap justify-between gap-2 text-xs text-slate-500"><span>{{ mailStatusLabel(message.status) }}</span><time>{{ new Date(message.updated_at || message.created_at).toLocaleString('ru-RU') }}</time></span><span class="block break-words font-semibold">{{ message.subject || 'Без темы' }}</span><span class="block break-all text-xs text-slate-500">{{ message.folder === 'inbox' ? message.sender_email : message.to.join(', ') || 'Получатель не указан' }}</span><span v-if="message.attachments.length" class="block text-xs text-slate-500">{{ message.attachments.length }} влож.</span></button></li></ul>
          <footer class="flex items-center justify-between gap-2 border-t border-slate-200 p-3 text-sm dark:border-slate-800"><button type="button" :disabled="page <= 1 || loading" class="disabled:opacity-40" @click="paginate(page - 1)">Назад</button><span>{{ page }} / {{ pages }} · {{ total }}</span><button type="button" :disabled="page >= pages || loading" class="disabled:opacity-40" @click="paginate(page + 1)">Далее</button></footer>
        </section>
        <MailDraftEditor v-if="selected?.status === 'draft'" :key="selected.id" ref="editor" :initial="selected" :accounts="accounts" @saved="saved" @close="close" @deleted="close" @sent="sent" />
        <section v-else-if="selected" class="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"><header class="flex justify-between gap-3"><h2 class="break-words text-lg font-bold">{{ selected.subject || 'Без темы' }}</h2><button type="button" class="text-sm font-semibold text-slate-500" @click="close">Закрыть</button></header><MailMessageContent :message="selected" /><div class="flex flex-wrap gap-3"><button v-if="selected.folder === 'inbox' || selected.status === 'sent'" type="button" class="rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" :disabled="actionBusy" @click="reply">Ответить</button><button v-if="['sent', 'failed'].includes(selected.status)" type="button" class="rounded-xl border border-slate-300 px-4 py-2 text-sm dark:border-slate-700" :disabled="actionBusy" @click="copy">Создать новый черновик с теми же файлами</button><button v-if="['pending', 'sending', 'unknown'].includes(selected.status)" type="button" class="text-sm font-semibold text-brand-700 dark:text-brand-300" :disabled="actionBusy" @click="open(selected.id)">Проверить статус</button></div><p v-if="selected.status === 'sent'" class="text-xs text-slate-500">Это сохранённая история отправки. Почтовый сервер принял письмо; доставка адресату не подтверждена.</p></section>
      </div>
    </div>
  </main>
</template>
