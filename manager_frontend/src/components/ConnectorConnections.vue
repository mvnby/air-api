<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';
import { connectorConnectionsApi, type ConnectorGrant } from '../services/connector-connections-api';

const grants = ref<ConnectorGrant[]>([]);
const loading = ref(true);
const revoking = ref<number | null>(null);
const error = ref('');
const copied = ref(false);
const copyError = ref('');
const serverUrl = 'https://api.mvn.by/api/connector/mcp';
const copyServerUrl = async () => {
  copied.value = false;
  copyError.value = '';
  try {
    await navigator.clipboard.writeText(serverUrl);
    if (mounted) copied.value = true;
  } catch {
    if (mounted) copyError.value = 'Не удалось скопировать адрес. Выделите его и скопируйте вручную.';
  }
};
let mounted = true;
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
    <details data-testid="connector-quickstart" :open="!loading && !error && !grants.length" class="mt-5 rounded-lg border border-gray-200 p-4">
      <summary class="cursor-pointer font-medium text-gray-900">Как подключить Kitlane к ChatGPT</summary>
      <ol class="mt-3 list-decimal space-y-3 pl-5 text-sm text-gray-700">
        <li>Используйте свой логин Kitlane, выданный владельцем компании. У каждого сотрудника своё подключение.</li>
        <li>В ChatGPT откройте «Плагины» → «Добавить свой MCP-сервер». Назовите его Kitlane, вставьте адрес ниже и выберите OAuth. Если запрашивается ID клиента, укажите <code>kitlane-chatgpt</code>; секрет клиента не нужен.</li>
        <li>Войдите в Kitlane, проверьте название своей компании и выберите нужные разрешения. Для подготовки писем достаточно чтения почты и редактирования черновиков.</li>
        <li>Вернитесь в ChatGPT и попросите Kitlane показать ваши поручения или подготовить черновик. Подключение появится в списке выше.</li>
      </ol>
      <p class="mt-3 break-all rounded bg-gray-50 p-2 font-mono text-xs" data-testid="connector-server-url">{{ serverUrl }}</p>
      <button type="button" class="mt-2 text-sm font-medium text-brand-700" @click="copyServerUrl">{{ copied ? 'Адрес скопирован' : 'Скопировать адрес сервера' }}</button>
      <p v-if="copyError" role="alert" class="mt-2 text-sm text-red-700">{{ copyError }}</p>
      <p class="mt-3 text-xs text-gray-500">Это личное подключение. Доступность добавления своего сервера зависит от вашего аккаунта ChatGPT. Если такой пункт отсутствует, обратитесь к администратору рабочего пространства.</p>
      <p class="mt-2 text-xs text-gray-500">Для новых разрешений подключитесь заново. Почта доступна после настройки аккаунта вашей компании; подключение ChatGPT само по себе почтовый аккаунт не создаёт.</p>
    </details>
  </div>
</template>
