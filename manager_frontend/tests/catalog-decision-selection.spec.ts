import { beforeEach, describe, expect, it } from 'vitest';

import {
  CATALOG_DECISION_SELECTION_STORAGE_KEY,
  CATALOG_DECISION_SELECTION_TTL_MS,
  loadCatalogDecisionSelection,
  saveCatalogDecisionSelection,
} from '../src/services/catalog-decision-selection';

describe('catalog decision selection persistence', () => {
  beforeEach(() => window.sessionStorage.clear());

  it('restores the compact selection for five minutes across workspace mounts', () => {
    saveCatalogDecisionSelection([
      { id: 11, title: 'Gree Pular 12' },
      { id: 22, title: 'MDV Infini 18' },
    ], window.sessionStorage, 1_000);

    expect(loadCatalogDecisionSelection(window.sessionStorage, 1_000 + CATALOG_DECISION_SELECTION_TTL_MS - 1))
      .toEqual([{ id: 11, title: 'Gree Pular 12' }, { id: 22, title: 'MDV Infini 18' }]);
    expect(loadCatalogDecisionSelection(window.sessionStorage, 1_000 + CATALOG_DECISION_SELECTION_TTL_MS)).toEqual([]);
    expect(window.sessionStorage.getItem(CATALOG_DECISION_SELECTION_STORAGE_KEY)).toBeNull();
  });

  it('stores only the model identity needed for the basket', () => {
    const selectionWithCommercialData = { id: 11, title: 'Gree Pular 12', purchase_cost_byn: 900 };
    saveCatalogDecisionSelection([selectionWithCommercialData], window.sessionStorage, 1_000);

    expect(JSON.parse(window.sessionStorage.getItem(CATALOG_DECISION_SELECTION_STORAGE_KEY) || '{}'))
      .toMatchObject({ items: [{ id: 11, title: 'Gree Pular 12' }] });
  });
});
