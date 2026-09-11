export type CatalogDecisionOrderContext = {
  orderId: number;
  proposalId: number;
  returnTo: string;
};

const positiveId = (value: string | null): number | null => {
  if (!value || !/^[1-9]\d*$/.test(value)) return null;
  const id = Number(value);
  return Number.isSafeInteger(id) ? id : null;
};

export const orderWorkspaceUrl = (orderId: number, proposalId: number, returnTo?: string | null): string => {
  const fallback = '/manager/orders/kanban';
  const url = new URL(returnTo || fallback, 'https://manager.local');
  const allowed = url.origin === 'https://manager.local'
    && ['/manager/orders', '/manager/orders/kanban', '/manager/orders/list'].includes(url.pathname);
  const target = allowed ? url : new URL(fallback, 'https://manager.local');
  target.searchParams.set('orderId', String(orderId));
  target.searchParams.set('proposalId', String(proposalId));
  return `${target.pathname}${target.search}`;
};

export const readCatalogDecisionContext = (search: string): CatalogDecisionOrderContext | null => {
  const params = new URLSearchParams(search);
  if (!params.has('orderId') && !params.has('proposalId')) return null;
  const orderId = positiveId(params.get('orderId'));
  const proposalId = positiveId(params.get('proposalId'));
  if (!orderId || !proposalId) throw new Error('В ссылке подбора не указан корректный заказ и вариант предложения. Откройте подбор из заказа ещё раз.');
  return { orderId, proposalId, returnTo: orderWorkspaceUrl(orderId, proposalId, params.get('returnTo')) };
};

export const catalogDecisionUrl = (orderId: number, proposalId: number, returnTo: string): string => {
  const params = new URLSearchParams({ orderId: String(orderId), proposalId: String(proposalId), returnTo: orderWorkspaceUrl(orderId, proposalId, returnTo) });
  return `/manager/catalog-decision?${params}`;
};

export const navigateManager = (href: string) => {
  window.history.pushState({}, '', href);
  window.dispatchEvent(new PopStateEvent('popstate'));
};
