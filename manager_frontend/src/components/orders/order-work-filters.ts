import type { ManagerOrderListItemResponse } from '../../client';
import { getOrderExecutionStatus, isOverdue } from './order-utils';

export const ORDER_WORK_FILTERS = [
  { value: 'all', label: 'Все заказы' },
  { value: 'followup', label: 'Пора связаться' },
  { value: 'planning', label: 'К работам' },
  { value: 'unpaid', label: 'Есть остаток оплаты' },
] as const;

export type OrderWorkFilter = typeof ORDER_WORK_FILTERS[number]['value'];

export function matchesOrderWorkFilter(order: ManagerOrderListItemResponse, filter: OrderWorkFilter): boolean {
  if (filter === 'followup') return order.status !== 'closed' && isOverdue(order);
  if (filter === 'planning') {
    return (order.status === 'negotiation' && order.ready_for_execution)
      || (order.status === 'execution' && getOrderExecutionStatus(order) === 'needs_schedule');
  }
  // An unpaid balance is not evidence that a payment is overdue.
  if (filter === 'unpaid') return Number(order.balance_due || 0) > 0;
  return true;
}
