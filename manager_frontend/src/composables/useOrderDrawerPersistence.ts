import { computed, ref, watch, type Ref } from 'vue';
import type { ManagerOrderDetailResponse } from '../client';
import type {
  OrderDrawerDraft,
  OrderDrawerDraftScope,
  ProductLine,
  ServiceLine,
} from '../components/orders/order-editor-types';
import { isRecord, mergeOrderDraft, type DraftConflict, type DraftChoices } from '../components/orders/order-draft-merge';
import { useDemoReadOnly } from '../services/manager-demo';
import { managerSession } from '../services/manager-session';
import { managerStorefrontSelection } from '../services/manager-storefront-selection';

const createDefaultDrawerSections = () => ({
  website: false,
  clientDetails: false,
  planningDetails: false,
  repair: true,
  proposals: false,
  documents: false,
  payments: false,
  execution: false,
});

export type OrderDrawerSectionsState = ReturnType<typeof createDefaultDrawerSections>;

type UseOrderDrawerPersistenceOptions = {
  order: Readonly<Ref<ManagerOrderDetailResponse | null>>;
  activeProposalId: Readonly<Ref<number | null>>;
  productLines: Ref<ProductLine[]>;
  serviceLines: Ref<ServiceLine[]>;
  savedLinesSnapshot: Ref<string>;
  savedFormSnapshot: Ref<string>;
  currentLinesSnapshot: () => string;
  currentFormSnapshot: () => string;
  restoreFormDraft?: (draft: unknown) => void;
  ready?: Readonly<Ref<boolean>>;
};

