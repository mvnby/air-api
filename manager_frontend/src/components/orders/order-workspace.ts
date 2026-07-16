import type { ManagerOrderDocumentItem } from '../../client';
import { EXECUTION_STATUS_LABELS, NEGOTIATION_STATUS_LABELS, formatRelativeAge } from './order-utils';

export type OrderWorkflowType = 'sales_installation' | 'service_work' | 'maintenance' | 'repair';
export type OrderWorkspaceTarget = 'object' | 'planning' | 'proposal' | 'documents' | 'payments' | 'equipment';
export type OrderWorkspaceTone = 'slate' | 'sky' | 'amber' | 'teal' | 'emerald' | 'rose';

export type OrderWorkflowOption = {
  value: OrderWorkflowType;
  label: string;
  hint: string;
};

export const ORDER_WORKFLOW_OPTIONS: OrderWorkflowOption[] = [
  { value: 'sales_installation', label: 'Продажа + монтаж', hint: 'Товар и работы' },
  { value: 'service_work', label: 'Работы', hint: 'Монтаж, демонтаж, трассы' },
  { value: 'maintenance', label: 'Обслуживание', hint: 'ТО и сервис' },
  { value: 'repair', label: 'Ремонт', hint: 'Диагностика и ремонт' },
];

export const normalizeOrderWorkflowType = (value: unknown): OrderWorkflowType => {
  const raw = String(value || '').trim();
  if (raw === 'service_work' || raw === 'maintenance' || raw === 'repair') return raw;
  return 'sales_installation';
};

export type OrderWorkspaceLane = {
  id: 'product' | 'work' | 'documents' | 'payment';
  label: string;
  status: string;
  detail: string;
  actionLabel: string;
  tone: OrderWorkspaceTone;
  target: OrderWorkspaceTarget;
};

export type OrderWorkspaceViewModel = {
  stageLabel: string;
  stageAge: string;
  stageTone: OrderWorkspaceTone;
  nextAction: {
    label: string;
    target: OrderWorkspaceTarget;
    tone: OrderWorkspaceTone;
  };
  blockers: string[];
  lanes: OrderWorkspaceLane[];
};

export type OrderWorkspaceInput = {
  status: string;
  negotiationStatus?: string | null;
  executionStatus?: string | null;
  statusChangedAt?: string | null;
  negotiationStatusChangedAt?: string | null;
  executionStatusChangedAt?: string | null;
  installationDate?: string | null;
  productCount: number;
  serviceCount: number;
  linkedEquipmentCount: number;
  documents: ManagerOrderDocumentItem[];
  documentEmailStatus?: 'unknown' | 'none' | 'pending' | 'sent' | 'failed';
  missingReferencedInvoice?: string | null;
  total: number;
  paid: number;
  balance: number;
};

const plural = (count: number, one: string, few: string, many: string) => {
  const mod100 = count % 100;
  const mod10 = count % 10;
  if (mod100 >= 11 && mod100 <= 14) return many;
  if (mod10 === 1) return one;
  if (mod10 >= 2 && mod10 <= 4) return few;
  return many;
};

const documentTypesLabel = (documents: ManagerOrderDocumentItem[]) => {
  const labels = documents.slice(0, 3).map((item) => {
    if (item.doc_type === 'contract') return 'Договор';
    if (item.doc_type === 'invoice') return 'Счёт';
    if (item.doc_type === 'act') return 'Акт';
    if (item.doc_type === 'tn2') return 'ТН-2';
    return item.number || item.doc_type || 'документ';
  });
  return labels.join(', ');
};

const documentDeliveryLabel = (status: OrderWorkspaceInput['documentEmailStatus']) => ({
  sent: 'отправлены',
  pending: 'отправляются',
  failed: 'ошибка отправки',
  unknown: 'история отправки недоступна',
  none: 'нужно проверить и отправить',
}[status || 'none']);

