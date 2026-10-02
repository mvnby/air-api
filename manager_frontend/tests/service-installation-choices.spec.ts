import { describe, expect, it } from 'vitest';
import { groupSuggestedInstallations, standardServiceChoice } from '../src/components/orders/service-installation-choices';
import type { ProductLine, ServiceLine } from '../src/components/orders/order-editor-types';
import type { ManagerInstallationStandardTariff } from '../src/client';

const small: ManagerInstallationStandardTariff = {
  code: 'wall.small', title: 'Монтаж настенного кондиционера до 4,2 кВт',
  description: 'Трасса 3 м; проход стены до 80 см', price: '600',
  product_kind: 'complete_split_system', indoor_type: 'wall', route_m: '3',
  holes_by_type: { through_thick: '1' },
};
const large = { ...small, code: 'wall.large', title: 'Монтаж до 7 кВт', price: '800' };
const product = (product_id: number, quantity: number): ProductLine => ({
  product_id, quantity, product_query: 'Кондиционер', price: 1000, cost: 500,
});
const service = (quantity: number, tariff = small): ServiceLine => ({
  service_id: null, title: tariff.title, description: tariff.description,
  installation_standard: tariff, quantity, price: Number(tariff.price), cost: 0,
});

describe('published standard installation choices', () => {
  it('makes a published standard an ordinary priced service with no attached estimate or forced quantity', () => {
    const choice = standardServiceChoice(small);
    expect(choice).toMatchObject({ tariff_id: null, service_kind: 'installation',
      title: small.title, full_description: small.description, price: '600',
      included_route_meters: 3, installation_standard: small });
    expect(choice).not.toHaveProperty('quantity');
    expect(choice).not.toHaveProperty('installation_estimate_revision_id');
  });

  it('groups different products by tariff and reflects their current quantities above twenty', () => {
    const products = [product(1, 18), product(2, 12), product(3, 2), product(4, 5)];
    const choices = [{ product_id: 1, tariff: small }, { product_id: 2, tariff: small },
      { product_id: 3, tariff: large }];
    expect(groupSuggestedInstallations(products, choices, [])).toEqual([
      { tariff: small, quantity: 30 }, { tariff: large, quantity: 2 },
    ]);
    products[1]!.quantity = 25;
    expect(groupSuggestedInstallations(products, choices, [])[0]!.quantity).toBe(43);
  });

  it('subtracts previously added standard rows and omits completely satisfied recommendations', () => {
    const choices = [{ product_id: 1, tariff: small }, { product_id: 2, tariff: large }];
    const renamed = { ...service(3), title: 'Монтаж в спальне', description: 'По согласованию' };
    const legacy = { ...service(2), installation_standard: undefined };
    const unrelated = { ...service(99), title: 'Другая услуга', description: 'Другое', installation_standard: undefined };
    expect(groupSuggestedInstallations([product(1, 8), product(2, 2)], choices,
      [renamed, legacy, service(4, large), unrelated])).toEqual([{ tariff: small, quantity: 3 }]);
    expect(groupSuggestedInstallations([product(1, 5)], choices, [renamed, legacy])).toEqual([]);
  });

  it('does not recommend installations for absent tariffs or invalid product quantities', () => {
    expect(groupSuggestedInstallations([product(1, 0), product(2, -1), product(3, 1.5), product(4, 2)],
      [1, 2, 3].map((product_id) => ({ product_id, tariff: small })), [])).toEqual([]);
  });
});
