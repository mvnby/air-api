<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { ManagerPlatformAiService } from '../../../../client';
import { usePlatformSettingsContext } from '../platform-settings-context';

const { activeSettingsTab } = usePlatformSettingsContext();
type Status = { configured: boolean; enabled: boolean; selected_model: string | null };
const status = ref<Status>({ configured: false, enabled: false, selected_model: null });
const key = ref('');
const model = ref('');
const models = ref<string[]>([]);
const busy = ref(false);
const message = ref('');
const error = ref('');

const load = async () => {
  busy.value = true; error.value = '';
  try {
    status.value = await ManagerPlatformAiService.getPlatformAiApiManagerPlatformAiGet() as Status;
    model.value = status.value.selected_model || '';
  } catch { error.value = 'Не удалось загрузить подключение.'; }
  finally { busy.value = false; }
};

const save = async () => {
  busy.value = true; error.value = ''; message.value = '';
  try {
    status.value = await ManagerPlatformAiService.putPlatformAiApiManagerPlatformAiPut({
      key: key.value || null, selected_model: model.value || null,
    }) as Status;
    key.value = '';
    message.value = 'Настройки сохранены.';
  } catch { error.value = 'Не удалось сохранить настройки. Проверьте ключ и модель.'; }
  finally { busy.value = false; }
};

const toggle = async () => {
  busy.value = true; error.value = ''; message.value = '';
  try {
    status.value = await ManagerPlatformAiService.putPlatformAiApiManagerPlatformAiPut({ enabled: !status.value.enabled }) as Status;
    message.value = status.value.enabled ? 'Подключение включено.' : 'Подключение отключено.';
  } catch { error.value = 'Для включения сохраните ключ и выберите модель.'; }
  finally { busy.value = false; }
};

const discover = async () => {
  busy.value = true; error.value = ''; message.value = '';
  try {
    const response = await ManagerPlatformAiService.getPlatformAiModelsApiManagerPlatformAiModelsGet() as { items: string[] };
    models.value = response.items;
    message.value = `Каталог доступен: ${models.value.length} моделей. Поддержка текстового протокола проверяется отдельным запросом.`;
  } catch { error.value = 'Каталог недоступен. Проверьте ключ, баланс и соединение.'; }
  finally { busy.value = false; }
};

const testInference = async () => {
  busy.value = true; error.value = ''; message.value = '';
  try {
    const response = await ManagerPlatformAiService.testPlatformAiApiManagerPlatformAiTestPost() as { ok: boolean; model: string };
    message.value = response.ok ? `Текстовый запрос выполнен: ${response.model}.` : 'Модель вернула пустой ответ.';
  } catch { error.value = 'Текстовый запрос не выполнен. Возможно, модель не поддерживает Chat Completions или недоступна.'; }
  finally { busy.value = false; }
};

const remove = async () => {
  if (!window.confirm('Удалить ключ ZAPRO.SU и отключить подключение?')) return;
  busy.value = true; error.value = ''; message.value = '';
  try {
    status.value = await ManagerPlatformAiService.deletePlatformAiApiManagerPlatformAiDelete() as Status;
    key.value = ''; model.value = ''; models.value = [];
    message.value = 'Ключ удалён.';
  } catch { error.value = 'Не удалось удалить подключение.'; }
  finally { busy.value = false; }
};

onMounted(() => { void load(); });
</script>

<template>
  <section v-show="activeSettingsTab === 'aiConnection'" class="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-800 sm:p-6" data-testid="platform-ai-connection">
    <h2 class="text-lg font-semibold text-gray-900 dark:text-white">ZAPRO.SU — AI-подключение</h2>
    <p class="mt-2 text-sm text-gray-600 dark:text-slate-300">Платформенный ключ доступен только администраторам платформы. Запросы идут через сервер. Другие AI-сценарии сохраняют текущего провайдера, пока не подключены к этому адаптеру явно.</p>
    <p class="mt-3 text-sm font-medium text-gray-800 dark:text-slate-100">{{ status.configured ? 'Ключ настроен' : 'Ключ не настроен' }} · {{ status.enabled ? 'Подключение включено' : 'Подключение отключено' }}</p>
    <p v-if="message" role="status" class="mt-2 text-sm text-emerald-700 dark:text-emerald-300">{{ message }}</p>
    <p v-if="error" role="alert" class="mt-2 text-sm text-red-700 dark:text-red-300">{{ error }}</p>
    <div class="mt-5 grid gap-4 md:grid-cols-2">
      <label class="block text-sm font-medium text-gray-700 dark:text-slate-200">API-ключ
        <input v-model="key" type="password" autocomplete="new-password" :placeholder="status.configured ? 'Оставьте пустым, чтобы сохранить текущий' : 'Вставьте ключ из кабинета ZAPRO.SU'" class="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-slate-600 dark:bg-slate-900 dark:text-white" data-testid="platform-ai-key" />
      </label>
      <label class="block text-sm font-medium text-gray-700 dark:text-slate-200">Модель для текстового запроса
        <select v-model="model" class="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-slate-600 dark:bg-slate-900 dark:text-white" data-testid="platform-ai-model">
          <option value="">Выберите модель после проверки подключения</option>
          <option v-if="model && !models.includes(model)" :value="model">{{ model }} (сохранена ранее)</option>
          <option v-for="item in models" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
    </div>
    <div class="mt-5 flex flex-wrap gap-2">
      <button type="button" :disabled="busy || (!key && !status.configured)" class="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50" @click="save">Сохранить</button>
      <button type="button" :disabled="busy || !status.configured" class="rounded-lg border border-gray-300 px-4 py-2 text-sm dark:border-slate-600 dark:text-white disabled:opacity-50" @click="discover">Проверить подключение и получить модели</button>
      <button type="button" :disabled="busy || !status.selected_model" class="rounded-lg border border-gray-300 px-4 py-2 text-sm dark:border-slate-600 dark:text-white disabled:opacity-50" @click="testInference">Проверить текстовый запрос</button>
      <button type="button" :disabled="busy || !status.configured" class="rounded-lg border border-gray-300 px-4 py-2 text-sm dark:border-slate-600 dark:text-white disabled:opacity-50" @click="toggle">{{ status.enabled ? 'Отключить' : 'Включить' }}</button>
      <button type="button" :disabled="busy || !status.configured" class="rounded-lg px-4 py-2 text-sm text-red-700 dark:text-red-300 disabled:opacity-50" @click="remove">Удалить ключ</button>
    </div>
    <p class="mt-4 text-xs text-gray-500 dark:text-slate-400">Проверка каталога не подтверждает поддержку текстовых запросов. Текстовая проверка отправляет только фразу «Ответь только словом OK.» и может расходовать баланс.</p>
  </section>
</template>
