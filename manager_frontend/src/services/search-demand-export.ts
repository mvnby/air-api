import type { DashboardSearchQuery } from '../client';
import { formatSearchDemandProvider } from './dashboard-overview';


const csvCell = (value: string | number | null | undefined) => {
  const normalized = value == null
    ? ''
    : (typeof value === 'number' ? String(value).replace('.', ',') : value);
  return `"${normalized.replace(/"/g, '""')}"`;
};

export const buildSearchDemandCsv = (rows: DashboardSearchQuery[]) => {
  const header = ['Запрос', 'Источник', 'Клики', 'Показы', 'CTR, %', 'Средняя позиция'];
  const lines = rows.map(row => [
    row.query,
    formatSearchDemandProvider(row.provider),
    row.clicks,
    row.impressions,
    row.ctr,
    row.avg_position,
  ].map(csvCell).join(';'));
  return `\uFEFF${header.map(csvCell).join(';')}\r\n${lines.join('\r\n')}\r\n`;
};

export const downloadSearchDemandCsv = (rows: DashboardSearchQuery[], source: string) => {
  const blob = new Blob([buildSearchDemandCsv(rows)], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `poiskovye-zaprosy-${source}-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
};
