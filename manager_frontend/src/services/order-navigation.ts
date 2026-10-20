import { currentManagerHistoryTarget, goToManagerHistoryTarget, navigateManager } from './manager-navigation-history';
import type { ManagerOrderDetailResponse } from '../client';

const BOARD_PATHS = ['/manager/orders', '/manager/orders/kanban', '/manager/orders/list'];
const positiveId = (value: string | null) => value && /^[1-9]\d*$/.test(value) && Number.isSafeInteger(Number(value)) ? Number(value) : null;

export const orderReturnUrl = (value?: string | null): string => {
  const fallback = '/manager/orders/kanban';
  let url: URL;
  try { url = new URL(value || fallback, window.location.origin); } catch { return fallback; }
  if (url.origin !== window.location.origin || ![...BOARD_PATHS, '/manager/calendar'].includes(url.pathname)) return fallback;
  url.searchParams.delete('orderId');
  url.searchParams.delete('proposalId');
  url.searchParams.delete('returnTo');
  return `${url.pathname}${url.search}`;
};

export const orderPageUrl = (orderId: number, returnTo?: string, proposalId?: string | null) => {
  const params = new URLSearchParams();
  if (returnTo) {
    const returnUrl = orderReturnUrl(returnTo);
    params.set('returnTo', returnUrl);
    // Bootstrap still needs explicit company/site context before opening an old link.
    const context = new URL(returnUrl, window.location.origin).searchParams;
    for (const key of ['company', 'site']) context.getAll(key).forEach(value => params.append(key, value));
  }
  if (proposalId != null) params.set('proposalId', proposalId);
  return `/manager/orders/${orderId}${params.size ? `?${params}` : ''}`;
};

export const readOrderPage = (location: string) => {
  const url = new URL(location, window.location.origin);
  const match = url.pathname.match(/^\/manager\/orders\/([1-9]\d*)\/?$/);
  const orderId = match ? positiveId(match[1]!) : null;
  return orderId ? { orderId, returnTo: orderReturnUrl(url.searchParams.get('returnTo')) } : null;
};

export const readOrderProposalContext = (location: string) => {
  const url = new URL(location, window.location.origin);
  const orderId = readOrderPage(location)?.orderId
    ?? (BOARD_PATHS.includes(url.pathname) ? positiveId(url.searchParams.get('orderId')) : null);
  return { orderId, requested: url.searchParams.has('proposalId'), proposalId: url.searchParams.getAll('proposalId').length === 1 ? positiveId(url.searchParams.get('proposalId')) : null };
};

export const orderProposalLinkError = (order: ManagerOrderDetailResponse, location: string) => {
  const context = readOrderProposalContext(location);
  if (context.orderId !== order.id || !context.requested) return '';
  const proposal = order.proposals?.find(item => item.id === context.proposalId);
  if (!proposal) return 'Вариант предложения по этой ссылке недоступен. Откройте актуальное предложение заказа.';
  return proposal.is_archived ? 'Вариант предложения по этой ссылке в архиве. Откройте актуальное предложение заказа.' : '';
};

// Old links from mail, tasks, customers and the catalog remain direct order links.
export const normalizeOrderLocation = () => {
  const url = new URL(window.location.href);
  const orderId = BOARD_PATHS.includes(url.pathname) ? positiveId(url.searchParams.get('orderId')) : null;
  if (orderId) window.history.replaceState(window.history.state, '', orderPageUrl(orderId, orderReturnUrl(url.href), url.searchParams.get('proposalId')));
  return `${window.location.pathname}${window.location.search}`;
};

export type OrderBoardState = {
  expandedOrderId: number | null;
  expandedGroupIds: string[];
  columnFilters: Record<string, string>;
  scrollLeft: number;
};
export type OrderListPosition = { url: string; top: number; board?: OrderBoardState };
export const savedOrderListPosition = (): OrderListPosition | undefined => window.history.state?.orderListPosition;

export const openOrderPage = (orderId: number, board?: OrderBoardState) => {
  const returnTo = orderReturnUrl(`${window.location.pathname}${window.location.search}`);
  window.history.replaceState({ ...window.history.state, orderListPosition: { url: returnTo, top: window.scrollY, board } }, '', returnTo);
  return navigateManager(orderPageUrl(orderId, returnTo), { orderReturn: returnTo, orderOrigin: currentManagerHistoryTarget() });
};

export const returnFromOrder = (returnTo: string) => {
  const target = orderReturnUrl(returnTo);
  const origin = window.history.state?.orderOrigin;
  if (origin?.href === target && goToManagerHistoryTarget(origin, target)) return;
  return navigateManager(target, {}, true);
};
