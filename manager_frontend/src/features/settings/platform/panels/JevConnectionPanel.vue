<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { ManagerPlatformAiService } from '../../../../client';
import type { JevShadowReport, JevStatus } from '../../../../client';
import { confirmDialog } from '../../../../services/ui-feedback';
import { usePlatformSettingsContext } from '../platform-settings-context';

const { activeSettingsTab } = usePlatformSettingsContext();
type Connection = JevStatus;
type Report = JevShadowReport;
type ReportItem = JevShadowReport['items'][number];

const emptyConnection: Connection = { configured: false, enabled: false, model: '1.13.0', daily_budget_usd: 0.05, max_daily_requests: 500, today_requests: 0, today_budget_used_usd: 0 };
const connection = ref<Connection>({ ...emptyConnection });
const key = ref('');
const budget = ref('0.05');
const report = ref<Report | null>(null);
const disagreementsOnly = ref(false);
const busy = ref(false);
const reportBusy = ref(false);
const message = ref('');
const error = ref('');
const visibleItems = computed(() => report.value?.items.slice(0, 20) ?? []);

const load = async () => {
  busy.value = true;
  error.value = '';
  try {
    connection.value = await ManagerPlatformAiService.getJevConnection();
    budget.value = String(connection.value.daily_budget_usd ?? 0.05);
  } catch {
    error.value = 'Не удалось загрузить настройки Jev.';
  } finally {
    busy.value = false;
  }
};

const refreshReport = async () => {
  reportBusy.value = true;
  error.value = '';
  try {
    const [nextReport, nextConnection] = await Promise.all([
      ManagerPlatformAiService.getJevShadowReport(undefined, disagreementsOnly.value, 20),
      ManagerPlatformAiService.getJevConnection(),
    ]);
    report.value = nextReport;
    connection.value = nextConnection;
  } catch {
    error.value = 'Не удалось загрузить отчёт теневых проверок.';
  } finally {
    reportBusy.value = false;
  }
};

const save = async () => {
  busy.value = true;
  error.value = '';
  message.value = '';
  try {
    connection.value = await ManagerPlatformAiService.putJevConnection({
      key: key.value || null,
      daily_budget_usd: Number(budget.value),
    });
    key.value = '';
    budget.value = String(connection.value.daily_budget_usd ?? Number(budget.value));
    message.value = 'Настройки Jev сохранены.';
  } catch {
    error.value = 'Не удалось сохранить настройки Jev.';
  } finally {
    busy.value = false;
  }
};

const toggle = async () => {
  busy.value = true;
  error.value = '';
  message.value = '';
  try {
    connection.value = await ManagerPlatformAiService.putJevConnection({ enabled: !connection.value.enabled });
    message.value = connection.value.enabled ? 'Параллельные проверки Jev включены.' : 'Параллельные проверки Jev отключены.';
  } catch {
    error.value = 'Не удалось изменить состояние Jev.';
  } finally {
    busy.value = false;
  }
};

const test = async () => {
  busy.value = true;
  error.value = '';
  message.value = '';
  try {
    const result = await ManagerPlatformAiService.testJevConnection();
    message.value = result.ok ? `Платный проверочный запрос выполнен: ${result.model}.` : 'Проверочный запрос Jev не удался.';
  } catch {
    error.value = 'Проверочный запрос Jev не выполнен. Проверьте ключ и соединение.';
  } finally {
    busy.value = false;
  }
};

const toggleDisagreements = () => {
  disagreementsOnly.value = !disagreementsOnly.value;
  void refreshReport();
};

const remove = async () => {
  if (!await confirmDialog({
    title: 'Удалить ключ Jev?',
    description: 'Ключ будет удалён, параллельные проверки будут отключены.',
    confirmText: 'Удалить ключ',
    variant: 'danger',
  })) return;
  busy.value = true;
  error.value = '';
  message.value = '';
  try {
    connection.value = await ManagerPlatformAiService.deleteJevConnection();
    key.value = '';
    message.value = 'Ключ Jev удалён, параллельные проверки отключены.';
  } catch {
    error.value = 'Не удалось удалить ключ Jev.';
  } finally {
    busy.value = false;
  }
};

