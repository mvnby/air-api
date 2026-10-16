<script setup lang="ts">
import type { CompanySite } from '../../services/manager-companies';
defineProps<{ sites: CompanySite[] }>();
const siteStatus = { active: 'Активен', draft: 'Черновик', disabled: 'Отключён' };
const domainStatus = { active: 'Подключён', pending: 'Ожидает подтверждения', disabled: 'Отключён' };
</script>
<template>
  <div class="grid gap-3 sm:grid-cols-2">
    <article v-for="site in sites" :key="site.id" class="min-w-0 rounded-lg border bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900">
      <div class="flex flex-wrap items-center gap-2"><h3 class="font-semibold">{{ site.display_name }}</h3><span v-if="site.is_default" class="rounded bg-blue-100 px-2 py-0.5 text-xs text-blue-800">Основной</span><span class="text-xs text-gray-500">{{ siteStatus[site.status] }}</span></div>
      <p class="mt-1 text-sm text-gray-500">{{ site.city || 'Город не указан' }} · {{ site.currency }} · {{ site.default_locale }}</p>
      <ul class="mt-3 space-y-1 text-sm"><li v-for="domain in site.domains" :key="domain.id" class="break-all"><span class="font-medium">{{ domain.hostname }}</span><span class="ml-2 text-xs text-gray-500">{{ domain.is_primary ? 'Основной · ' : '' }}{{ domain.verified_at ? 'Подтверждён' : 'Не подтверждён' }} · {{ domainStatus[domain.status] }}</span></li></ul>
      <p v-if="!site.domains.length" class="mt-3 text-sm text-gray-500">Домены не добавлены</p>
    </article>
    <p v-if="!sites.length" class="text-sm text-gray-500">Сайтов пока нет.</p>
  </div>
</template>
