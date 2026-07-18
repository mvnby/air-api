export type ProposalLifecycleStatus = 'draft' | 'ready_to_send' | 'sent' | 'approved' | 'rejected';

export const PROPOSAL_STATUS_META: Record<ProposalLifecycleStatus, {
  label: string;
  tone: 'slate' | 'sky' | 'amber' | 'emerald' | 'rose';
}> = {
  draft: { label: 'Черновик', tone: 'slate' },
  ready_to_send: { label: 'Готово к отправке', tone: 'sky' },
  sent: { label: 'Отправлено', tone: 'amber' },
  approved: { label: 'Принято клиентом', tone: 'emerald' },
  rejected: { label: 'Отклонено клиентом', tone: 'rose' },
};

export const normalizeProposalStatus = (value: unknown): ProposalLifecycleStatus => {
  const status = String(value || 'draft').trim().toLowerCase();
  if (status === 'accepted') return 'approved';
  if (status === 'ready_to_send' || status === 'sent' || status === 'approved' || status === 'rejected') return status;
  return 'draft';
};

export const proposalStatusLabel = (value: unknown) => PROPOSAL_STATUS_META[normalizeProposalStatus(value)].label;

export const isProposalRevisionLocked = (value: unknown) => {
  const status = normalizeProposalStatus(value);
  return status === 'sent' || status === 'approved';
};

export type ProposalPrimaryAction = 'finish' | 'send' | 'record_response' | 'create_variant' | null;

export const proposalPrimaryAction = (value: unknown): ProposalPrimaryAction => {
  const status = normalizeProposalStatus(value);
  if (status === 'draft') return 'finish';
  if (status === 'ready_to_send') return 'send';
  if (status === 'sent') return 'record_response';
  if (status === 'rejected') return 'create_variant';
  return null;
};

export const proposalPrimaryActionLabel = (value: unknown) => {
  const action = proposalPrimaryAction(value);
  if (!action) return '';
  return {
    finish: 'Завершить подготовку',
    send: 'Отправить предложение',
    record_response: 'Зафиксировать ответ',
    create_variant: 'Подготовить новый вариант',
  }[action];
};
