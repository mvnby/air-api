import { currentManagerHistoryTarget, goToManagerHistoryTarget, navigateManager } from './manager-navigation-history';
import type { ManagerOrderDetailResponse } from '../client';
import type { OrderWorkspaceSection } from '../components/orders/OrderWorkspaceNav.vue';

const BOARD_PATHS = ['/manager/orders', '/manager/orders/kanban', '/manager/orders/list'];
const positiveId = (value: string | null) => value && /^[1-9]\d*$/.test(value) && Number.isSafeInteger(Number(value)) ? Number(value) : null;

export const orderReturnUrl = (value?: string | null): string => {
  const fallback = '/manager/orders/kanban';
  let url: URL;
  try { url = new URL(value || fallback, window.location.origin); } catch { return fallback; }
  if (url.origin !== window.location.origin || ![...BOARD_PATHS, '/manager/calendar'].includes(url.pathname)) return fallback;
  url.searchParams.delete('orderId');
  url.searchParams.delete('proposalId');
  url.searchParams.delete('section');
  url.searchParams.delete('returnTo');
  return `${url.pathname}${url.search}`;
};

export const readOrderWorkspaceSection = (location: string): OrderWorkspaceSection => {
  const values = new URL(location, window.location.origin).searchParams.getAll('section');
  const section = values.length === 1 ? values[0] : null;
  return section === 'documents' || section === 'work' || section === 'payments' ? section : 'proposal';
};

export const orderPageUrl = (orderId: number, returnTo?: string, proposalId?: string | null, section?: OrderWorkspaceSection) => {
  const params = new URLSearchParams();
  if (returnTo) {
    const returnUrl = orderReturnUrl(returnTo);
    params.set('returnTo', returnUrl);
    // Bootstrap still needs explicit company/site context before opening an old link.
    const context = new URL(returnUrl, window.location.origin).searchParams;
    for (const key of ['company', 'site']) context.getAll(key).forEach(value => params.append(key, value));
  }
  if (proposalId != null) params.set('proposalId', proposalId);
  if (section) params.set('section', section);
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
  if (orderId) {
    const canonical = new URL(orderPageUrl(
      orderId,
      orderReturnUrl(url.searchParams.get('returnTo') || url.href),
      url.searchParams.get('proposalId'),
      url.searchParams.has('section') ? readOrderWorkspaceSection(url.href) : undefined,
    ), window.location.origin);
    for (const key of ['company', 'site']) {
      if (!url.searchParams.has(key)) continue;
      canonical.searchParams.delete(key);
      url.searchParams.getAll(key).forEach(value => canonical.searchParams.append(key, value));
    }
    window.history.replaceState(window.history.state, '', `${canonical.pathname}${canonical.search}`);
  }
  return `${window.location.pathname}${window.location.search}`;
};

export type OrderBoardState = {
  expandedOrderId: number | null;
  expandedGroupIds: string[];
  columnFilters: Record<string, string>;
  scrollLeft: number;
  columnScrollTops?: Record<string, number>;
  loadedPages?: Record<string, number>;
  mobileColumn?: string;
  mobileScrollTops?: Record<string, number>;
};
export type OrderListPosition = { url: string; top: number; board?: OrderBoardState };
export const savedOrderListPosition = (): OrderListPosition | undefined => window.history.state?.orderListPosition;

// Native anchor navigation keeps browser actions available; only a plain click uses the guarded app transition.
export const handleOrderLinkClick = (event: MouseEvent, open: () => void) => {
  event.stopPropagation();
  if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  open();
};

export const orderLinkUrl = (orderId: number) => orderPageUrl(orderId, orderReturnUrl(window.location.href));

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