export const useOrderDrawerPersistence = ({
  order,
  activeProposalId,
  productLines,
  serviceLines,
  savedLinesSnapshot,
  savedFormSnapshot,
  currentLinesSnapshot,
  currentFormSnapshot,
  restoreFormDraft,
  ready,
}: UseOrderDrawerPersistenceOptions) => {
  const draftConflicts = ref<DraftConflict[]>([]);
  const draftBlocked = computed(() => draftConflicts.value.length > 0);
  let recovery: { payload: Partial<OrderDrawerDraft>; server: Record<string, unknown>; products: ProductLine[]; services: ServiceLine[]; choices: DraftChoices; sourceKey: string; contextKey: string } | null = null;
  const readSnapshot = (raw: string): Record<string, unknown> => {
    try { const value: unknown = JSON.parse(raw); return isRecord(value) ? value : {}; } catch { return {}; }
  };
  const demoReadOnly = useDemoReadOnly();
  const draftScope = computed<OrderDrawerDraftScope | null>(() => {
    const auth = managerSession.auth.value;
    const account = auth?.staff_user_id ? `staff:${auth.staff_user_id}` : auth?.username ? `legacy:${auth.username}` : null;
    return auth?.tenant_id && account ? {
      tenantId: auth.tenant_id,
      account,
      storefrontId: auth.storefront_id ?? null,
      storefrontSlug: managerStorefrontSelection.selectedSlug.value,
    } : null;
  });
  const matchesDraftScope = (stored: unknown) => {
    if (!stored || typeof stored !== 'object' || !draftScope.value) return false;
    const scope = stored as Record<string, unknown>;
    return Object.entries(draftScope.value).every(([key, value]) => scope[key] === value);
  };
  const expandedDrawerSections = ref(createDefaultDrawerSections());
  const initializedOrderId = ref<number | null>(null);
  const pendingDraftClearOrderId = ref<number | null>(null);
  const legacyDraftKey = computed(() => (
    order.value ? `manager_order_drawer_draft_${order.value.id}_${activeProposalId.value || 'default'}` : ''
  ));
  const draftKey = computed(() => draftScope.value && legacyDraftKey.value ? `${legacyDraftKey.value}_${encodeURIComponent(JSON.stringify(draftScope.value))}` : '');
  const drawerSectionsKey = computed(() => (
    order.value ? `manager_order_drawer_sections_${order.value.id}` : ''
  ));
  const hasUnsavedChanges = computed(() => (
    Boolean(order.value?.id)
    && (draftBlocked.value ||
      (Boolean(savedLinesSnapshot.value) && currentLinesSnapshot() !== savedLinesSnapshot.value)
      || (Boolean(savedFormSnapshot.value) && currentFormSnapshot() !== savedFormSnapshot.value)
    )
  ));

  const persistDraft = () => {
    if (!draftKey.value || ready?.value === false || (recovery && recovery.contextKey !== draftKey.value)) return;
    try {
      if (demoReadOnly.value) {
        window.sessionStorage.removeItem(draftKey.value);
        return;
      }
      if (draftBlocked.value) return; // Keep both original versions until every decision is explicit.
      if (!hasUnsavedChanges.value) {
        if (recovery) window.sessionStorage.removeItem(recovery.sourceKey);
        window.sessionStorage.removeItem(draftKey.value);
        return;
      }
      if (!draftScope.value) return;
      const payload: OrderDrawerDraft = {
        version: 2, orderId: order.value!.id, proposalId: activeProposalId.value,
        baseForm: readSnapshot(savedFormSnapshot.value),
        baseLines: readSnapshot(savedLinesSnapshot.value) as OrderDrawerDraft['baseLines'],
        linesDraft: readSnapshot(currentLinesSnapshot()) as OrderDrawerDraft['linesDraft'],
        productLines: productLines.value.map((line) => ({ ...line })),
        serviceLines: serviceLines.value.map((line) => ({ ...line })),
      };
      if (draftScope.value) {
        payload.scope = draftScope.value;
        if (restoreFormDraft) {
          const form = JSON.parse(currentFormSnapshot()) as unknown;
          if (form && typeof form === 'object' && !Array.isArray(form)) payload.formDraft = form as Record<string, unknown>;
        }
      }
      window.sessionStorage.setItem(draftKey.value, JSON.stringify(payload));
      if (recovery && recovery.sourceKey !== draftKey.value) window.sessionStorage.removeItem(recovery.sourceKey);
    } catch (error) {
      console.warn('Failed to persist order drawer draft', error);
    }
  };

  const applyRecovery = () => {
    if (!recovery || recovery.contextKey !== draftKey.value) return;
    const { payload, server, choices } = recovery;
    const hasBase = payload.version === 2 && isRecord(payload.baseForm) && isRecord(payload.baseLines)
      && Array.isArray(payload.baseLines.products) && Array.isArray(payload.baseLines.services) && isRecord(payload.linesDraft);
    const legacyProducts = payload.productLines?.map(line => ({
      ...line, link_id: Number(line.link_id || 0) || null, product_id: Number(line.product_id || 0),
      product_query: String(line.product_query || ''), client_description: String(line.client_description || '').trim() || null,
      quantity: Number(line.quantity || 1), price: Number(line.price || 0), cost: Number(line.cost || 0),
      product_logistics_components: Array.isArray(line.product_logistics_components) ? line.product_logistics_components : [],
      logistics_components: Array.isArray(line.logistics_components) ? line.logistics_components : null,
    }));
    const legacyServices = payload.serviceLines?.map(line => ({
      ...line, link_id: Number(line.link_id || 0) || null, service_id: line.service_id ?? null,
      title: String(line.title || ''), description: line.description || null,
      quantity: Number(line.quantity || 1), price: Number(line.price || 0), cost: Number(line.cost || 0),
    }));
    const local = {
      form: payload.formDraft || {},
      products: hasBase ? payload.linesDraft!.products : legacyProducts ?? server.products,
      services: hasBase ? payload.linesDraft!.services : legacyServices ?? server.services,
    };
    const merged = mergeOrderDraft({ form: payload.baseForm, ...payload.baseLines }, local, server, choices, !hasBase);
    draftConflicts.value = merged.conflicts;
    restoreFormDraft?.(merged.value.form);
    // Editable snapshots omit display/template metadata. Retain the current server metadata for existing rows.
    const enrich = <T extends { link_id?: number | null }>(rows: unknown, fresh: T[], cached: T[]) => {
      const additions = cached.filter(item => !item.link_id);
      return (Array.isArray(rows) ? rows : []).map(row => {
        const value = row as T;
        const restoredId = merged.restoredRows.get(row as object);
        const metadata = restoredId ? cached.find(item => item.link_id === restoredId) : value.link_id ? fresh.find(item => item.link_id === value.link_id) || cached.find(item => item.link_id === value.link_id) : additions.shift();
        return { ...metadata, ...value };
      });
    };
    productLines.value = enrich(merged.value.products, recovery.products, payload.productLines || []);
    serviceLines.value = enrich(merged.value.services, recovery.services, payload.serviceLines || []);
  };
  const resolveDraftConflict = (id: string, choice: 'local' | 'server') => {
    if (!recovery || recovery.contextKey !== draftKey.value || !draftConflicts.value.some(item => item.id === id)) return;
    recovery.choices[id] = { choice, server: draftConflicts.value.find(item => item.id === id)!.server };
    try { window.sessionStorage.setItem(recovery.sourceKey, JSON.stringify({ ...recovery.payload, resolutions: recovery.choices })); }
    catch (error) { console.warn('Failed to persist order draft decision', error); }
    applyRecovery();
    if (!draftBlocked.value) persistDraft();
  };

  const restoreDraft = () => {
    draftConflicts.value = [];
    recovery = null;
    if (!draftKey.value) return;
    try {
      if (demoReadOnly.value) {
        window.sessionStorage.removeItem(draftKey.value);
        return;
      }
      const sourceKey = window.sessionStorage.getItem(draftKey.value) ? draftKey.value : legacyDraftKey.value;
      const raw = window.sessionStorage.getItem(sourceKey);
      if (!raw) return;
      const parsed: unknown = JSON.parse(raw);
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return;
      const payload = parsed as Partial<OrderDrawerDraft>;
      if ((payload.scope !== undefined || payload.formDraft !== undefined) && !matchesDraftScope(payload.scope)) return;
      if (payload.version === 2 && (payload.orderId !== order.value?.id || payload.proposalId !== activeProposalId.value)) return;
      recovery = {
        payload, sourceKey, contextKey: draftKey.value, choices: { ...payload.resolutions },
        server: { form: readSnapshot(savedFormSnapshot.value), products: productLines.value, services: serviceLines.value, ...readSnapshot(savedLinesSnapshot.value) },
        products: productLines.value, services: serviceLines.value,
      };
      applyRecovery();
    } catch (error) {
      console.warn('Failed to restore order drawer draft', error);
    }
  };

  const persistDrawerSections = () => {
    if (!drawerSectionsKey.value) return;
    try {
      window.sessionStorage.setItem(drawerSectionsKey.value, JSON.stringify(expandedDrawerSections.value));
    } catch (error) {
      console.warn('Failed to persist order drawer sections', error);
    }
  };

  const restoreDrawerSections = (): OrderDrawerSectionsState => {
    if (!drawerSectionsKey.value) return createDefaultDrawerSections();
    try {
      const raw = window.sessionStorage.getItem(drawerSectionsKey.value);
      if (!raw) return createDefaultDrawerSections();
      const stored = JSON.parse(raw) as Partial<OrderDrawerSectionsState>;
      return {
        ...createDefaultDrawerSections(),
        ...Object.fromEntries(Object.entries(stored).filter(([, value]) => typeof value === 'boolean')),
      } as OrderDrawerSectionsState;
    } catch (error) {
      console.warn('Failed to restore order drawer sections', error);
      return createDefaultDrawerSections();
    }
  };

  const clearDraft = () => {
    const sourceKey = recovery?.contextKey === draftKey.value ? recovery.sourceKey : undefined;
    draftConflicts.value = [];
    recovery = null;
    if (!draftKey.value) return;
    try {
      window.sessionStorage.removeItem(draftKey.value);
      if (sourceKey) window.sessionStorage.removeItem(sourceKey);
    } catch (error) {
      console.warn('Failed to clear order drawer draft', error);
    }
  };

  watch(productLines, persistDraft, { deep: true });
  watch(serviceLines, persistDraft, { deep: true });
  watch(currentFormSnapshot, persistDraft);
  watch([savedFormSnapshot, savedLinesSnapshot, () => ready?.value], persistDraft, { flush: 'post' });
  watch(expandedDrawerSections, persistDrawerSections, { deep: true });

  return {
    draftConflicts, draftBlocked, resolveDraftConflict, draftContextKey: draftKey, draftIdentityKey: computed(() => JSON.stringify(draftScope.value)),
    clearDraft,
    expandedDrawerSections,
    hasUnsavedChanges,
    initializedOrderId,
    pendingDraftClearOrderId,
    persistDraft,
    restoreDraft,
    restoreDrawerSections,
  };
};
