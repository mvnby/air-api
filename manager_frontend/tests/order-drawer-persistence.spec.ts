import { effectScope, nextTick, ref, type EffectScope } from 'vue';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ManagerOrderDetailResponse } from '../src/client';
import { useOrderDrawerPersistence } from '../src/composables/useOrderDrawerPersistence';
import { useOrderDrawerForm } from '../src/composables/useOrderDrawerForm';
import { managerSession } from '../src/services/manager-session';
import { managerStorefrontSelection } from '../src/services/manager-storefront-selection';

let scope: EffectScope;

beforeEach(() => { window.sessionStorage.clear(); setDraftIdentity(); });

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
    const currentLinesSnapshot = () => JSON.stringify({ products: productLines.value, services: serviceLines.value });
    const savedLinesSnapshot = ref(currentLinesSnapshot());
    scope = effectScope();
    const persistence = scope.run(() => useOrderDrawerPersistence({
      order,
      activeProposalId,
      productLines,
      serviceLines,
      savedLinesSnapshot,
      savedFormSnapshot: ref('{}'),
      currentLinesSnapshot,
      currentFormSnapshot: () => '{}',
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

    const key = scopedKey;
    expect(window.sessionStorage.getItem(key)).toContain('Gree Pular');
    productLines.value = [];
    persistence.restoreDraft();
    expect(productLines.value[0]).toEqual(expect.objectContaining({
      product_id: 9,
      client_description: 'Тихий; серебристый корпус',
      quantity: 1,
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

  it('does not restore drafts or delete unknown legacy inputs in the read-only demo', async () => {
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
      currentLinesSnapshot: () => JSON.stringify({ products: productLines.value, services: serviceLines.value }),
      currentFormSnapshot: () => 'saved',
    }))!;

    persistence.restoreDraft();
    productLines.value = [{ product_id: 10, product_query: 'Новая правка' }];
    await nextTick();

    expect(productLines.value).toEqual([{ product_id: 10, product_query: 'Новая правка' }]);
    expect(window.sessionStorage.getItem(key)).toContain('Старый черновик');
  });
});


const scopedPersistence = (restoreFormDraft = vi.fn()) => {
  const fields = ref({ title: 'Сохранённое название', comment: 'Сохранённый комментарий' });
  const products = ref<any[]>([]);
  const currentFormSnapshot = () => JSON.stringify(fields.value);
  scope = effectScope();
  const persistence = scope.run(() => useOrderDrawerPersistence({
    order: ref({ id: 42 } as ManagerOrderDetailResponse), activeProposalId: ref(17),
    productLines: products, serviceLines: ref([]), savedLinesSnapshot: ref('{"products":[],"services":[]}'),
    savedFormSnapshot: ref(currentFormSnapshot()), currentLinesSnapshot: () => JSON.stringify({ products: products.value, services: [] }),
    currentFormSnapshot, restoreFormDraft,
  }))!;
  return { fields, products, persistence, restoreFormDraft };
};
const legacyKey = 'manager_order_drawer_draft_42_17';
const scopedKey = `${legacyKey}_${encodeURIComponent(JSON.stringify({tenantId:5,account:'staff:7',storefrontId:9,storefrontSlug:'minsk'}))}`;
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
          savedLinesSnapshot: ref('{"products":[],"services":[]}'), savedFormSnapshot, currentLinesSnapshot: () => JSON.stringify({ products: productLines.value, services: serviceLines.value }),
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

  it('keeps legacy line-only drafts for explicit review under the existing key', () => {
    setDraftIdentity();
    sessionStorage.setItem(legacyKey, JSON.stringify({ productLines: [{ product_id: 9, product_query: 'Старый товар', quantity: 2 }] }));
    const { persistence, products, restoreFormDraft } = scopedPersistence();
    persistence.restoreDraft();
    expect(products.value).toEqual([]);
    expect(persistence.draftBlocked.value).toBe(true);
    expect(sessionStorage.getItem(legacyKey)).toContain('Старый товар');
    const conflict = persistence.draftConflicts.value[0]!;
    persistence.resolveDraftConflict(conflict.id, 'local');
    expect(products.value[0]).toMatchObject({ product_id: 9, product_query: 'Старый товар', quantity: 2 });
    expect(persistence.draftBlocked.value).toBe(false);
  });
});

