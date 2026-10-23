import { OpenAPI } from '../client/core/OpenAPI';
import { request } from '../client/core/request';
import type { DashboardDetailResponse, DashboardPeriodRange } from '../client';
import type { DashboardKpiKey } from './dashboard-overview';

export const getDashboardDetails = (metric: DashboardKpiKey, period: DashboardPeriodRange, offset = 0) => request<DashboardDetailResponse>(OpenAPI, {
  method: 'GET', url: `/api/manager/dashboard/details/${metric}`,
  query: { start: period.start, end: period.end, limit: 50, offset },
});
