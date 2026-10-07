import {
  ManagerIncomingService,
  type IncomingCreatePayload as GeneratedIncomingCreatePayload,
  type IncomingResponse,
  type IncomingUpdatePayload,
} from '../client';

export type { IncomingResponse, IncomingUpdatePayload };
export type IncomingCreatePayload = GeneratedIncomingCreatePayload & {
  source_timezone: string;
};

export const newIncomingIdempotencyKey = (): string => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `incoming-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

export const incomingApi = {
  clarify: (leadId: number, expectedVersion: number, idempotencyKey: string): Promise<IncomingResponse> => Promise.resolve(
    ManagerIncomingService.createManagerIncomingClarification(leadId, idempotencyKey, { expected_version: expectedVersion }),
  ),
  create: (payload: IncomingCreatePayload, idempotencyKey: string): Promise<IncomingResponse> => Promise.resolve(
    ManagerIncomingService.createManagerIncoming(idempotencyKey, payload),
  ),
  get: (leadId: number): Promise<IncomingResponse> => Promise.resolve(
    ManagerIncomingService.getManagerIncoming(leadId),
  ),
  update: (
    leadId: number,
    payload: IncomingUpdatePayload,
    idempotencyKey: string,
  ): Promise<IncomingResponse> => Promise.resolve(
    ManagerIncomingService.updateManagerIncoming(leadId, idempotencyKey, payload),
  ),
};
