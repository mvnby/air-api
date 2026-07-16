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
  total: number;
  paid: number;
  balance: number;
};

const documentLabel = (documents: ManagerOrderDocumentItem[]) => {
  if (!documents.length) return 'Не созданы';
  const labels = documents.slice(0, 3).map((item) => {
    if (item.doc_type === 'contract') return 'договор';
    if (item.doc_type === 'invoice') return 'счёт';
    if (item.doc_type === 'act') return 'акт';
    if (item.doc_type === 'tn2') return 'ТН-2';
    return item.number || item.doc_type || 'документ';
  });
  return `${documents.length} док. · ${labels.join(', ')}`;
};

export const buildOrderWorkspaceViewModel = (input: OrderWorkspaceInput): OrderWorkspaceViewModel => {
  const inExecution = input.status === 'execution';
  const isClosed = input.status === 'closed';
  const substatus = inExecution
    ? (input.executionStatus || 'needs_schedule')
    : (input.negotiationStatus || 'awaiting_offer');
  const changedAt = inExecution
    ? (input.executionStatusChangedAt || input.statusChangedAt)
    : (input.negotiationStatusChangedAt || input.statusChangedAt);
  const stageLabel = isClosed
    ? 'Заказ завершён'
    : inExecution
      ? (EXECUTION_STATUS_LABELS[substatus] || 'Работы')
      : (NEGOTIATION_STATUS_LABELS[substatus] || 'Переговоры');

  const blockers: string[] = [];
  if (!input.productCount && !input.serviceCount) blockers.push('Смета не заполнена');
  if (input.balance > 0) blockers.push(`Остаток ${Math.round(input.balance).toLocaleString('ru-RU')} BYN`);
  if (inExecution && substatus === 'work_done' && !input.documents.length) blockers.push('Нет закрывающих документов');

  let nextAction: OrderWorkspaceViewModel['nextAction'];
  if (isClosed) nextAction = { label: 'Проверить историю', target: 'documents', tone: 'slate' };
  else if (!input.productCount && !input.serviceCount) nextAction = { label: 'Заполнить смету', target: 'proposal', tone: 'sky' };
  else if (!inExecution && substatus === 'awaiting_visit') nextAction = { label: 'Назначить выезд', target: 'planning', tone: 'sky' };
  else if (!inExecution && substatus === 'awaiting_payment') nextAction = { label: 'Открыть оплаты', target: 'payments', tone: 'emerald' };
  else if (!inExecution && substatus === 'proposal_sent') nextAction = { label: 'Проверить предложение', target: 'proposal', tone: 'amber' };
  else if (!inExecution) nextAction = { label: 'Подготовить предложение', target: 'proposal', tone: 'sky' };
  else if (substatus === 'order_equipment' || substatus === 'awaiting_equipment') nextAction = { label: 'Проверить товар', target: 'proposal', tone: 'amber' };
  else if (substatus === 'needs_schedule' || substatus === 'scheduled') nextAction = { label: 'Открыть планирование', target: 'planning', tone: 'teal' };
  else if (substatus === 'work_done' || substatus === 'awaiting_documents') nextAction = { label: 'Закрыть документы', target: 'documents', tone: 'teal' };
  else nextAction = { label: 'Открыть оплаты', target: 'payments', tone: 'emerald' };

  const productStatus = !input.productCount
    ? 'Товар не выбран'
    : (substatus === 'order_equipment' ? 'Нужно заказать' : substatus === 'awaiting_equipment' ? 'Ждём оборудование' : `${input.productCount} поз.`);
  const workStatus = substatus === 'work_done' || substatus === 'awaiting_documents' || substatus === 'awaiting_payment'
    ? 'Работы выполнены'
    : input.installationDate
      ? 'Работы назначены'
      : 'Работы не назначены';
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
        tone: !input.productCount ? 'rose' : (substatus === 'order_equipment' || substatus === 'awaiting_equipment') ? 'amber' : 'teal',
        target: 'proposal',
      },
      {
        id: 'work',
        label: 'Работы',
        status: workStatus,
        detail: input.serviceCount ? `${input.serviceCount} услуг в смете` : 'Услуги не добавлены',
        tone: workStatus === 'Работы выполнены' ? 'emerald' : input.installationDate ? 'teal' : 'amber',
        target: 'planning',
      },
      {
        id: 'documents',
        label: 'Документы',
        status: documentLabel(input.documents),
        detail: input.documents.length ? 'Откройте комплект для проверки и отправки' : 'Создайте документы из актуальной сметы',
        tone: input.documents.length ? 'teal' : 'amber',
        target: 'documents',
      },
      {
        id: 'payment',
        label: 'Оплата',
        status: paymentStatus,
        detail: input.balance > 0 ? `Долг ${Math.round(input.balance).toLocaleString('ru-RU')} BYN` : 'Долга нет',
        tone: input.balance > 0 ? 'rose' : 'emerald',
        target: 'payments',
      },
    ],
  };
};
