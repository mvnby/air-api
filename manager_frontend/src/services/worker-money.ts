import { OpenAPI, type ClientMoneyReceived, type WorkerCashBalance, type WorkerCashHandoverAction, type WorkerCashHandoverCreate, type WorkerMoneyCommandResult, type WorkerMoneyCorrection, type WorkerMoneyEntry, type WorkerMoneyOverview, type WorkerMoneyRecipient, type WorkerMoneyRecipients, type WorkerMoneyWorkspace } from '../client';
import { request } from '../client/core/request';
export type Currency = WorkerCashBalance['currency'];
export type MoneyCommand = WorkerCashHandoverAction;
// UI commands always send decimal strings, even though the wire schema also accepts numbers.
export type AmountCommand = Omit<ClientMoneyReceived, 'amount'> & { amount: string };
export type CashBalance = WorkerCashBalance;
export type MoneyEntry = WorkerMoneyEntry;
export type MoneyWorkspace = WorkerMoneyWorkspace;
export type MoneyOverview = WorkerMoneyOverview;
export type MoneyRecipient = WorkerMoneyRecipient;
const get = <T>(url: string, page = 1) => request<T>(OpenAPI, { method: 'GET', url, query: { page, limit: 30 } });
const post = (url: string, body: unknown) => request<WorkerMoneyCommandResult>(OpenAPI, { method: 'POST', url, headers: { 'X-Kitlane-Team': '1' }, body, mediaType: 'application/json' });
export const workerMoneyApi = {
  own: (page = 1) => get<MoneyWorkspace>('/api/installer/money', page),
  recipients: (page = 1) => get<WorkerMoneyRecipients>('/api/installer/money/recipients', page),
  receive: (id: number, body: AmountCommand) => post(`/api/installer/works/${id}/collections`, body),
  handover: (body: Omit<WorkerCashHandoverCreate, 'amount'> & { amount: string }) => post('/api/installer/money/handovers', body),
  cancel: (id: number, body: MoneyCommand) => post(`/api/installer/money/handovers/${id}/cancel`, body),
  overview: (page = 1) => get<MoneyOverview>('/api/manager/worker-money', page),
  worker: (id: number, page = 1) => get<MoneyWorkspace>(`/api/manager/worker-money/${id}`, page),
  action: (worker: number, id: number, action: 'confirm' | 'reject', body: MoneyCommand) => post(`/api/manager/worker-money/${worker}/handovers/${id}/${action}`, body),
  reverseHandover: (worker: number, id: number, body: WorkerMoneyCorrection) => post(`/api/manager/worker-money/${worker}/handovers/${id}/reverse`, body),
  reverse: (worker: number, id: number, body: WorkerMoneyCorrection) => post(`/api/manager/worker-money/${worker}/receipts/${id}/reverse`, body),
};
// Integer cents keep both validation and comparisons exact. Extra decimals are rejected.
export const moneyCents = (value: string): bigint | null => {
  if (!/^\d{1,12}([.,]\d{1,2})?$/.test(value.trim())) return null;
  const [whole = '', fraction = ''] = value.trim().replace(',', '.').split('.');
  return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'));
};
export const exactAmount = (value: string): string | null => {
  const cents = moneyCents(value);
  return cents !== null && cents > 0n ? `${cents / 100n}.${String(cents % 100n).padStart(2, '0')}` : null;
};
export const moneyConflict = (cause: unknown) => (cause as { status?: number })?.status === 409;
