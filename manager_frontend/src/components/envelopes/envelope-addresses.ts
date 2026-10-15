import type { ManagerCatalogCustomerItemResponse } from '../../client';

export function splitPostalAddress(value: string): { address: string; postal_code: string } {
  const matches = [...value.matchAll(/(?:^|[\s,;])([0-9]{6})(?=$|[\s,;])/g)];
  if (matches.length !== 1) return { address: value.trim(), postal_code: '' };
  const match = matches[0]!;
  return {
    address: `${value.slice(0, match.index)} ${value.slice(match.index! + match[0].length)}`.replace(/[,;]\s*[,;]/g, ',').replace(/^[\s,;]+|[\s,;]+$/g, '').replace(/\s+/g, ' '),
    postal_code: match[1]!,
  };
}

export function envelopeAddresses(customer: ManagerCatalogCustomerItemResponse, orderAddress?: string) {
  const candidates = [
    { id: 'legal', label: 'Юридический адрес', address: customer.legal_address || '' },
    { id: 'actual', label: 'Фактический / почтовый адрес', address: customer.actual_address || '' },
    ...(customer.branches || []).map(branch => ({ id: `branch-${branch.id}`, label: branch.name || 'Адрес филиала', address: branch.delivery_address })),
    { id: 'order', label: 'Адрес из заказа', address: orderAddress || '' },
    { id: 'last', label: 'Последний адрес доставки', address: customer.last_delivery_address || '' },
  ];
  const seen = new Set<string>();
  return candidates.filter(item => {
    const normalized = item.address.trim().toLocaleLowerCase().replace(/\s+/g, ' ');
    if (!normalized || seen.has(normalized)) return false;
    seen.add(normalized);
    return true;
  });
}
