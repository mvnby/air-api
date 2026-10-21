import { effectScope, nextTick, ref, type EffectScope } from 'vue';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ManagerOrderDetailResponse } from '../src/client';
import { useOrderDrawerPersistence } from '../src/composables/useOrderDrawerPersistence';
import { useOrderDrawerForm } from '../src/composables/useOrderDrawerForm';
import { managerSession } from '../src/services/manager-session';
import { managerStorefrontSelection } from '../src/services/manager-storefront-selection';

let scope: EffectScope;

beforeEach(() => window.sessionStorage.clear());

afterEach(() => {
  scope?.stop();
  managerSession.auth.value = null;
  managerStorefrontSelection.selectedSlug.value = null;
  window.sessionStorage.clear();
});

describe('useOrderDrawerPersistence', () => {
  it('isolates drafts by order and proposal and restores normalized line values', async () => {
    const order = ref({ id: 42 } as ManagerOrderDetailResponse);
    const activeProposalId = ref<number | null>(17);
    const productLines = ref<any[]>([]);
    const serviceLines = ref<any[]>([]);
    const currentLinesSnapshot = () => JSON.stringify(productLines.value);
    const savedLinesSnapshot = ref(currentLinesSnapshot());
    scope = effectScope();
    const persistence = scope.run(() => useOrderDrawerPersistence({
      order,
      activeProposalId,
      productLines,
      serviceLines,
      savedLinesSnapshot,
      savedFormSnapshot: ref('saved-form'),
      currentLinesSnapshot,
      currentFormSnapshot: () => 'saved-form',
    }))!;

    productLines.value = [{
      product_id: 9,
      product_query: 'Gree Pular',
      client_description: 'Тихий; серебристый корпус',
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
      client_description: 'Тихий; серебристый корпус',
      quantity: 1,
      product_logistics_components: [],
      logistics_components: null,
    }));
    savedLinesSnapshot.value = currentLinesSnapshot();
    await nextTick();
    expect(window.sessionStorage.getItem(key)).toBeNull();
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

  it('does not restore or retain drafts in the read-only demo', async () => {
    managerSession.auth.value = { demo_read_only: true } as any;
    const order = ref({ id: 44 } as ManagerOrderDetailResponse);
    const productLines = ref<any[]>([]);
    const key = 'manager_order_drawer_draft_44_17';
    window.sessionStorage.setItem(key, JSON.stringify({
      productLines: [{ product_id: 9, product_query: 'Старый черновик' }],
    }));
    scope = effectScope();
    const persistence = scope.run(() => useOrderDrawerPersistence({
      order,
      activeProposalId: ref(17),
      productLines,
      serviceLines: ref([]),
      savedLinesSnapshot: ref('saved'),
      savedFormSnapshot: ref('saved'),
      currentLinesSnapshot: () => JSON.stringify(productLines.value),
      currentFormSnapshot: () => 'saved',
    }))!;

    persistence.restoreDraft();
    productLines.value = [{ product_id: 10, product_query: 'Новая правка' }];
    await nextTick();

    expect(productLines.value).toEqual([{ product_id: 10, product_query: 'Новая правка' }]);
    expect(window.sessionStorage.getItem(key)).toBeNull();
  });
});


const scopedPersistence = (restoreFormDraft = vi.fn()) => {
  const fields = ref({ title: 'Сохранённое название', comment: 'Сохранённый комментарий' });
  const products = ref<any[]>([]);
  const currentFormSnapshot = () => JSON.stringify(fields.value);
  scope = effectScope();
  const persistence = scope.run(() => useOrderDrawerPersistence({
    order: ref({ id: 42 } as ManagerOrderDetailResponse), activeProposalId: ref(17),
    productLines: products, serviceLines: ref([]), savedLinesSnapshot: ref('[]'),
    savedFormSnapshot: ref(currentFormSnapshot()), currentLinesSnapshot: () => JSON.stringify(products.value),
    currentFormSnapshot, restoreFormDraft,
  }))!;
  return { fields, products, persistence, restoreFormDraft };
};
const scopedKey = 'manager_order_drawer_draft_42_17';
const setDraftIdentity = () => {
  managerSession.auth.value = { tenant_id: 5, staff_user_id: 7, username: 'manager', storefront_id: 9 } as any;
  managerStorefrontSelection.selectedSlug.value = 'minsk';
};

describe('scoped order form drafts', () => {
  it('restores an actual form after a fresh editor scope with its server baseline intact', async () => {
    setDraftIdentity();
    const mountEditor = () => {
      scope = effectScope();
      return scope.run(() => {
        const productLines = ref<any[]>([]), serviceLines = ref<any[]>([]);
        const server = ref({ id: 42, status: 'negotiation', title: 'Название с сервера', comment: 'Комментарий с сервера', payments: [] } as unknown as ManagerOrderDetailResponse);
        const form = useOrderDrawerForm({ total: ref(100), productLines, serviceLines, serviceTariffOptions: ref([]), activeServiceSuggestionIndex: ref(null),
          applyTariffTemplateToLine: vi.fn(), buildLinesPayload: () => ({}), validateLines: () => '', setToast: vi.fn(), loadExecutorsOnHydrate: false });
        form.hydrateOrder(server.value);
        const savedFormSnapshot = ref(form.currentFormSnapshot());
        const persistence = useOrderDrawerPersistence({ order: server, activeProposalId: ref(17), productLines, serviceLines,
          savedLinesSnapshot: ref('[]'), savedFormSnapshot, currentLinesSnapshot: () => JSON.stringify(productLines.value),
          currentFormSnapshot: form.currentFormSnapshot, restoreFormDraft: form.restoreFormDraft });
        return { form, persistence, savedFormSnapshot };
      })!;
    };
    const first = mountEditor();
    first.form.orderTitle.value = 'Мой черновик';
    first.form.comment.value = 'Комментарий до ошибки сети';
    await nextTick();
    scope.stop();
    const second = mountEditor();
    second.persistence.restoreDraft();
    expect(second.form.orderTitle.value).toBe('Мой черновик');
    expect(second.form.comment.value).toBe('Комментарий до ошибки сети');
    expect(JSON.parse(second.savedFormSnapshot.value).title).toBe('Название с сервера');
    expect(second.persistence.hasUnsavedChanges.value).toBe(true);
  });

  it('persists form-only edits and restores form data together with the existing line draft after reload', async () => {
    setDraftIdentity();
    const first = scopedPersistence();
    first.fields.value.title = 'Черновик названия';
    first.fields.value.comment = 'Несохранённый комментарий';
    await nextTick();
    const payload = JSON.parse(sessionStorage.getItem(scopedKey)!);
    expect(payload).toMatchObject({
      formDraft: { title: 'Черновик названия', comment: 'Несохранённый комментарий' },
      scope: { tenantId: 5, account: 'staff:7', storefrontId: 9, storefrontSlug: 'minsk' },
    });
    scope.stop();
    const reloaded = scopedPersistence();
    reloaded.persistence.restoreDraft();
    expect(reloaded.restoreFormDraft).toHaveBeenCalledExactlyOnceWith(payload.formDraft);
  });

  it.each(['tenant', 'account', 'storefront', 'storefrontId'])('rejects both form and lines from a different %s scope', async field => {
    setDraftIdentity();
    const first = scopedPersistence();
    first.fields.value.title = 'Чужое название';
    first.products.value = [{ product_id: 5, product_query: 'Чужой товар' }];
    await nextTick();
    scope.stop();
    if (field === 'tenant') managerSession.auth.value = { ...managerSession.auth.value!, tenant_id: 6 };
    if (field === 'account') managerSession.auth.value = { ...managerSession.auth.value!, staff_user_id: 8 };
    if (field === 'storefrontId') managerSession.auth.value = { ...managerSession.auth.value!, storefront_id: 10 };
    if (field === 'storefront') managerStorefrontSelection.selectedSlug.value = 'orsha';
    const next = scopedPersistence();
    next.persistence.restoreDraft();
    expect(next.restoreFormDraft).not.toHaveBeenCalled();
    expect(next.products.value).toEqual([]);
  });

  it.each(['null', '[]', '"text"', '{bad-json', '{"formDraft":{"title":"unsafe"}}'])('ignores malformed or unscoped form payload: %s', raw => {
    setDraftIdentity();
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    sessionStorage.setItem(scopedKey, raw);
    const { persistence, restoreFormDraft, products } = scopedPersistence();
    expect(() => persistence.restoreDraft()).not.toThrow();
    expect(restoreFormDraft).not.toHaveBeenCalled();
    expect(products.value).toEqual([]);
    warn.mockRestore();
  });

  it('continues restoring legacy line-only drafts under the existing key', () => {
    setDraftIdentity();
    sessionStorage.setItem(scopedKey, JSON.stringify({ productLines: [{ product_id: '9', product_query: 'Старый товар', quantity: '2' }] }));
    const { persistence, products, restoreFormDraft } = scopedPersistence();
    persistence.restoreDraft();
    expect(products.value[0]).toMatchObject({ product_id: 9, product_query: 'Старый товар', quantity: 2 });
    expect(restoreFormDraft).not.toHaveBeenCalled();
  });
});
