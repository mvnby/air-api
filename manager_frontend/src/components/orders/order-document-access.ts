export type OrderDocumentAccess = {
  mode: 'active' | 'history';
  canCreate: boolean;
  canUpload: boolean;
  canReplace: boolean;
  canDelete: boolean;
  canSend: boolean;
  summary: string;
};

const ACTIVE_DOCUMENT_ACCESS: OrderDocumentAccess = {
  mode: 'active',
  canCreate: true,
  canUpload: true,
  canReplace: true,
  canDelete: true,
  canSend: true,
  summary: 'Создавайте, обновляйте и отправляйте актуальные документы.',
};

const CLOSED_DOCUMENT_ACCESS: OrderDocumentAccess = {
  mode: 'history',
  canCreate: false,
  canUpload: false,
  canReplace: false,
  canDelete: false,
  canSend: true,
  summary: 'Заказ завершён: документы и история отправки доступны только для просмотра и повторной отправки.',
};

export const getOrderDocumentAccess = (orderStatus?: string | null): OrderDocumentAccess => (
  orderStatus === 'closed' ? CLOSED_DOCUMENT_ACCESS : ACTIVE_DOCUMENT_ACCESS
);
