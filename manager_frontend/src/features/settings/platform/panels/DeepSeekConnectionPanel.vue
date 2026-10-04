<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { ManagerPlatformAiService } from '../../../../client';
import { confirmDialog } from '../../../../services/ui-feedback';
import { usePlatformSettingsContext } from '../platform-settings-context';

const { activeSettingsTab } = usePlatformSettingsContext();
type Status = {
  configured: boolean;
  enabled: boolean;
  source: 'settings' | 'environment' | 'none';
  environment_key_available: boolean;
};
const status = ref<Status>({ configured: false, enabled: false, source: 'none', environment_key_available: false });
const key = ref('');
const busy = ref(false);
const message = ref('');
const error = ref('');

const load = async () => {
  busy.value = true;
  error.value = '';
  try {
    status.value = await ManagerPlatformAiService.getDeepseekConnection() as Status;
  } catch {
    error.value = 'Не удалось загрузить подключение DeepSeek.';
  } finally {
    busy.value = false;
  }
};

const save = async () => {
  busy.value = true;
  error.value = '';
  message.value = '';
  try {
    status.value = await ManagerPlatformAiService.putDeepseekConnection({ key: key.value || null }) as Status;
    key.value = '';
    message.value = 'Ключ сохранён.';
  } catch {
    error.value = 'Не удалось сохранить ключ. Проверьте его и повторите попытку.';
  } finally {
    busy.value = false;
  }
};

const toggle = async () => {
  busy.value = true;
  error.value = '';
  message.value = '';
  try {
    status.value = await ManagerPlatformAiService.putDeepseekConnection({ enabled: !status.value.enabled }) as Status;
    message.value = status.value.enabled ? 'Подключение включено.' : 'Подключение отключено.';
  } catch {
    error.value = 'Не удалось изменить состояние подключения.';
  } finally {
    busy.value = false;
  }
};

const importEnvironmentKey = async () => {
  busy.value = true;
  error.value = '';
  message.value = '';
  try {
    status.value = await ManagerPlatformAiService.importDeepseekEnvironmentKey() as Status;
    message.value = 'Текущий ключ перенесён в настройки.';
  } catch {
    error.value = 'Не удалось перенести текущий ключ.';
  } finally {
    busy.value = false;
  }
};

const test = async () => {
  busy.value = true;
  error.value = '';
  message.value = '';
  try {
    const result = await ManagerPlatformAiService.testDeepseekConnection() as { ok: boolean };
    message.value = result.ok ? 'Проверочный запрос выполнен.' : 'Проверочный запрос не удался.';
  } catch {
    error.value = 'Проверочный запрос не выполнен. Проверьте ключ и соединение.';
  } finally {
    busy.value = false;
  }
};

const remove = async () => {
  if (!await confirmDialog({
    title: 'Удалить ключ DeepSeek?',
    description: 'Ключ будет удалён, а подключение отключено.',
    confirmText: 'Удалить ключ',
    variant: 'danger',
  })) return;
  busy.value = true;
  error.value = '';
  message.value = '';
  try {
    status.value = await ManagerPlatformAiService.deleteDeepseekConnection() as Status;
    key.value = '';
    message.value = 'Ключ удалён, подключение отключено.';
  } catch {
    error.value = 'Не удалось удалить подключение.';
  } finally {
    busy.value = false;
  }
};

onMounted(() => { void load(); });
</script>

<template>
  <section v-show="activeSettingsTab === 'aiConnection'" class="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-800 sm:p-6" data-testid="deepseek-connection">
    <h2 class="text-lg font-semibold text-gray-900 dark:text-white">DeepSeek — AI-подключение</h2>
    <p class="mt-2 text-sm text-gray-600 dark:text-slate-300">Ключ доступен только администраторам платформы и хранится на сервере. Запросы идут через сервер.</p>
    <p class="mt-3 text-sm font-medium text-gray-800 dark:text-slate-100">{{ status.configured ? 'Ключ настроен' : 'Ключ не настроен' }} · {{ status.enabled ? 'Подключение включено' : 'Подключение отключено' }}<span v-if="status.source === 'environment'"> · используется ключ окружения</span></p>
    <p v-if="message" role="status" class="mt-2 text-sm text-emerald-700 dark:text-emerald-300">{{ message }}</p>
    <p v-if="error" role="alert" class="mt-2 text-sm text-red-700 dark:text-red-300">{{ error }}</p>
    <div class="mt-5 grid gap-4 md:grid-cols-2">
      <label class="block text-sm font-medium text-gray-700 dark:text-slate-200">API-ключ DeepSeek
        <input v-model="key" type="password" autocomplete="new-password" :placeholder="status.configured ? 'Оставьте пустым, чтобы сохранить текущий' : 'Вставьте API-ключ DeepSeek'" class="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-slate-600 dark:bg-slate-900 dark:text-white" data-testid="deepseek-key" />
      </label>
    </div>
    <div class="mt-5 flex flex-wrap gap-2">
      <button type="button" :disabled="busy || (!key && !status.configured)" class="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50" @click="save">Сохранить ключ</button>
      <button v-if="status.environment_key_available && (status.source !== 'settings' || !status.configured)" type="button" :disabled="busy" class="rounded-lg border border-gray-300 px-4 py-2 text-sm dark:border-slate-600 dark:text-white disabled:opacity-50" @click="importEnvironmentKey">Перенести текущий ключ</button>
      <button type="button" :disabled="busy || !status.configured" class="rounded-lg border border-gray-300 px-4 py-2 text-sm dark:border-slate-600 dark:text-white disabled:opacity-50" @click="test">Проверить запрос</button>
      <button type="button" :disabled="busy || !status.configured" class="rounded-lg border border-gray-300 px-4 py-2 text-sm dark:border-slate-600 dark:text-white disabled:opacity-50" @click="toggle">{{ status.enabled ? 'Отключить' : 'Включить' }}</button>
      <button type="button" :disabled="busy || !status.configured" class="rounded-lg px-4 py-2 text-sm text-red-700 dark:text-red-300 disabled:opacity-50" @click="remove">Удалить ключ</button>
    </div>
    <p class="mt-4 text-xs text-gray-500 dark:text-slate-400">Проверка отправляет короткий синтетический запрос в DeepSeek и может расходовать баланс.</p>
  </section>
</template>
