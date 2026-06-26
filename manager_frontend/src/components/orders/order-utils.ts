import type { ManagerOrderListItemResponse } from '../../client';
import type { Segment } from '../../api';

export const STATUS_ORDER = [
    'negotiation',
    'execution',
    'closed',
] as const;

export const NEGOTIATION_STATUS_OPTIONS = [
    { value: 'awaiting_offer', label: 'Ждет предложение', icon: 'rate_review', tone: 'sky' },
    { value: 'awaiting_visit', label: 'Ждет выезд', icon: 'location_on', tone: 'violet' },
    { value: 'proposal_sent', label: 'Ожидаем ответ', icon: 'send', tone: 'amber' },
    { value: 'awaiting_payment', label: 'Ожидаем оплату', icon: 'payments', tone: 'emerald' },
    { value: 'follow_up', label: 'Уточнить', icon: 'contact_phone', tone: 'slate' },
] as const;

export const BOARD_COLUMNS = [
    { value: 'negotiation', label: 'Переговоры', icon: 'forum', tone: 'sky' },
    { value: 'execution', label: 'Установка / работы', icon: 'construction', tone: 'teal' },
    { value: 'closed_won', label: 'Завершено', icon: 'check_circle', tone: 'green' },
    { value: 'closed_lost', label: 'Отказники', icon: 'cancel', tone: 'rose' },
] as const;

export const STATUS_LABELS: Record<string, string> = {
    new_lead: 'Новый лид',
    negotiation: 'Переговоры',
    execution: 'Монтаж',
    closed: 'Закрыто',
};

export const NEGOTIATION_STATUS_LABELS: Record<string, string> = Object.fromEntries(
    NEGOTIATION_STATUS_OPTIONS.map((item) => [item.value, item.label]),
);

export const BOARD_COLUMN_LABELS: Record<string, string> = Object.fromEntries(
    BOARD_COLUMNS.map((item) => [item.value, item.label]),
);

export const BOARD_COLUMN_TONE_CLASSES: Record<string, { column: string; badge: string; text: string }> = {
    negotiation: {
        column: 'border-sky-100 bg-sky-50/60 dark:border-sky-500/20 dark:bg-sky-500/10',
        badge: 'bg-sky-100 text-sky-700 dark:bg-sky-500/20 dark:text-sky-200',
        text: 'text-sky-800 dark:text-sky-200',
    },
    awaiting_offer: {
        column: 'border-sky-100 bg-sky-50/60 dark:border-sky-500/20 dark:bg-sky-500/10',
        badge: 'bg-sky-100 text-sky-700 dark:bg-sky-500/20 dark:text-sky-200',
        text: 'text-sky-800 dark:text-sky-200',
    },
    awaiting_visit: {
        column: 'border-violet-100 bg-violet-50/60 dark:border-violet-500/20 dark:bg-violet-500/10',
        badge: 'bg-violet-100 text-violet-700 dark:bg-violet-500/20 dark:text-violet-200',
        text: 'text-violet-800 dark:text-violet-200',
    },
    proposal_sent: {
        column: 'border-amber-100 bg-amber-50/70 dark:border-amber-500/20 dark:bg-amber-500/10',
        badge: 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-200',
        text: 'text-amber-800 dark:text-amber-200',
    },
    awaiting_payment: {
        column: 'border-emerald-100 bg-emerald-50/60 dark:border-emerald-500/20 dark:bg-emerald-500/10',
        badge: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-200',
        text: 'text-emerald-800 dark:text-emerald-200',
    },
    follow_up: {
        column: 'border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800',
        badge: 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-200',
        text: 'text-slate-700 dark:text-slate-200',
    },
    execution: {
        column: 'border-teal-100 bg-teal-50/60 dark:border-teal-500/20 dark:bg-teal-500/10',
        badge: 'bg-teal-100 text-teal-700 dark:bg-teal-500/20 dark:text-teal-200',
        text: 'text-teal-800 dark:text-teal-200',
    },
    closed_won: {
        column: 'border-green-100 bg-green-50/60 dark:border-green-500/20 dark:bg-green-500/10',
        badge: 'bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-200',
        text: 'text-green-800 dark:text-green-200',
    },
    closed_lost: {
        column: 'border-rose-100 bg-rose-50/60 dark:border-rose-500/20 dark:bg-rose-500/10',
        badge: 'bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-200',
        text: 'text-rose-800 dark:text-rose-200',
    },
};