const statusLabel = (status: string) => ({ queued: 'В очереди', running: 'В работе', completed: 'Завершено', failed: 'Ошибка' } as Record<string, string>)[status] ?? 'Неизвестно';
const sourceLabel = (source: ReportItem['source']) => source === 'email' ? 'Почта · основная DeepSeek' : 'Заявка Belzakupki';
const yesNo = (value: boolean | null) => value === null ? '—' : value ? 'Да' : 'Нет';
const kindLabel = (kind: string | null) => ({ tender: 'Тендер', customer_request: 'Запрос клиента', service: 'Сервис', supplier_offer: 'Предложение поставщика', advertising: 'Реклама', other: 'Прочее' } as Record<string, string>)[kind || ''] ?? '—';
const errorLabel = (code: string | null) => {
  if (!code) return '';
  const messages: Record<string, string> = {
    provider_error: 'Провайдер Jev недоступен',
    timeout: 'Истекло время ожидания',
    authentication_rejected: 'Провайдер Jev отклонил ключ',
    rate_limited: 'Слишком много запросов к провайдеру Jev',
    provider_unavailable: 'Провайдер Jev временно недоступен',
    provider_rejected: 'Провайдер Jev отклонил запрос',
    invalid_response: 'Провайдер Jev вернул некорректный ответ',
    invalid_credential: 'Ключ Jev некорректен',
    not_configured: 'Ключ Jev не настроен',
    credential_store_unavailable: 'Хранилище ключа недоступно',
    credential_unreadable: 'Не удалось прочитать ключ',
    invalid_budget: 'Некорректный лимит расходов',
  };
  return messages[code] ?? 'Запрос не выполнен';
};

onMounted(() => {
  void load();
  void refreshReport();
});
</script>

