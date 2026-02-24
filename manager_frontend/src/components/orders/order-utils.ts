import type { ManagerOrderListItemResponse } from '../../client';

export const STATUS_ORDER = [
    'new_lead',
    'negotiation',
    'execution',
    'closed',
] as const;

export const STATUS_LABELS: Record<string, string> = {
    new_lead: 'Новый лид',
    negotiation: 'Переговоры',
    execution: 'Монтаж',
    closed: 'Закрыто',
};

export function formatMoney(value: number): string {
    return `${Math.round(value).toLocaleString('ru-RU')} BYN`;
}

export function formatDate(value?: string | null): string {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '—';
    return date.toLocaleDateString('ru-RU');
}

export function formatPhone(phone?: string | null): string {
    if (!phone) return '—';
    const digits = phone.replace(/\D/g, '');
    const normalized = digits.startsWith('375') ? digits : digits.startsWith('80') ? `375${digits.slice(2)}` : '';
    if (normalized.length !== 12) return phone;
    const cc = normalized.slice(0, 3);
    const op = normalized.slice(3, 5);
    const p1 = normalized.slice(5, 8);
    const p2 = normalized.slice(8, 10);
    const p3 = normalized.slice(10, 12);
    return `+${cc} (${op}) ${p1}-${p2}-${p3}`;
}

export function isOverdue(order: ManagerOrderListItemResponse): boolean {
    if (!order.next_followup_date) return false;
    const date = new Date(order.next_followup_date);
    if (Number.isNaN(date.getTime())) return false;
    return date.getTime() < Date.now();
}
