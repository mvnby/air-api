<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { connectorConnectionsApi, type ConnectorGrant } from '../services/connector-connections-api';
import ConnectorConnectionCard from './ConnectorConnectionCard.vue';

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
const currentTime = ref(Date.now());
let expiryTimer: ReturnType<typeof setInterval> | undefined;
const active = (grant: ConnectorGrant) => !grant.revoked_at && Date.parse(grant.expires_at) > currentTime.value;
const activeGrants = computed(() => grants.value.filter(active));
const historicalGrants = computed(() => grants.value.filter(grant => !active(grant)));

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

onMounted(() => {
  void load();
  expiryTimer = setInterval(() => { currentTime.value = Date.now(); }, 30_000);
});
onUnmounted(() => {
  mounted = false;
  clearInterval(expiryTimer);
});
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
      <section v-if="grants.length" data-testid="connector-active" class="mt-4">
        <h3 class="font-medium text-gray-900">Активные подключения ({{ activeGrants.length }})</h3>
        <p v-if="!activeGrants.length" class="mt-2 text-sm text-gray-500">Активных подключений нет.</p>
        <ul v-else class="mt-3 divide-y divide-gray-100">
          <ConnectorConnectionCard v-for="grant in activeGrants" :key="grant.id" :grant="grant" :active="true" :revoking="revoking" @revoke="revoke" />
        </ul>
      </section>
      <details v-if="historicalGrants.length" data-testid="connector-history" class="mt-4 rounded-lg border border-gray-200 p-4">
        <summary class="cursor-pointer font-medium text-gray-900">История подключений ({{ historicalGrants.length }})</summary>
        <ul class="mt-3 divide-y divide-gray-100">
          <ConnectorConnectionCard v-for="grant in historicalGrants" :key="grant.id" :grant="grant" :active="false" :revoking="revoking" />
        </ul>
      </details>
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
