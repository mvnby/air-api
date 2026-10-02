import type { ManagerInstallationStandardTariff, ManagerQuickTariffResponse } from '../../client';
import type { ProductLine, ServiceLine } from './order-editor-types';

export type SuggestedInstallation = { tariff: ManagerInstallationStandardTariff; quantity: number };

export const standardServiceChoice = (tariff: ManagerInstallationStandardTariff): ManagerQuickTariffResponse => ({
  tariff_id: null,
  service_kind: 'installation',
  short_name: tariff.title,
  title: tariff.title,
  full_description: tariff.description,
  price: tariff.price,
  category: tariff.indoor_type || '',
  included_route_meters: Number(tariff.route_m),
  installation_standard: tariff,
});

/** Suggestions are quantities in the current proposal, never equipment claims. */
export const groupSuggestedInstallations = (
  products: ProductLine[],
  choices: Array<{ product_id: number; tariff: ManagerInstallationStandardTariff }>,
  services: ServiceLine[],
): SuggestedInstallation[] => {
  const byProduct = new Map(choices.map((choice) => [choice.product_id, choice.tariff]));
  const groups = new Map<string, SuggestedInstallation>();
  for (const product of products) {
    const tariff = byProduct.get(product.product_id);
    if (!tariff || !Number.isInteger(product.quantity) || product.quantity < 1) continue;
    const group = groups.get(tariff.code);
    if (group) group.quantity += product.quantity;
    else groups.set(tariff.code, { tariff, quantity: product.quantity });
  }
  return [...groups.values()].map((group) => {
    const alreadyAdded = services.reduce((sum, line) => {
      const matching = line.installation_standard?.code === group.tariff.code
        || (line.title === group.tariff.title && line.description === group.tariff.description);
      return sum + (matching ? Number(line.quantity || 0) : 0);
    }, 0);
    return { ...group, quantity: Math.max(0, group.quantity - alreadyAdded) };
  }).filter((group) => group.quantity > 0);
};
