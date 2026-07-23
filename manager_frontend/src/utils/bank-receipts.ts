import type { BankReceiptResponse } from '../client';

export type BankReceiptGroupOrder = {
  order_id?: number;
  title?: string | null;
  customer_name?: string | null;
  status?: string | null;
  total_amount?: number;
  total_payments?: number;
  balance_due?: number;
};

export type BankReceiptGroupMatch = {
  available?: boolean;
  is_exact?: boolean;
  selection_mode?: string | null;
  total_balance_due?: number;
  open_balance_due?: number;
  receipt_amount?: number;
  order_ids?: number[];
  orders?: BankReceiptGroupOrder[];
  open_order_ids?: number[];
  open_orders?: BankReceiptGroupOrder[];
};

export const BANK_RECEIPT_STATUS_OPTIONS = [
  { value: '', label: 'Все' },
  { value: 'requires_review', label: 'Требуют проверки' },
  { value: 'partially_allocated', label: 'С остатком' },
  { value: 'matched', label: 'Разнесены' },
  { value: 'closed_orders', label: 'Закрытые заказы' },
  { value: 'non_order_income', label: 'Не CRM' },
  { value: 'void', label: 'Ошибочные' },
  { value: 'parse_failed', label: 'Ошибки парсинга' },
];

export const bankReceiptStatusLabel = (value?: string | null) => {
  switch (value) {
    case 'matched': return 'Разнесен';
    case 'partially_allocated': return 'Разнесен частично';
    case 'requires_review': return 'Проверить';
    case 'closed_orders': return 'Закрытые заказы';
    case 'non_order_income': return 'Не CRM';
    case 'void': return 'Ошибочный';
    case 'parse_failed': return 'Не распознан';
    default: return value || 'Новый';
  }
};

export const bankReceiptStatusClass = (value?: string | null) => {
  switch (value) {
    case 'matched':
      return 'bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20';
    case 'partially_allocated':
      return 'bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-500/10 dark:text-amber-200 dark:border-amber-500/20';
    case 'requires_review':
      return 'bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-500/20';
    case 'closed_orders':
      return 'bg-sky-100 text-sky-700 border-sky-200 dark:bg-sky-500/10 dark:text-sky-300 dark:border-sky-500/20';
    case 'non_order_income':
      return 'bg-violet-100 text-violet-700 border-violet-200 dark:bg-violet-500/10 dark:text-violet-300 dark:border-violet-500/20';
    case 'void':
      return 'bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-700/50 dark:text-slate-300 dark:border-slate-600';
    case 'parse_failed':
      return 'bg-red-100 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20';
    default:
      return 'bg-gray-100 text-gray-700 border-gray-200 dark:bg-slate-700 dark:text-slate-300 dark:border-slate-600';
  }
};

export const bankReceiptCandidateOrders = (receipt: BankReceiptResponse) => {
  const ids = receipt.match_meta?.candidate_order_ids;
  return Array.isArray(ids) ? ids.filter(Boolean) : [];
};

export const bankReceiptGroupMatch = (
  receipt: BankReceiptResponse,
): BankReceiptGroupMatch | null => {
  const raw = receipt.match_meta?.group_match;
  return raw && typeof raw === 'object' ? raw as BankReceiptGroupMatch : null;
};

export const bankReceiptGroupOrders = (receipt: BankReceiptResponse) => {
  const items = bankReceiptGroupMatch(receipt)?.orders;
  return Array.isArray(items) ? items.filter((item) => item?.order_id) : [];
};

export const bankReceiptGroupOrderIds = (receipt: BankReceiptResponse) => {
  const ids = bankReceiptGroupMatch(receipt)?.order_ids;
  if (Array.isArray(ids) && ids.length) return ids.map(Number).filter(Boolean);
  return bankReceiptGroupOrders(receipt).map((item) => Number(item.order_id)).filter(Boolean);
};

export const bankReceiptGroupMatchLabel = (receipt: BankReceiptResponse) => {
  const match = bankReceiptGroupMatch(receipt);
  if (!match) return '';
  if (match.selection_mode === 'exact_subset') return 'Подобрана часть открытых актов';
  if (match.is_exact) return 'Открытая задолженность совпадает';
  return 'Открытая задолженность по УНП';
};

export const canAttachBankReceiptGroup = (receipt: BankReceiptResponse) => {
  const match = bankReceiptGroupMatch(receipt);
  return Boolean(
    match?.available
    && match.is_exact
    && bankReceiptGroupOrderIds(receipt).length > 1
    && receipt.status !== 'matched'
    && !receipt.matched_payment_id
  );
};

export const canManageBankReceiptAllocations = (receipt: BankReceiptResponse) => (
  Boolean(receipt.payer_unp)
  && Number(receipt.amount || 0) > 0
  && !['void', 'closed_orders', 'non_order_income', 'parse_failed'].includes(receipt.status)
);
