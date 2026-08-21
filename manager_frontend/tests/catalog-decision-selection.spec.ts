import { beforeEach, describe, expect, it } from 'vitest';

import {
  CATALOG_DECISION_SELECTION_TTL_MS,
  catalogDecisionSelectionStorageKey,
  loadCatalogDecisionSelection,
  saveCatalogDecisionSelection,
} from '../src/services/catalog-decision-selection';

describe('catalog decision selection persistence', () => {
  const managerKey = catalogDecisionSelectionStorageKey({
    tenant_id: 7,
    staff_user_id: 42,
    username: 'manager',
  });

  beforeEach(() => window.localStorage.clear());

  it('restores the compact selection for 24 hours across workspace mounts', () => {
    expect(CATALOG_DECISION_SELECTION_TTL_MS).toBe(24 * 60 * 60 * 1000);
    saveCatalogDecisionSelection([
      { id: 11, title: 'Gree Pular 12' },
      { id: 22, title: 'MDV Infini 18' },
    ], managerKey, window.localStorage, 1_000);

    expect(loadCatalogDecisionSelection(managerKey, window.localStorage, 1_000 + CATALOG_DECISION_SELECTION_TTL_MS - 1))
      .toEqual([{ id: 11, title: 'Gree Pular 12' }, { id: 22, title: 'MDV Infini 18' }]);
    expect(loadCatalogDecisionSelection(managerKey, window.localStorage, 1_000 + CATALOG_DECISION_SELECTION_TTL_MS)).toEqual([]);
    expect(window.localStorage.getItem(managerKey)).toBeNull();
  });

  it('stores only the model identity needed for the basket', () => {
    const selectionWithCommercialData = { id: 11, title: 'Gree Pular 12', purchase_cost_byn: 900 };
    saveCatalogDecisionSelection([selectionWithCommercialData], managerKey);

    expect(JSON.parse(window.localStorage.getItem(managerKey) || '{}'))
      .toMatchObject({ items: [{ id: 11, title: 'Gree Pular 12' }] });
    expect(loadCatalogDecisionSelection(managerKey)).toEqual([{ id: 11, title: 'Gree Pular 12' }]);
  });

  it('isolates selections between manager accounts in one browser', () => {
    const otherManagerKey = catalogDecisionSelectionStorageKey({
      tenant_id: 7,
      staff_user_id: 99,
      username: 'other',
    });
    const otherTenantKey = catalogDecisionSelectionStorageKey({
      tenant_id: 8,
      staff_user_id: 42,
      username: 'manager',
    });
    saveCatalogDecisionSelection([{ id: 11, title: 'Gree Pular 12' }], managerKey, window.localStorage, 1_000);

    expect(loadCatalogDecisionSelection(otherManagerKey, window.localStorage, 1_001)).toEqual([]);
    expect(loadCatalogDecisionSelection(otherTenantKey, window.localStorage, 1_001)).toEqual([]);
  });
});
