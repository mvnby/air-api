import type { ManagerOrderListItemResponse, ManagerOrderUpdatePayload } from '../../client';
import { EXECUTION_STATUS_LABELS } from './order-utils';

export const needsExecutionWithoutPaymentConfirmation = (
  order: Pick<ManagerOrderListItemResponse, 'balance_due' | 'execution_without_payment'>,
  column: string,
) => {
  const movesToExecution = column === 'execution' || column.startsWith('execution:');
  const executionStatus = column.startsWith('execution:') ? column.slice('execution:'.length) : '';
  return movesToExecution
    && executionStatus !== 'awaiting_payment'
    && Number(order.balance_due || 0) > 0
    && !order.execution_without_payment;
};

export const buildBoardTransitionPayload = (
  order: Pick<ManagerOrderListItemResponse, 'balance_due' | 'execution_without_payment'>,
  column: string,
  executionWithoutPaymentReason?: string | null,
): ManagerOrderUpdatePayload | null => {
  if (column.startsWith('execution:')) {
    const executionStatus = column.slice('execution:'.length);
    if (!EXECUTION_STATUS_LABELS[executionStatus]) return null;
    const payload: ManagerOrderUpdatePayload = {
      status: 'execution',
      execution_status: executionStatus,
      closing_result: null,
      reject_reason: null,
    };
    if (needsExecutionWithoutPaymentConfirmation(order, column) && executionWithoutPaymentReason) {
      payload.execution_without_payment = true;
      payload.execution_without_payment_reason = executionWithoutPaymentReason;
    }
    return payload;
  }
  if (column === 'closed_lost') return null;
  if (column === 'closed_won') {
    return { status: 'closed', closing_result: 'won', reject_reason: null };
  }
  if (column === 'execution') {
    const payload: ManagerOrderUpdatePayload = {
      status: 'execution',
      closing_result: null,
      reject_reason: null,
    };
    if (needsExecutionWithoutPaymentConfirmation(order, column) && executionWithoutPaymentReason) {
      payload.execution_without_payment = true;
      payload.execution_without_payment_reason = executionWithoutPaymentReason;
    }
    return payload;
  }
  if (column === 'negotiation') {
    return {
      status: 'negotiation',
      closing_result: null,
      reject_reason: null,
      execution_without_payment: false,
      execution_without_payment_reason: null,
    };
  }
  return {
    status: 'negotiation',
    negotiation_status: column,
    closing_result: null,
    reject_reason: null,
    execution_without_payment: false,
    execution_without_payment_reason: null,
    measurement_required: column === 'awaiting_visit' ? true : undefined,
  };
};

export const runOptimisticOrderTransition = async <TSnapshot, TResult>({
  snapshot,
  apply,
  persist,
  rollback,
}: {
  snapshot: TSnapshot;
  apply: () => void;
  persist: () => Promise<TResult>;
  rollback: (snapshot: TSnapshot) => void;
}) => {
  apply();
  try {
    return await persist();
  } catch (error) {
    rollback(snapshot);
    throw error;
  }
};
