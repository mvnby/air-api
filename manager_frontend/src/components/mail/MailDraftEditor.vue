<script setup lang="ts">
import { computed, ref } from 'vue';
import { useMailDraft } from '../../composables/useMailDraft';
import { mailApi, type MailAccount, type MailMessage } from '../../services/mail-workspace-api';
import { getApiErrorMessage } from '../../utils/api-errors';
import MailMessageContent from './MailMessageContent.vue';

const props = defineProps<{ initial: MailMessage; accounts: MailAccount[] }>();
const emit = defineEmits<{ saved: [message: MailMessage]; close: []; deleted: []; sent: [message: MailMessage] }>();
const { draft, model, dirty, saving, busy, error, hasConflict, preview, sendUncertain, editable, saveLabel, save, reload, showPreview, confirmAndSend, confirmOnly, changeAttachment } = useMailDraft(props.initial, message => {
  emit('saved', message);
  if (message.status === 'sent') emit('sent', message);
});
const deletePrompt = ref(false);
const signature = computed(() => props.accounts.find(account => account.id === model.account_id)?.signature || '');
const canSend = computed(() => editable.value && !hasConflict.value && props.accounts.some(account => account.id === model.account_id));
const close = async () => { if (!busy.value && await save()) emit('close'); };
const upload = async (event: Event) => {
  const input = event.target as HTMLInputElement;
  const files = [...(input.files || [])];
  for (const file of files) {
    await changeAttachment((id, version) => mailApi.upload(id, version, file));
    if (error.value) break;
  }
  input.value = '';
};
const remove = async () => {
  if (busy.value || !await save()) return;
  busy.value = true;
  try { await mailApi.remove(draft.value.id, draft.value.version); emit('deleted'); }
  catch (cause) { error.value = getApiErrorMessage(cause); }
  finally { busy.value = false; }
};
defineExpose({ save: async () => !busy.value && await save() });
</script>

