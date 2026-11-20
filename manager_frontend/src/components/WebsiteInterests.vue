<script setup lang="ts">
import type { WebsiteInterests, WebsiteLeadAttribution } from '../client';

defineProps<{ interests?: WebsiteInterests | null; attribution?: WebsiteLeadAttribution | null }>();
const labels: Record<string, string> = { product: 'Товар', article: 'Статья', service: 'Услуга', topic: 'Тема' };
const duration = (seconds: number) => seconds >= 60 ? `≈ ${Math.max(1, Math.round(seconds / 60))} мин` : '< 1 мин';
const channels: Record<WebsiteLeadAttribution['channel'], string> = {
  organic_search: 'Поиск', paid: 'Реклама', referral: 'Переход по ссылке',
  campaign: 'Помеченная ссылка', unknown: 'Источник неизвестен',
};
const sources = { google: 'Google', yandex: 'Яндекс', bing: 'Bing', duckduckgo: 'DuckDuckGo', chatgpt: 'ChatGPT' };
const forms: Record<WebsiteLeadAttribution['form_id'], string> = {
  contact: 'Обратная связь', checkout: 'Оформление заказа', installation_calculator: 'Калькулятор монтажа',
  installation_estimate: 'Монтаж по фото', repair_diagnostic: 'Диагностика ремонта',
  product_availability: 'Сообщить о поступлении', multi_split: 'Подбор мультисплита',
};
</script>

<template>
  <section v-if="attribution?.consent" class="my-4 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm dark:border-slate-700 dark:bg-slate-900">
    <h3 class="font-semibold">Вход на сайт</h3>
    <dl class="mt-2 space-y-1">
      <div><dt class="inline text-slate-500">Источник: </dt><dd class="inline">{{ channels[attribution.channel] }}<span v-if="attribution.source"> · {{ sources[attribution.source] }}</span></dd></div>
      <div><dt class="inline text-slate-500">Страница входа: </dt><dd class="inline break-all">{{ attribution.landing_path }}</dd></div>
      <div><dt class="inline text-slate-500">Отправка: </dt><dd class="inline break-all">{{ forms[attribution.form_id] }} · {{ attribution.page_path }}</dd></div>
    </dl>
  </section>
  <section v-if="interests?.consent && interests.items.length" class="my-4 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm dark:border-slate-700 dark:bg-slate-900" data-testid="website-interests">
    <h3 class="font-semibold">Интересы на сайте</h3>
    <p class="mt-1 text-xs text-slate-500">Передано с согласия посетителя · примерное активное время</p>
    <ul class="mt-3 space-y-3">
      <li v-for="(item, index) in interests.items" :key="`${item.page_path}-${index}`" class="min-w-0" data-testid="website-interest-item">
        <div class="flex flex-wrap items-baseline justify-between gap-x-3">
          <span class="break-words font-medium">{{ labels[item.kind] }}: {{ item.title }}</span>
          <span class="whitespace-nowrap text-xs text-slate-500">{{ duration(item.active_seconds) }}</span>
        </div>
        <p class="mt-1 break-all text-xs text-slate-500">{{ item.page_path }}<span v-if="item.product_id"> · Товар #{{ item.product_id }}</span></p>
        <p v-if="item.topics?.length" class="mt-1 text-xs text-slate-600">Темы: {{ item.topics.join(', ') }}</p>
      </li>
    </ul>
  </section>
</template>
