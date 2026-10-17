import { OpenAPI, type WorkerPayAgreementItem, type ManagerWorkerPayAgreementItem, type WorkerPayBalance, type WorkerPayEntry, type WorkerPayWorkspace, type ManagerWorkerPayWorkspace, type WorkerPayOverview, type WorkerPayCandidate, type WorkerPayOrderWorkspace, type WorkerPayAgreementCreate, type WorkerMoneyCommandResult } from '../client';
import { request } from '../client/core/request';
import type { AmountCommand, MoneyCommand } from './worker-money';
export type PayAgreement = WorkerPayAgreementItem;
export type ManagerPayAgreement = ManagerWorkerPayAgreementItem;
export type PayBalance = WorkerPayBalance;
export type PayEntry = WorkerPayEntry;
export type PayWorkspace = WorkerPayWorkspace;
export type ManagerPayWorkspace = ManagerWorkerPayWorkspace;
export type PayOverview = WorkerPayOverview;
export type PayCandidate = WorkerPayCandidate;
export type PayOrderWorkspace = WorkerPayOrderWorkspace;
export type PayAgreementAmount = Omit<WorkerPayAgreementCreate, 'assignment_id' | 'amount' | 'cost_byn_amount'> & { amount: string; cost_byn_amount?: string };
const base = '/api/manager/worker-pay';
const get = <T>(url: string, page = 1) => request<T>(OpenAPI, { method: 'GET', url, query: { page, limit: 30 } });
const post = (url: string, body: unknown) => request<WorkerMoneyCommandResult>(OpenAPI, { method: 'POST', url, headers: { 'X-Kitlane-Team': '1' }, body, mediaType: 'application/json' });
export const workerPayApi = {
  own: (page = 1) => get<PayWorkspace>('/api/installer/pay', page),
  overview: (page = 1) => get<PayOverview>(base, page),
  worker: (id: number, page = 1) => get<ManagerPayWorkspace>(`${base}/${id}`, page),
  order: (id: number) => get<PayOrderWorkspace>(`/api/manager/orders/${id}/worker-pay`),
  agree: (order: number, body: PayAgreementAmount & { assignment_id: number }) => post(`/api/manager/orders/${order}/worker-pay/agreements`, body),
  revise: (worker: number, id: number, body: PayAgreementAmount & { expected_agreement_version: number }) => post(`${base}/${worker}/agreements/${id}/revise`, body),
  agreementAction: (worker: number, id: number, action: 'accrue' | 'cancel', body: MoneyCommand & { expected_agreement_version: number; reason?: string }) => post(`${base}/${worker}/agreements/${id}/${action}`, body),
  payout: (worker: number, body: AmountCommand & { method: 'cash' | 'bank' }) => post(`${base}/${worker}/payouts`, body),
  offset: (worker: number, body: AmountCommand) => post(`${base}/${worker}/offsets`, body),
  reverse: (worker: number, id: number, body: MoneyCommand & { reason: string }) => post(`${base}/${worker}/payouts/${id}/reverse`, body),
};
