<script setup lang="ts">
import type { IncomingOrderContext } from '../../client';
defineProps<{ context: IncomingOrderContext }>();
const wishedDate = (context: IncomingOrderContext) => context.requested_at
  ? new Intl.DateTimeFormat('ru-BY', context.date_precision === 'date'
    ? { timeZone: context.source_timezone, dateStyle: 'medium' }
    : { timeZone: context.source_timezone, dateStyle: 'medium', timeStyle: 'short' }).format(new Date(context.requested_at))
  : context.requested_time_text;
const sourceTime = (context: IncomingOrderContext) => context.source_occurred_at
  ? new Intl.DateTimeFormat('ru-BY', { timeZone: context.source_timezone, dateStyle: 'medium', timeStyle: 'short' }).format(new Date(context.source_occurred_at))
  : 'неизвестно';
const fieldLabels: Record<string, string> = { phone: 'Телефон', region_text: 'Район', address_text: 'Адрес', requested_at: 'Желаемая дата', requested_time_text: 'Пожелание по времени', call_before_visit: 'Предварительный звонок', clarification_requested: 'Поручение на уточнение' };
</script>
<template>
  <section class="mt-4 rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm dark:border-blue-800 dark:bg-blue-950/30" data-testid="order-incoming-context">
    <h3 class="font-semibold">Договорённости из входящего #{{ context.lead_id }}</h3>
    <p v-if="context.region_text">Район: {{ context.region_text }}</p>
    <p v-if="context.address_text">Адрес: {{ context.address_text }}</p>
    <p v-if="wishedDate(context)">Пожелание клиента: {{ wishedDate(context) }} · выезд не подтверждён</p>
    <p v-if="context.call_before_visit">Созвониться перед выездом</p>
    <p v-if="context.clarification_task_id"><a class="underline" :href="`/manager/tasks?taskId=${context.clarification_task_id}`">Поручение на уточнение #{{ context.clarification_task_id }}</a></p>
    <details class="mt-2"><summary class="cursor-pointer">Исходный текст и происхождение</summary>
      <p class="mt-2 whitespace-pre-wrap">{{ context.original_text }}</p>
      <p v-if="context.request_text !== context.original_text" class="mt-2 whitespace-pre-wrap">Исправлено: {{ context.request_text }}</p>
      <p>Время источника: {{ sourceTime(context) }} · {{ context.source_timezone }}</p>
      <p v-for="(source, field) in context.field_sources" :key="field" v-show="fieldLabels[field]">{{ fieldLabels[field] }}: {{ source === 'text' ? 'из исходного текста' : 'передано при сохранении' }}</p>
      <p>Версия входящего: {{ context.lead_version }}</p>
      <a class="underline" :href="`/manager/leads?incomingId=${context.lead_id}`">Исходное обращение #{{ context.lead_id }}</a>
    </details>
  </section>
</template>