import { mergeOrderDraft } from '../src/components/orders/order-draft-merge';

describe('three-way draft recovery', () => {
  const service = (id: number, price: number) => ({ link_id: id, title: `Услуга ${id}`, quantity: 1, price });
  const tree = (form: any = {}, services: any[] = [], products: any[] = []) => ({ form, services, products });
  it('merges actual edits at field level, retaining server status, currency, object and repair data', () => {
    const base = tree({ title: 'A', status: 'negotiation', targetCurrency: null, customerBranchId: 1, repairMeta: { diagnosis: '', serial: 'old' } });
    const local = structuredClone(base); local.form.title = 'B'; local.form.repairMeta.diagnosis = 'Моя диагностика';
    const fresh = tree({ title: 'A', status: 'execution', targetCurrency: 'EUR', customerBranchId: 2, repairMeta: { diagnosis: '', serial: 'new' } });
    const result = mergeOrderDraft(base, local, fresh);
    expect(result.conflicts).toEqual([]);
    expect(result.value).toEqual(tree({ ...fresh.form, title: 'B', repairMeta: { diagnosis: 'Моя диагностика', serial: 'new' } }));
  });
  it('merges separate fields in the same service and preserves concurrent additions and removals', () => {
    const base = tree({}, [service(1, 1200), service(2, 10)]);
    const local = tree({}, [{ ...service(1, 1200), quantity: 2 }, service(2, 10), { link_id: null, title: 'Новая локальная', price: 20 }]);
    const fresh = tree({}, [service(1, 1800)]);
    const result = mergeOrderDraft(base, local, fresh);
    expect(result.conflicts).toEqual([]);
    expect(result.value.services).toEqual([{ ...service(1, 1800), quantity: 2 }, { link_id: null, title: 'Новая локальная', price: 20 }]);
  });
  it.each(['services', 'products'])('requires an explicit choice for conflicting %s price and deletion', kind => {
    const base = { form: {}, products: [], services: [], [kind]: [service(1, 1200)] };
    const local = { ...base, [kind]: [service(1, 1400)] };
    const fresh = { ...base, [kind]: [service(1, 1800)] };
    const conflict = mergeOrderDraft(base, local, fresh).conflicts[0]!;
    expect(conflict.path).toEqual([kind, '1', 'price']);
    expect(mergeOrderDraft(base, local, fresh, { [conflict.id]: { choice: 'local', server: 1800 } }).value[kind]).toEqual([service(1, 1400)]);
    expect(mergeOrderDraft(base, { ...base, [kind]: [] }, fresh).conflicts).toHaveLength(1);
    expect(mergeOrderDraft(base, local, { ...base, [kind]: [] }).conflicts).toHaveLength(1);
  });
  it('does not reuse a decision for a newer server value after reload', () => {
    const base = tree({ title: 'A' }), local = tree({ title: 'B' }), fresh = tree({ title: 'C' });
    const conflict = mergeOrderDraft(base, local, fresh).conflicts[0]!;
    const choices = { [conflict.id]: { choice: 'local' as const, server: 'C' } };
    expect(mergeOrderDraft(base, local, fresh, choices).conflicts).toEqual([]);
    expect(mergeOrderDraft(base, local, tree({ title: 'D' }), choices).conflicts).toHaveLength(1);
  });
});