export const BOARD_CARD_ACCENT_CLASSES: Record<string, string> = {
    negotiation: 'border-sky-200 bg-sky-50/50 shadow-sky-100/80 hover:shadow-sky-200/80 dark:border-sky-500/30 dark:bg-sky-500/10 dark:shadow-none',
    awaiting_offer: 'border-sky-200 bg-sky-50/50 shadow-sky-100/80 hover:shadow-sky-200/80 dark:border-sky-500/30 dark:bg-sky-500/10 dark:shadow-none',
    awaiting_visit: 'border-violet-200 bg-violet-50/55 shadow-violet-100/80 hover:shadow-violet-200/80 dark:border-violet-500/30 dark:bg-violet-500/10 dark:shadow-none',
    proposal_sent: 'border-amber-200 bg-amber-50/60 shadow-amber-100/80 hover:shadow-amber-200/80 dark:border-amber-500/30 dark:bg-amber-500/10 dark:shadow-none',
    awaiting_payment: 'border-emerald-200 bg-emerald-50/55 shadow-emerald-100/80 hover:shadow-emerald-200/80 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:shadow-none',
    follow_up: 'border-slate-300 bg-slate-50 shadow-slate-100/80 hover:shadow-slate-200/80 dark:border-slate-600 dark:bg-slate-700/40 dark:shadow-none',
    execution: 'border-teal-200 bg-teal-50/55 shadow-teal-100/80 hover:shadow-teal-200/80 dark:border-teal-500/30 dark:bg-teal-500/10 dark:shadow-none',
    closed_won: 'border-green-200 bg-green-50/55 shadow-green-100/80 hover:shadow-green-200/80 dark:border-green-500/30 dark:bg-green-500/10 dark:shadow-none',
    closed_lost: 'border-rose-200 bg-rose-50/55 shadow-rose-100/80 hover:shadow-rose-200/80 dark:border-rose-500/30 dark:bg-rose-500/10 dark:shadow-none',
};

export type ConcreteSegment = 'b2c' | 'b2b';

export function getOrderSegment(order: ManagerOrderListItemResponse): ConcreteSegment {
    const customer = order.customer;
    const inn = String(customer?.inn || '').trim();
    const customerType = String(customer?.type || '').trim();
    return customerType === 'company' || Boolean(inn) ? 'b2b' : 'b2c';
}

export function getOrderBoardColumn(order: ManagerOrderListItemResponse): string {
    if (order.status === 'closed') {
        return order.closing_result === 'lost' ? 'closed_lost' : 'closed_won';
    }
    if (order.status === 'execution') return 'execution';
    if (order.status === 'negotiation') return 'negotiation';
    return order.status || 'awaiting_offer';
}

export function getOrderBoardLabel(order: ManagerOrderListItemResponse): string {
    return BOARD_COLUMN_LABELS[getOrderBoardColumn(order)] || STATUS_LABELS[order.status] || order.status;
}

export function getOrderNegotiationStatus(order: ManagerOrderListItemResponse): string {
    const value = order.negotiation_status || '';
    return NEGOTIATION_STATUS_LABELS[value] ? value : 'awaiting_offer';
}

export function getOrderNegotiationLabel(order: ManagerOrderListItemResponse): string {
    return NEGOTIATION_STATUS_LABELS[getOrderNegotiationStatus(order)] || 'Ждет предложение';
}

export function formatMoney(value: number): string {
    return `${Math.round(value).toLocaleString('ru-RU')} BYN`;
}

export function formatDate(value?: string | null): string {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '—';
    return date.toLocaleDateString('ru-RU');
}