export const buildOrderWorkspaceViewModel = (input: OrderWorkspaceInput): OrderWorkspaceViewModel => {
  const inExecution = input.status === 'execution';
  const isClosed = input.status === 'closed';
  const substatus = inExecution
    ? (input.executionStatus || 'needs_schedule')
    : (input.negotiationStatus || 'awaiting_offer');
  const changedAt = inExecution
    ? (input.executionStatusChangedAt || input.statusChangedAt)
    : (input.negotiationStatusChangedAt || input.statusChangedAt);
  const isDocumentStage = inExecution && (substatus === 'work_done' || substatus === 'awaiting_documents');
  let stageLabel = NEGOTIATION_STATUS_LABELS[substatus] || 'Переговоры';
  if (inExecution) stageLabel = EXECUTION_STATUS_LABELS[substatus] || 'Работы';
  if (inExecution && substatus === 'awaiting_payment') stageLabel = 'Ожидание оплаты';
  if (isDocumentStage) stageLabel = 'Оформление документов';
  if (isClosed) stageLabel = 'Заказ завершён';

  const blockers: string[] = [];
  if (!input.productCount && !input.serviceCount) blockers.push('Смета не заполнена');
  if (input.balance > 0) blockers.push(`Остаток ${Math.round(input.balance).toLocaleString('ru-RU')} BYN`);
  if (inExecution && substatus === 'work_done' && !input.documents.length) blockers.push('Нет закрывающих документов');
  if (input.missingReferencedInvoice) blockers.push(`Не найден счёт ${input.missingReferencedInvoice} из назначения платежа`);

  let nextAction: OrderWorkspaceViewModel['nextAction'];
  if (isClosed) nextAction = { label: 'Проверить историю', target: 'documents', tone: 'slate' };
  else if (!input.productCount && !input.serviceCount) nextAction = { label: 'Заполнить смету', target: 'proposal', tone: 'sky' };
  else if (!inExecution && substatus === 'awaiting_visit') nextAction = { label: 'Назначить выезд', target: 'planning', tone: 'sky' };
  else if (!inExecution && substatus === 'awaiting_payment') nextAction = { label: `Ожидать оплату ${Math.round(input.balance).toLocaleString('ru-RU')} BYN`, target: 'payments', tone: 'emerald' };
  else if (!inExecution && substatus === 'proposal_sent') nextAction = { label: 'Проверить предложение', target: 'proposal', tone: 'amber' };
  else if (!inExecution) nextAction = { label: 'Подготовить предложение', target: 'proposal', tone: 'sky' };
  else if (substatus === 'order_equipment' || substatus === 'awaiting_equipment') nextAction = { label: 'Проверить товар', target: 'proposal', tone: 'amber' };
  else if (substatus === 'needs_schedule' || substatus === 'scheduled') nextAction = { label: 'Открыть планирование', target: 'planning', tone: 'teal' };
  else if (substatus === 'work_done' || substatus === 'awaiting_documents') {
    if (input.missingReferencedInvoice) nextAction = { label: `Проверить счёт ${input.missingReferencedInvoice}`, target: 'documents', tone: 'amber' };
    else if (!input.documents.length) nextAction = { label: 'Создать комплект документов', target: 'documents', tone: 'teal' };
    else if (input.documentEmailStatus === 'unknown') nextAction = { label: 'Проверить комплект документов', target: 'documents', tone: 'amber' };
    else if (input.documentEmailStatus === 'failed') nextAction = { label: 'Повторить отправку документов', target: 'documents', tone: 'rose' };
    else if (input.documentEmailStatus === 'pending') nextAction = { label: 'Проверить отправку документов', target: 'documents', tone: 'amber' };
    else if (input.documentEmailStatus !== 'sent') nextAction = { label: 'Отправить документы', target: 'documents', tone: 'teal' };
    else if (input.balance > 0) nextAction = { label: `Ожидать оплату ${Math.round(input.balance).toLocaleString('ru-RU')} BYN`, target: 'payments', tone: 'emerald' };
    else nextAction = { label: 'Проверить завершение заказа', target: 'payments', tone: 'emerald' };
  } else if (input.balance > 0) nextAction = { label: `Ожидать оплату ${Math.round(input.balance).toLocaleString('ru-RU')} BYN`, target: 'payments', tone: 'emerald' };
  else nextAction = { label: 'Проверить завершение заказа', target: 'payments', tone: 'emerald' };

  const productStatus = !input.productCount
    ? 'Товар не выбран'
    : (substatus === 'order_equipment' ? 'Нужно заказать' : substatus === 'awaiting_equipment' ? 'Ждём оборудование' : `${input.productCount} ${plural(input.productCount, 'товар', 'товара', 'товаров')}`);
  const workStatus = substatus === 'work_done' || substatus === 'awaiting_documents' || substatus === 'awaiting_payment'
    ? 'Выполнен'
    : input.installationDate
      ? 'Назначен'
      : 'Не назначен';
  const paymentStatus = input.balance <= 0 && input.total > 0
    ? 'Оплачено полностью'
    : `Оплачено ${Math.round(input.paid).toLocaleString('ru-RU')} из ${Math.round(input.total).toLocaleString('ru-RU')} BYN`;

  return {
    stageLabel,
    stageAge: formatRelativeAge(changedAt),
    stageTone: isClosed ? 'emerald' : inExecution ? 'teal' : 'sky',
    nextAction,
    blockers,
    lanes: [
      {
        id: 'product',
        label: 'Товар',
        status: productStatus,
        detail: input.linkedEquipmentCount ? `Оборудование на объекте: ${input.linkedEquipmentCount}` : 'Оборудование объекта ещё не создано',
        actionLabel: !input.productCount ? 'Добавить товар' : input.linkedEquipmentCount ? 'Открыть товар и оборудование' : 'Создать оборудование',
        tone: !input.productCount ? 'rose' : (substatus === 'order_equipment' || substatus === 'awaiting_equipment') ? 'amber' : 'teal',
        target: 'equipment',
      },
      {
        id: 'work',
        label: 'Монтаж',
        status: workStatus,
        detail: input.serviceCount ? `${input.serviceCount} ${plural(input.serviceCount, 'услуга', 'услуги', 'услуг')} в смете` : 'Услуги не добавлены',
        actionLabel: workStatus === 'Выполнен' ? 'Открыть результат' : 'Открыть планирование',
        tone: workStatus === 'Выполнен' ? 'emerald' : input.installationDate ? 'teal' : 'amber',
        target: 'planning',
      },
      {
        id: 'documents',
        label: 'Документы',
        status: input.documents.length ? `${input.documents.length} ${plural(input.documents.length, 'документ', 'документа', 'документов')}` : 'Не созданы',
        detail: input.missingReferencedInvoice
          ? `Счёт ${input.missingReferencedInvoice} из платежа не найден`
          : input.documents.length
            ? `${documentTypesLabel(input.documents)} · ${documentDeliveryLabel(input.documentEmailStatus)}`
            : 'Создайте документы из актуальной сметы',
        actionLabel: input.missingReferencedInvoice
          ? 'Проверить счёт'
          : input.documents.length ? 'Открыть комплект' : 'Создать документы',
        tone: input.missingReferencedInvoice || input.documentEmailStatus === 'failed' ? 'rose' : input.documentEmailStatus === 'unknown' || !input.documents.length ? 'amber' : 'teal',
        target: 'documents',
      },
      {
        id: 'payment',
        label: 'Оплата',
        status: paymentStatus,
        detail: input.balance > 0 ? `Долг ${Math.round(input.balance).toLocaleString('ru-RU')} BYN` : 'Долга нет',
        actionLabel: input.balance > 0 ? 'Внести оплату' : 'Открыть оплаты',
        tone: input.balance > 0 ? 'rose' : 'emerald',
        target: 'payments',
      },
    ],
  };
};
