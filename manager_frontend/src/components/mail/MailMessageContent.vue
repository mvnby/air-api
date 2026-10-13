<script setup lang="ts">
import { ref } from 'vue';
import { downloadMailAttachment, mailStatusLabel, type MailAttachment, type MailMessage } from '../../services/mail-workspace-api';
import { getApiErrorMessage } from '../../utils/api-errors';

defineProps<{ message: MailMessage; preview?: boolean }>();
const downloading = ref<string | null>(null);
const error = ref('');
const download = async (attachment: MailAttachment) => {
  if (downloading.value) return;
  downloading.value = attachment.filename;
  error.value = '';
  try { await downloadMailAttachment(attachment); }
  catch (cause) { error.value = getApiErrorMessage(cause); }
  finally { downloading.value = null; }
};
</script>

<template>
  <article class="space-y-4" data-testid="mail-content">
    <p v-if="!preview" class="text-sm font-semibold">{{ mailStatusLabel(message.status) }}</p>
    <dl class="space-y-2 text-sm">
      <div><dt class="text-slate-500">Отправитель</dt><dd class="break-all">{{ message.sender_name }} &lt;{{ message.sender_email || 'Не выбран' }}&gt;</dd></div>
      <div><dt class="text-slate-500">Кому</dt><dd class="break-all">{{ message.to.join(', ') || 'Не указано' }}</dd></div>
      <div><dt class="text-slate-500">Копия</dt><dd class="break-all">{{ message.cc.join(', ') || '—' }}</dd></div>
      <div><dt class="text-slate-500">Скрытая копия</dt><dd class="break-all">{{ message.bcc.join(', ') || '—' }}</dd></div>
      <div><dt class="text-slate-500">Тема</dt><dd class="break-words font-semibold">{{ message.subject || 'Без темы' }}</dd></div>
      <div v-if="message.sent_at"><dt class="text-slate-500">Принято сервером</dt><dd>{{ new Date(message.sent_at).toLocaleString('ru-RU') }}</dd></div>
      <div v-if="message.message_id"><dt class="text-slate-500">Идентификатор письма (Message-ID)</dt><dd class="break-all">{{ message.message_id }}</dd></div>
    </dl>
    <pre class="whitespace-pre-wrap break-words rounded-xl bg-slate-50 p-4 font-sans text-sm leading-6 dark:bg-slate-950">{{ message.body_text || 'Текстовая версия не сохранена' }}</pre>
    <section>
      <h3 class="text-sm font-semibold">Вложения · {{ message.attachments.length }}</h3>
      <ul v-if="message.attachments.length" class="mt-2 space-y-2 text-sm">
        <li v-for="(attachment, index) in message.attachments" :key="attachment.id || index" class="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 p-3 dark:border-slate-700">
          <span class="break-all">{{ attachment.filename }} · {{ (attachment.size / 1024).toFixed(1) }} КБ</span>
          <button v-if="attachment.available && attachment.download_url" type="button" class="font-semibold text-brand-700 disabled:opacity-50 dark:text-brand-300" :disabled="!!downloading" @click="download(attachment)">{{ downloading === attachment.filename ? 'Скачиваем…' : 'Скачать' }}</button>
          <span v-else class="text-amber-700 dark:text-amber-300">Файл не сохранён; повторная отправка недоступна</span>
        </li>
      </ul>
      <p v-else class="mt-1 text-sm text-slate-500">Вложений нет.</p>
    </section>
    <p v-if="message.order_id || message.customer_id" class="text-sm text-slate-500">{{ message.order_id ? `Заказ #${message.order_id}` : '' }} {{ message.customer_id ? `Клиент #${message.customer_id}` : '' }}</p>
    <p v-if="message.status === 'unknown'" class="rounded-xl bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-100">Почтовый сервер мог принять письмо. Проверьте папку отправленных у провайдера и обратитесь к администратору для проверки журнала отправки. Не отправляйте письмо повторно до проверки.</p>
    <p v-if="message.error || error" role="alert" class="rounded-xl bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">{{ error || message.error }}</p>
  </article>
</template>