export function formatRelativeAge(value?: string | null): string {
    if (!value) return 'давно';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return 'давно';
    const diffMs = Math.max(0, Date.now() - date.getTime());
    const minutes = Math.floor(diffMs / 60000);
    if (minutes < 60) return `${Math.max(1, minutes)} мин`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} ч`;
    const days = Math.floor(hours / 24);
    return `${days} дн`;
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

export type CustomerOrderGroup = {
    id: string;
    customerId: number;
    customerName: string;
    originalCustomerName: string;
    orders: ManagerOrderListItemResponse[];
    totalAmount: number;
    margin: number;
    balanceDue: number;
    statusCounts: Array<{ status: string; count: number }>;
    addresses: string[];
    hiddenAddressCount: number;
    hasOverdue: boolean;
    needsAttention: boolean;
};

export type OrderRenderItem =
    | { type: 'order'; order: ManagerOrderListItemResponse }
    | { type: 'group'; group: CustomerOrderGroup };

export function getOrderCustomerName(order: ManagerOrderListItemResponse, segment: Segment): string {
    const customer = order.customer;
    if (!customer) return `Заказ #${order.id}`;

    if ((segment === 'all' ? getOrderSegment(order) : segment) === 'b2b') {
        return customer.full_legal_name
            || customer.name
            || customer.phone
            || customer.email
            || `Клиент #${customer.id}`;
    }

    return customer.name
        || customer.phone
        || customer.email
        || `Клиент #${customer.id}`;
}

export function formatOrderCount(count: number): string {
    const mod10 = count % 10;
    const mod100 = count % 100;
    if (mod10 === 1 && mod100 !== 11) return `${count} заказ`;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${count} заказа`;
    return `${count} заказов`;
}

export function buildCustomerOrderRenderItems(
    orders: ManagerOrderListItemResponse[],
    segment: Segment,
    groupingEnabled: boolean,
    customerAliases: Record<number, string> = {},
): OrderRenderItem[] {
    if (!groupingEnabled) {
        return orders.map((order) => ({ type: 'order', order }));
    }

    const customerCounts = new Map<number, number>();
    for (const order of orders) {
        const customerId = order.customer?.id;
        if (!customerId) continue;
        customerCounts.set(customerId, (customerCounts.get(customerId) || 0) + 1);
    }

    const groupedByCustomer = new Map<number, ManagerOrderListItemResponse[]>();
    for (const order of orders) {
        const customerId = order.customer?.id;
        if (!customerId || (customerCounts.get(customerId) || 0) < 2) continue;
        const group = groupedByCustomer.get(customerId);
        if (group) group.push(order);
        else groupedByCustomer.set(customerId, [order]);
    }
    const emittedCustomers = new Set<number>();
    const items: OrderRenderItem[] = [];

    for (const order of orders) {
        const customerId = order.customer?.id;
        if (!customerId || (customerCounts.get(customerId) || 0) < 2) {
            items.push({ type: 'order', order });
            continue;
        }

        if (emittedCustomers.has(customerId)) continue;

        emittedCustomers.add(customerId);
        const groupOrders = groupedByCustomer.get(customerId) || [order];
        items.push({ type: 'group', group: createCustomerOrderGroup(customerId, groupOrders, segment, customerAliases[customerId]) });
    }

    return items;
}

export function createCustomerOrderGroup(
    customerId: number,
    orders: ManagerOrderListItemResponse[],
    segment: Segment,
    alias?: string,
): CustomerOrderGroup {
    const firstOrder = orders[0];
    const statusCounter = new Map<string, number>();
    const addresses: string[] = [];

    for (const order of orders) {
        statusCounter.set(order.status, (statusCounter.get(order.status) || 0) + 1);
        const address = order.delivery_address?.trim();
        if (address && !addresses.includes(address)) addresses.push(address);
    }

    const originalCustomerName = firstOrder ? getOrderCustomerName(firstOrder, segment) : `Клиент #${customerId}`;
    const customerName = alias?.trim() || originalCustomerName;

    return {
        id: `customer-${customerId}-${orders.map((order) => order.id).join('-')}`,
        customerId,
        customerName,
        originalCustomerName,
        orders,
        totalAmount: orders.reduce((sum, order) => sum + order.total_amount, 0),
        margin: orders.reduce((sum, order) => sum + order.margin, 0),
        balanceDue: orders.reduce((sum, order) => sum + Number(order.balance_due || 0), 0),
        statusCounts: Array.from(statusCounter.entries()).map(([status, count]) => ({ status, count })),
        addresses: addresses.slice(0, 3),
        hiddenAddressCount: Math.max(addresses.length - 3, 0),
        hasOverdue: orders.some(isOverdue),
        needsAttention: orders.some((order) => order.needs_attention),
    };
}