<template>
  <section v-show="activeSettingsTab === 'aiConnection'" class="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-800 sm:p-6" data-testid="jev-connection">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 class="text-lg font-semibold text-gray-900 dark:text-white">Jev — параллельные проверки</h2>
        <p class="mt-1 text-sm text-gray-600 dark:text-slate-300">TypeSafe · модель 1.13.0. Jev оценивает заявки параллельно. Письма обрабатывает основная DeepSeek-модель; для заявок Belzakupki решение принимает текущий основной сценарий.</p>
      </div>
      <p class="text-sm font-medium text-gray-800 dark:text-slate-100">{{ connection.configured ? 'Ключ настроен' : 'Ключ не настроен' }} · {{ connection.enabled ? 'Включено' : 'Выключено' }}</p>
    </div>
    <p v-if="message" role="status" class="mt-2 text-sm text-emerald-700 dark:text-emerald-300">{{ message }}</p>
    <p v-if="error" role="alert" class="mt-2 text-sm text-red-700 dark:text-red-300">{{ error }}</p>
    <div class="mt-4 grid gap-3 md:grid-cols-[minmax(0,1fr)_12rem]">
      <label class="block text-sm font-medium text-gray-700 dark:text-slate-200">API-ключ Jev
        <input v-model="key" type="password" autocomplete="new-password" :placeholder="connection.configured ? 'Оставьте пустым, чтобы сохранить текущий' : 'Вставьте API-ключ Jev'" class="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-slate-600 dark:bg-slate-900 dark:text-white" data-testid="jev-key" />
      </label>
      <label class="block text-sm font-medium text-gray-700 dark:text-slate-200">Лимит расходов в день, USD
        <input v-model="budget" type="number" min="0.01" step="0.01" class="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-slate-600 dark:bg-slate-900 dark:text-white" data-testid="jev-budget" />
      </label>
    </div>
    <p class="mt-2 text-xs text-gray-500 dark:text-slate-400">Лимит по умолчанию — $0.05 в день. Ключ доступен только администраторам и хранится на сервере.</p>
    <p class="mt-1 text-xs text-gray-500 dark:text-slate-400">Сегодня: {{ connection.today_requests ?? 0 }} / {{ connection.max_daily_requests }} запросов · занято в бюджете: ${{ Number(connection.today_budget_used_usd ?? 0).toFixed(6) }}. Неуспешные запросы учитываются с резервом.</p>
    <div class="mt-4 flex flex-wrap gap-2">
      <button type="button" data-testid="jev-save" :disabled="busy || !Number.isFinite(Number(budget)) || Number(budget) <= 0 || (!key && !connection.configured)" class="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50" @click="save">Сохранить ключ и лимит</button>
      <button type="button" data-testid="jev-toggle" :disabled="busy || !connection.configured" class="rounded-lg border border-gray-300 px-4 py-2 text-sm dark:border-slate-600 dark:text-white disabled:opacity-50" @click="toggle">{{ connection.enabled ? 'Отключить' : 'Включить' }}</button>
      <button type="button" data-testid="jev-test" :disabled="busy || !connection.configured" class="rounded-lg border border-gray-300 px-4 py-2 text-sm dark:border-slate-600 dark:text-white disabled:opacity-50" @click="test">Проверить ключ</button>
      <button type="button" data-testid="jev-remove" :disabled="busy || !connection.configured" class="rounded-lg px-4 py-2 text-sm text-red-700 dark:text-red-300 disabled:opacity-50" @click="remove">Удалить ключ</button>
    </div>

    <div class="mt-6 border-t border-gray-200 pt-5 dark:border-slate-700">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <h3 class="text-base font-semibold text-gray-900 dark:text-white">Отчёт параллельных проверок</h3>
        <div class="flex gap-2">
          <button type="button" data-testid="jev-disagreements-toggle" class="rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-slate-600 dark:text-white" @click="toggleDisagreements">{{ disagreementsOnly ? 'Показать все' : 'Только расхождения' }}</button>
          <button type="button" data-testid="jev-report-refresh" :disabled="reportBusy" class="rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-slate-600 dark:text-white disabled:opacity-50" @click="refreshReport">Обновить</button>
        </div>
      </div>
      <template v-if="report">
        <dl class="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
          <div><dt class="text-gray-500 dark:text-slate-400">Успешно</dt><dd class="font-semibold">{{ report.completed }}</dd></div>
          <div><dt class="text-gray-500 dark:text-slate-400">Расхождения</dt><dd class="font-semibold">{{ report.disagreements }} / {{ report.comparable }} сравнимых</dd></div>
          <div><dt class="text-gray-500 dark:text-slate-400">Ошибки</dt><dd class="font-semibold">{{ report.failed }}</dd></div>
          <div><dt class="text-gray-500 dark:text-slate-400">Оценочный расход</dt><dd class="font-semibold">${{ report.estimated_usd.toFixed(6) }}</dd></div>
        </dl>
        <p class="mt-2 text-xs text-gray-500 dark:text-slate-400">В очереди: {{ report.queued }} · выполняются: {{ report.running }} · совпадений: {{ report.agreements }} · входных токенов: {{ report.input_tokens }} · медиана: {{ report.median_duration_ms === null ? '—' : `${report.median_duration_ms} мс` }}</p>
        <div class="mt-3 max-h-80 overflow-auto rounded-lg border border-gray-200 dark:border-slate-700">
          <table class="w-full text-left text-xs">
            <thead class="bg-gray-50 text-gray-600 dark:bg-slate-900 dark:text-slate-300"><tr><th class="p-2">Дата / источник</th><th class="p-2">Заявка</th><th class="p-2">Статус</th><th class="p-2">Основная / Jev</th><th class="p-2">Модели / тип</th><th class="p-2">Оценочный расход</th></tr></thead>
            <tbody>
              <tr v-for="item in visibleItems" :key="item.id" class="border-t border-gray-200 align-top dark:border-slate-700">
                <td class="p-2">{{ new Date(item.created_at).toLocaleString() }}<br />{{ sourceLabel(item.source) }}</td>
                <td class="max-w-64 p-2"><details><summary class="cursor-pointer">{{ item.subject || 'Заявка' }}</summary><p class="mt-1 max-h-36 overflow-auto whitespace-pre-wrap text-gray-600 dark:text-slate-300">{{ item.state || 'Исходное описание отсутствует.' }}</p></details></td>
                <td class="p-2">{{ statusLabel(item.status) }}<span v-if="item.error_code"> · {{ errorLabel(item.error_code) }}</span></td>
                <td class="p-2">{{ yesNo(item.primary_is_relevant) }} / {{ yesNo(item.jev_is_relevant) }}</td>
                <td class="p-2"><span>{{ item.primary_provider === 'deepseek' ? 'DeepSeek' : 'Сервис закупок' }}{{ item.primary_model_requested ? ` / ${item.primary_model_requested}` : '' }}</span><br /><span>Jev: {{ item.model || '—' }} · {{ kindLabel(item.kind) }}<span v-if="item.hvac_probability !== null"> · климатический спрос {{ Math.round(item.hvac_probability * 100) }}%</span></span><br /><span class="text-gray-500 dark:text-slate-400">Время: {{ item.primary_duration_ms === null ? '—' : `${item.primary_duration_ms} мс` }} / {{ item.duration_ms === null ? '—' : `${item.duration_ms} мс` }}</span></td>
                <td class="whitespace-nowrap p-2">{{ item.estimated_usd === null ? '—' : `$${item.estimated_usd.toFixed(6)}` }}</td>
              </tr>
              <tr v-if="visibleItems.length === 0"><td colspan="6" class="p-3 text-center text-gray-500 dark:text-slate-400">Записей пока нет.</td></tr>
            </tbody>
          </table>
        </div>
      </template>
      <p v-else-if="reportBusy" class="mt-3 text-sm text-gray-500 dark:text-slate-400">Загрузка отчёта…</p>
    </div>
    <p class="mt-4 text-xs text-gray-500 dark:text-slate-400">Проверка ключа отправляет платный запрос внешнему провайдеру и может расходовать баланс.</p>
  </section>
</template>
