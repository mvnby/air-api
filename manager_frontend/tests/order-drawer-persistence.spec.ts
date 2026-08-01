import { effectScope, nextTick, ref, type EffectScope } from 'vue';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { ManagerOrderDetailResponse } from '../src/client';
import { useOrderDrawerPersistence } from '../src/composables/useOrderDrawerPersistence';

let scope: EffectScope;

beforeEach(() => window.sessionStorage.clear());

afterEach(() => {
  scope?.stop();
  window.sessionStorage.clear();
});

describe('useOrderDrawerPersistence', () => {
  it('isolates drafts by order and proposal and restores normalized line values', async () => {
    const order = ref({ id: 42 } as ManagerOrderDetailResponse);
    const activeProposalId = ref<number | null>(17);
    const productLines = ref<any[]>([]);
    const serviceLines = ref<any[]>([]);
    scope = effectScope();
    const persistence = scope.run(() => useOrderDrawerPersistence({
      order,
      activeProposalId,
      productLines,
      serviceLines,
      savedLinesSnapshot: ref('saved-lines'),
      savedFormSnapshot: ref('saved-form'),
      currentLinesSnapshot: () => 'saved-lines',
      currentFormSnapshot: () => 'saved-form',
    }))!;

    productLines.value = [{
      product_id: 9,
      product_query: 'Gree Pular',
      quantity: 1,
      price: 3_000,
      cost: 2_000,
    }];
    await nextTick();

    const key = 'manager_order_drawer_draft_42_17';
    expect(window.sessionStorage.getItem(key)).toContain('Gree Pular');
    productLines.value = [];
    persistence.restoreDraft();
    expect(productLines.value[0]).toEqual(expect.objectContaining({
      product_id: 9,
      quantity: 1,
      product_logistics_components: [],
      logistics_components: null,
    }));
  });

  it('persists disclosure state without treating it as a form change', async () => {
    const order = ref({ id: 43 } as ManagerOrderDetailResponse);
    scope = effectScope();
    const persistence = scope.run(() => useOrderDrawerPersistence({
      order,
      activeProposalId: ref(null),
      productLines: ref([]),
      serviceLines: ref([]),
      savedLinesSnapshot: ref('same'),
      savedFormSnapshot: ref('same'),
      currentLinesSnapshot: () => 'same',
      currentFormSnapshot: () => 'same',
    }))!;

    persistence.expandedDrawerSections.value.documents = true;
    await nextTick();

    expect(JSON.parse(window.sessionStorage.getItem('manager_order_drawer_sections_43') || '{}')).toEqual(
      expect.objectContaining({ documents: true }),
    );
    expect(persistence.hasUnsavedChanges.value).toBe(false);
  });
});