describe('draft storage boundaries', () => {
  it('preserves the original account draft after another account opens and edits the same order', async () => {
    const first = scopedPersistence(); first.fields.value.title = 'Ввод первого'; await nextTick(); scope.stop();
    const original = sessionStorage.getItem(scopedKey);
    managerSession.auth.value = { ...managerSession.auth.value!, staff_user_id: 8 };
    const second = scopedPersistence(); second.persistence.restoreDraft(); await nextTick();
    second.fields.value.title = 'Ввод второго'; await nextTick(); scope.stop();
    expect(sessionStorage.getItem(scopedKey)).toBe(original);
    setDraftIdentity(); const returned = scopedPersistence(); returned.persistence.restoreDraft();
    expect(returned.restoreFormDraft).toHaveBeenCalledWith(expect.objectContaining({ title: 'Ввод первого' }));
  });
  it('does not persist initialization over an existing legacy scoped draft', async () => {
    const ready = ref(false), fields = ref({ title: 'Сервер' });
    sessionStorage.setItem(legacyKey, JSON.stringify({ scope: { tenantId:5,account:'staff:7',storefrontId:9,storefrontSlug:'minsk' }, formDraft: { title: 'Старый ввод' } }));
    scope = effectScope();
    const persistence = scope.run(() => useOrderDrawerPersistence({ order: ref({id:42} as any), activeProposalId:ref(17), productLines:ref([]),serviceLines:ref([]),
      savedFormSnapshot:ref(JSON.stringify(fields.value)), savedLinesSnapshot:ref('{"products":[],"services":[]}'), currentFormSnapshot:()=>JSON.stringify(fields.value),currentLinesSnapshot:()=>'{"products":[],"services":[]}', restoreFormDraft: vi.fn(), ready }))!;
    fields.value.title = 'Промежуточная загрузка'; await nextTick();
    persistence.restoreDraft(); ready.value = true; await nextTick();
    expect(persistence.draftBlocked.value).toBe(true);
    expect(sessionStorage.getItem(legacyKey)).toContain('Старый ввод');
  });
  it.each([1200, 1800])('requires review when a new local row may already have been committed and repriced to %s after a lost response', price => {
    const row = { title: 'Диагностика', price:1200, quantity:1 };
    const base = { services: [], products: [] }, local = { ...base, services:[{...row,link_id:null}] }, server = { ...base, services:[{...row,price,link_id:81}] };
    const result = mergeOrderDraft(base, local, server);
    expect(result.conflicts).toHaveLength(1);
    expect(result.value.services).toEqual(server.services);
    const conflict = result.conflicts[0]!;
    expect(mergeOrderDraft(base,local,server,{[conflict.id]:{choice:'server',server:conflict.server}}).value.services).toEqual(server.services);
  });
});

it('does not combine a local currency amount with another manager currency change', () => {
  const form = { enableCurrency: true, targetCurrency: 'USD', targetCurrencyAmount: 100 };
  const result = mergeOrderDraft({form}, {form:{...form,targetCurrencyAmount:150}}, {form:{...form,targetCurrency:'EUR'}});
  expect(result.conflicts).toEqual([expect.objectContaining({path:['form','currency']})]);
});

it('retains both inputs after partial conflict resolution and a newer server response on reload', async () => {
  const original = scopedPersistence();
  original.fields.value = { title: 'Мой заголовок', comment: 'Мой комментарий' }; await nextTick(); scope.stop();
  const saved = JSON.parse(sessionStorage.getItem(scopedKey)!);
  const reopen = (title: string) => {
    const fields = ref({ title, comment: 'Серверный комментарий' });
    scope = effectScope();
    const snapshot = () => JSON.stringify(fields.value);
    const persistence = scope.run(() => useOrderDrawerPersistence({ order:ref({id:42} as any),activeProposalId:ref(17),productLines:ref([]),serviceLines:ref([]),
      savedFormSnapshot:ref(snapshot()),savedLinesSnapshot:ref('{"products":[],"services":[]}'), currentFormSnapshot:snapshot,currentLinesSnapshot:()=>'{"products":[],"services":[]}', restoreFormDraft:draft=>{fields.value=draft as typeof fields.value;} }))!;
    persistence.restoreDraft(); return persistence;
  };
  const first = reopen('Серверный заголовок');
  const titleConflict = first.draftConflicts.value.find(item=>item.path.at(-1)==='title')!;
  first.resolveDraftConflict(titleConflict.id,'local'); await nextTick();
  expect(first.draftConflicts.value).toHaveLength(1);
  expect(JSON.parse(sessionStorage.getItem(scopedKey)!).formDraft).toEqual(saved.formDraft);
  scope.stop(); const second = reopen('Более новый заголовок');
  expect(second.draftConflicts.value).toHaveLength(2);
  expect(second.draftConflicts.value.find(item=>item.path.at(-1)==='title')).toMatchObject({local:'Мой заголовок',server:'Более новый заголовок'});
});
