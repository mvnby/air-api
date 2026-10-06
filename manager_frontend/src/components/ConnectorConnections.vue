<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';
import { connectorConnectionsApi, type ConnectorGrant } from '../services/connector-connections-api';

const grants = ref<ConnectorGrant[]>([]);
const loading = ref(true);
const revoking = ref<number | null>(null);
const error = ref('');
let mounted = true;
const scopeLabels: Record<string, string> = {
  'kitlane:read': 'Просмотр данных',
  'kitlane:incoming:write': 'Добавление входящих',
  'kitlane:tasks:write': 'Создание и изменение личных задач',
};
const active = (grant: ConnectorGrant) => !grant.revoked_at && Date.parse(grant.expires_at) > Date.now();
const dateLabel = (date: string) => new Date(date).toLocaleDateString('ru-RU');

const load = async () => {
  loading.value = true;
  error.value = '';
  try {
    const response = await connectorConnectionsApi.list();
    if (mounted) grants.value = response.items;
  } catch {
    if (mounted) error.value = 'Не удалось загрузить подключения. Попробуйте ещё раз.';
  } finally {
    if (mounted) loading.value = false;
  }
};

const revoke = async (grant: ConnectorGrant) => {
  if (revoking.value !== null) return;
  revoking.value = grant.id;
  error.value = '';
  try {
    await connectorConnectionsApi.revoke(grant.id);
    if (mounted) grant.revoked_at = new Date().toISOString();
  } catch {
    if (mounted) error.value = 'Не удалось отключить ChatGPT. Доступ ещё действует; попробуйте снова.';
  } finally {
    if (mounted) revoking.value = null;
  }
};

onMounted(load);
onUnmounted(() => { mounted = false; });
</script>

<template>
  <div data-testid="connector-connections" class="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
    <h2 class="text-lg font-semibold text-gray-900">Подключения ChatGPT</h2>
    <p class="mt-1 text-sm text-gray-600">Здесь можно отозвать выданный вами доступ к Kitlane.</p>
    <p v-if="loading" role="status" class="mt-4 text-sm text-gray-500">Загружаем подключения…</p>
    <div v-else>
      <p v-if="error" role="alert" class="mt-4 text-sm text-red-700">{{ error }}</p>
      <button v-if="error && !grants.length" type="button" class="mt-2 text-sm font-medium text-brand-700" @click="load">Повторить</button>
      <p v-else-if="!grants.length" class="mt-4 text-sm text-gray-500">Подключений пока нет. Разрешение появится здесь после подключения Kitlane в ChatGPT.</p>
      <ul v-if="grants.length" class="mt-4 divide-y divide-gray-100">
        <li v-for="grant in grants" :key="grant.id" class="py-3 first:pt-0 last:pb-0">
          <div class="flex items-start justify-between gap-4">
            <div>
              <p class="font-medium text-gray-900">ChatGPT</p>
              <p class="mt-1 text-xs text-gray-500">Подключён {{ dateLabel(grant.created_at) }} · {{ grant.revoked_at ? 'Доступ отозван' : active(grant) ? `Доступ до ${dateLabel(grant.expires_at)}` : 'Срок доступа истёк' }}</p>
            </div>
            <button v-if="active(grant)" type="button" :data-grant-id="grant.id" :disabled="revoking !== null" class="text-sm font-medium text-red-700 hover:text-red-800 disabled:opacity-50" @click="revoke(grant)">
              {{ revoking === grant.id ? 'Отключаем…' : 'Отключить' }}
            </button>
          </div>
          <p class="mt-2 text-sm text-gray-600">{{ grant.scopes.map(scope => scopeLabels[scope] || scope).join(' · ') }}</p>
        </li>
      </ul>
    </div>
  </div>
</template>
