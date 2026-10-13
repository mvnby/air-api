<script setup lang="ts">
import type { ConnectorGrant } from '../services/connector-connections-api';

defineProps<{ grant: ConnectorGrant; active: boolean; revoking: number | null }>();
const emit = defineEmits<{ revoke: [grant: ConnectorGrant] }>();
const scopeLabels: Record<string, string> = {
  'kitlane:read': 'Просмотр данных',
  'kitlane:incoming:write': 'Добавление входящих',
  'kitlane:tasks:write': 'Создание и изменение личных задач',
  'kitlane:maintenance:write': 'Замечания, фото и черновики документов ТО',
  'kitlane:catalog:write': 'Подбор оборудования и черновики КП и счетов',
  'kitlane:mail:read': 'Чтение почты и вложений',
  'kitlane:mail:drafts:write': 'Изменение почтовых черновиков и вложений',
  'kitlane:mail:send': 'Отправка писем после подтверждения в Manager',
};
const dateTimeLabel = (value: string) => new Date(value).toLocaleString('ru-RU', {
  year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit',
});
</script>

<template>
  <li :data-connection-id="grant.id" class="py-3 first:pt-0 last:pb-0">
    <div class="flex items-start justify-between gap-4">
      <div class="min-w-0">
        <p class="font-medium text-gray-900">ChatGPT</p>
        <p class="mt-1 text-xs text-gray-500">Создано: <time :datetime="grant.created_at">{{ dateTimeLabel(grant.created_at) }}</time></p>
        <p class="mt-1 text-xs text-gray-500">Последнее использование: <time v-if="grant.last_used_at" :datetime="grant.last_used_at">{{ dateTimeLabel(grant.last_used_at) }}</time><span v-else>Данных пока нет</span></p>
        <p class="mt-1 text-xs text-gray-500">
          <template v-if="grant.revoked_at">Доступ отозван: <time :datetime="grant.revoked_at">{{ dateTimeLabel(grant.revoked_at) }}</time></template>
          <template v-else-if="active">Доступ до: <time :datetime="grant.expires_at">{{ dateTimeLabel(grant.expires_at) }}</time></template>
          <template v-else>Срок доступа истёк: <time :datetime="grant.expires_at">{{ dateTimeLabel(grant.expires_at) }}</time></template>
        </p>
      </div>
      <button v-if="active" type="button" :data-grant-id="grant.id" :disabled="revoking !== null" class="shrink-0 text-sm font-medium text-red-700 hover:text-red-800 disabled:opacity-50" @click="emit('revoke', grant)">
        {{ revoking === grant.id ? 'Отключаем…' : 'Отключить' }}
      </button>
    </div>
    <p class="mt-2 text-sm text-gray-600">{{ grant.scopes.map(scope => scopeLabels[scope] || scope).join(' · ') }}</p>
  </li>
</template>
