import { describe, expect, it } from 'vitest';
import { buildProductPowerSupplyDescription } from '../src/utils/product-power-supply';
import fixtures from '../../tests/fixtures/product_power_supply.json';
import manifest from '../../config/catalog_source_repairs/power-supply-2026-10.json';

const cases = fixtures as {
  name: string; specs: Record<string, unknown>; product_kind?: string; expected: string;
}[];

describe('catalog power supply in client descriptions', () => {
  it.each(cases)('$name', ({ specs, product_kind, expected }) => {
    expect(buildProductPowerSupplyDescription(specs, product_kind)).toBe(expected);
  });

  it.each(manifest.products)('reviewed source for product $identity.id has no unresolved power warning', (row) => {
    const result = buildProductPowerSupplyDescription(row.specs_set, row.identity.product_kind);
    expect(result).toContain(' В');
    expect(result).not.toContain('уточн');
  });
});
