import type { OrderWorkspaceSection } from './OrderWorkspaceNav.vue';

export const loadProposalWorkspace = () => import('./OrderProposalWorkspace.vue');
export const loadDocumentsWorkspace = () => import('./OrderDocumentsWorkspace.vue');
export const loadWorkWorkspace = () => import('./OrderWorkWorkspace.vue');
export const loadPaymentsWorkspace = () => import('./OrderPaymentWorkspace.vue');

export const loadOrderWorkspaceSection = (section: OrderWorkspaceSection) => ({
  proposal: loadProposalWorkspace,
  documents: loadDocumentsWorkspace,
  work: loadWorkWorkspace,
  payments: loadPaymentsWorkspace,
}[section]());
