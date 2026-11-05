import { getApiErrorCode } from '../../../utils/api-errors';

export type PreviousContractAct = { id: number; orderId: number; number: string; url: string | null; minimum: number };
export type ContractActConfirmation = { previousActId: number; previousNumber: number };
export const MAX_PREVIOUS_ACT_NUMBER = 999999999;

export function previousContractAct(error: unknown): PreviousContractAct | null {
  if (getApiErrorCode(error) !== 'contract_act_number_confirmation_required') return null;
  const response = error as { status?: number; body?: { detail?: { minimum_previous_number?: number; previous_act?: Record<string, unknown> } } };
  const act = response.body?.detail?.previous_act;
  if (response.status !== 409 || !act || typeof act.id !== 'number' || !Number.isInteger(act.id) || act.id <= 0
    || typeof act.order_id !== 'number' || !Number.isInteger(act.order_id) || act.order_id <= 0 || typeof act.number !== 'string') return null;
  const url = typeof act.url === 'string' && /^https:\/\/drive\.google\.com\/open\?id=[a-zA-Z0-9_-]+$/.test(act.url) ? act.url : null;
  const minimum = response.body?.detail?.minimum_previous_number;
  return { id: act.id, orderId: act.order_id, number: act.number, url,
    minimum: typeof minimum === 'number' && Number.isSafeInteger(minimum) && minimum > 0 ? minimum : 0 };
}
