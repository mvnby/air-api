import type { ManagerOrderListItemResponse } from '../../client';
import type { Segment } from '../../api';

export const STATUS_ORDER = [
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

    if (segment === 'b2b') {
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

function createCustomerOrderGroup(
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