<template>
  <section class="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900" aria-label="Редактор черновика">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div><h2 class="text-lg font-bold">{{ preview ? 'Проверка перед отправкой' : draft.status === 'draft' ? 'Черновик' : 'Результат отправки' }} #{{ draft.id }}</h2><p class="text-sm text-slate-500" aria-live="polite" data-testid="mail-save-state">{{ saveLabel }}</p></div>
      <button type="button" class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700" :disabled="busy || saving" @click="close">{{ dirty ? 'Сохранить и закрыть' : 'Закрыть' }}</button>
    </header>

    <template v-if="preview">
      <p class="text-sm text-slate-600 dark:text-slate-300">Будет отправлена сохранённая версия {{ preview.version }}. Проверьте отправителя, всех получателей, полный текст и файлы.</p>
      <MailMessageContent :message="preview" preview />
      <div class="flex flex-wrap gap-3">
        <button type="button" class="rounded-xl border border-slate-300 px-4 py-2 text-sm dark:border-slate-700" :disabled="busy" @click="preview = null">Вернуться к редактированию</button>
        <button type="button" class="rounded-xl border border-brand-300 px-4 py-2 text-sm font-semibold text-brand-700 disabled:opacity-50 dark:border-brand-700 dark:text-brand-300" :disabled="busy || !preview.content_hash || !preview.csrf_token" @click="confirmOnly">Подтвердить для ChatGPT</button>
        <button type="button" class="rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" :disabled="busy || !preview.content_hash || !preview.csrf_token" @click="confirmAndSend">{{ busy ? 'Отправляем…' : 'Подтверждаю, отправить письмо' }}</button>
      </div>
      <p class="text-xs text-slate-500">«Подтвердить для ChatGPT» разрешает подключённому ChatGPT отправить эту версию после вашей отдельной команды. Редактирование письма отменяет подтверждение.</p>
    </template>
    <MailMessageContent v-else-if="draft.status !== 'draft'" :message="draft" />
    <template v-else>
      <p v-if="draft.confirmed_version === draft.version && !dirty" class="rounded-xl bg-emerald-50 p-3 text-sm text-emerald-800 dark:bg-emerald-950 dark:text-emerald-100" role="status">Версия {{ draft.version }} подтверждена и ещё не отправлена. Можно поручить отправку подключённому ChatGPT с разрешением на отправку почты. Изменения требуют новой проверки.</p>
      <fieldset class="space-y-4 disabled:opacity-70" :disabled="!editable || hasConflict">
        <label class="block"><span class="text-sm font-semibold">Отправитель</span><select v-model="model.account_id" aria-label="Отправитель" class="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"><option v-if="!accounts.length" :value="model.account_id">Нет доступного настроенного аккаунта</option><option v-for="account in accounts" :key="account.id" :value="account.id">{{ account.name }} &lt;{{ account.email }}&gt;</option></select></label>
        <div class="grid gap-3 sm:grid-cols-2"><label class="block sm:col-span-2"><span class="text-sm font-semibold">Кому</span><input v-model="model.to" aria-label="Кому" class="mt-1 w-full rounded-xl border border-slate-300 bg-transparent px-3 py-2 text-sm dark:border-slate-700" placeholder="supplier@example.com" /><span class="text-xs text-slate-500">Несколько адресов разделяйте запятой. Для разных поставщиков создавайте отдельные письма.</span></label><label class="block"><span class="text-sm font-semibold">Копия</span><input v-model="model.cc" aria-label="Копия" class="mt-1 w-full rounded-xl border border-slate-300 bg-transparent px-3 py-2 text-sm dark:border-slate-700" /></label><label class="block"><span class="text-sm font-semibold">Скрытая копия</span><input v-model="model.bcc" aria-label="Скрытая копия" class="mt-1 w-full rounded-xl border border-slate-300 bg-transparent px-3 py-2 text-sm dark:border-slate-700" /></label></div>
        <label class="block"><span class="text-sm font-semibold">Тема</span><input v-model="model.subject" aria-label="Тема" class="mt-1 w-full rounded-xl border border-slate-300 bg-transparent px-3 py-2 text-sm dark:border-slate-700" /></label>
        <label class="block"><span class="text-sm font-semibold">Текст</span><textarea v-model="model.body_text" aria-label="Текст" rows="12" class="mt-1 w-full rounded-xl border border-slate-300 bg-transparent px-3 py-2 text-sm leading-6 dark:border-slate-700" /></label>
        <button v-if="signature && !model.body_text.includes(signature)" type="button" class="text-sm font-semibold text-brand-700 dark:text-brand-300" @click="model.body_text = [model.body_text, signature].filter(Boolean).join('\n\n')">Добавить подпись компании</button>
        <div class="space-y-2"><h3 class="text-sm font-semibold">Вложения</h3><label class="inline-flex cursor-pointer rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700">Прикрепить файлы<input type="file" multiple class="sr-only" aria-label="Прикрепить файлы" :disabled="!editable || hasConflict" @change="upload" /></label><ul class="space-y-2 text-sm"><li v-for="(attachment, index) in draft.attachments" :key="attachment.id || index" class="flex items-center justify-between gap-3"><span class="break-all">{{ attachment.filename }} · {{ (attachment.size / 1024).toFixed(1) }} КБ</span><button v-if="attachment.id" type="button" class="text-red-600 dark:text-red-300" @click="changeAttachment((id, version) => mailApi.removeAttachment(id, attachment.id!, version))">Убрать</button></li></ul><p class="text-xs text-slate-500">Файлы сохраняются приватно и фиксируются вместе с версией письма.</p></div>
        <details><summary class="cursor-pointer text-sm font-semibold text-slate-600 dark:text-slate-300">Связать с заказом или клиентом (необязательно)</summary><div class="mt-3 grid gap-3 sm:grid-cols-2"><label class="text-sm">Номер заказа<input v-model="model.order_id" type="number" min="1" step="1" aria-label="Номер заказа" class="mt-1 w-full rounded-xl border border-slate-300 bg-transparent px-3 py-2 dark:border-slate-700" /></label><label class="text-sm">Номер клиента<input v-model="model.customer_id" type="number" min="1" step="1" aria-label="Номер клиента" class="mt-1 w-full rounded-xl border border-slate-300 bg-transparent px-3 py-2 dark:border-slate-700" /></label></div><p class="mt-1 text-xs text-slate-500">Доступность заказа и клиента проверяется при сохранении.</p></details>
      </fieldset>
      <div class="flex flex-wrap gap-3"><button type="button" class="rounded-xl border border-slate-300 px-4 py-2 text-sm dark:border-slate-700" :disabled="busy || hasConflict || sendUncertain" @click="save">{{ saving ? 'Сохраняем…' : 'Сохранить черновик' }}</button><button type="button" class="rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" :disabled="!canSend" @click="showPreview">Проверить и отправить</button><button type="button" class="ml-auto text-sm text-red-600 disabled:opacity-50 dark:text-red-300" :disabled="busy || saving || sendUncertain" @click="deletePrompt = !deletePrompt">Удалить черновик</button></div>
      <div v-if="deletePrompt" class="rounded-xl bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950 dark:text-red-100"><p>Удалить черновик и его вложения?</p><button type="button" class="mt-2 font-semibold underline" :disabled="busy || saving" @click="remove">Удалить</button><button type="button" class="ml-4 underline" @click="deletePrompt = false">Оставить</button></div>
    </template>
    <p v-if="error" role="alert" class="rounded-xl bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">{{ error }}</p>
    <p v-if="!accounts.length && draft.status === 'draft'" class="text-sm text-amber-700 dark:text-amber-300">Отправка недоступна: у вашей компании нет доступного настроенного почтового аккаунта.</p>
    <button v-if="hasConflict || sendUncertain || ['sending', 'pending', 'unknown'].includes(draft.status)" type="button" class="text-sm font-semibold text-brand-700 dark:text-brand-300" :disabled="busy || saving" @click="reload">{{ hasConflict ? 'Открыть актуальную версию (заменит текст в форме)' : 'Проверить статус' }}</button>
  </section>
</template>
