import type { DashboardKpi, DashboardMarketing } from '../client';

export type DashboardMode = 'manager' | 'owner';
export type DashboardKpiKey = 'revenue' | 'new_leads' | 'sales' | 'installations' | 'active_tasks' | 'receivables';

export const DASHBOARD_MODE_STORAGE_KEY = 'manager:dashboard:mode:v1';

export const dashboardKpiOrder: Record<DashboardMode, DashboardKpiKey[]> = {
  manager: ['new_leads', 'active_tasks', 'sales', 'installations', 'revenue', 'receivables'],
  owner: ['revenue', 'sales', 'receivables', 'new_leads', 'installations', 'active_tasks'],
};

export const dashboardKpiLabels: Record<DashboardKpiKey, string> = {
  revenue: 'Оплаты за месяц',
  new_leads: 'Новые заявки',
  sales: 'Продажи',
  installations: 'Монтажи',
  active_tasks: 'Активные касания',
  receivables: 'Дебиторская задолженность',
};

export const loadDashboardMode = (): DashboardMode => {
  try {
    return window.localStorage.getItem(DASHBOARD_MODE_STORAGE_KEY) === 'owner' ? 'owner' : 'manager';
  } catch {
    return 'manager';
  }
};

export const saveDashboardMode = (mode: DashboardMode) => {
  try {
    window.localStorage.setItem(DASHBOARD_MODE_STORAGE_KEY, mode);
  } catch {
    // Dashboard remains usable where local storage is unavailable.
  }
};

export const formatDashboardNumber = (value: number | null | undefined) => (
  value == null ? '—' : new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value)
);

export const formatDashboardCurrency = (value: number | null | undefined) => (
  value == null
    ? '—'
    : new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'BYN', maximumFractionDigits: 0 }).format(value)
);

export const formatDashboardKpi = (key: DashboardKpiKey, kpi: DashboardKpi) => (
  kpi.unit === 'byn' || key === 'revenue' || key === 'receivables'
    ? formatDashboardCurrency(kpi.current)
    : formatDashboardNumber(kpi.current)
);

export type DashboardTrend = { label: string; tone: 'positive' | 'negative' | 'neutral' };

export const getDashboardTrend = (key: DashboardKpiKey, kpi: DashboardKpi): DashboardTrend => {
  if (kpi.previous == null || kpi.trend === 'unavailable' || kpi.delta_pct == null) {
    return { label: 'Срез на сейчас', tone: 'neutral' };
  }
  if (kpi.trend === 'flat') return { label: 'Без изменений', tone: 'neutral' };

  const prefix = kpi.delta_pct > 0 ? '+' : '';
  const label = `${prefix}${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(kpi.delta_pct)}% к прошлому месяцу`;
  if (key === 'receivables') {
    return { label, tone: kpi.trend === 'down' ? 'positive' : 'negative' };
  }
  return { label, tone: kpi.trend === 'up' ? 'positive' : 'negative' };
};

export const dashboardMarketingStatus = (marketing: DashboardMarketing) => {
  const messages = {
    fresh: 'Данные аналитики обновлены и готовы к работе.',
    stale: 'Данные аналитики обновлялись давно и могут быть неактуальны.',
    error: 'Интеграция аналитики временно недоступна. CRM-данные продолжают работать.',
    unconfigured: 'Подключите Яндекс Метрику, чтобы видеть визиты и источники.',
  } as const;
  const labels = {
    fresh: 'Данные актуальны',
    stale: 'Данные устарели',
    error: 'Ошибка интеграции',
    unconfigured: 'Не подключено',
  } as const;
  return { label: labels[marketing.status], message: messages[marketing.status], tone: marketing.status };
};

export const formatMarketingProvider = (provider: string | null | undefined) => {
  if (provider === 'yandex_metrika') return 'Яндекс Метрика';
  return provider || 'Веб-аналитика и реклама';
};

export const formatMarketingValue = (
  value: number | null | undefined,
  kind: 'count' | 'currency' | 'percent' = 'count',
) => {
  if (value == null) return '—';
  if (kind === 'currency') return formatDashboardCurrency(value);
  if (kind === 'percent') return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value)}%`;
  return formatDashboardNumber(value);
};
