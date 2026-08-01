import { computed, ref, watch, type Ref } from 'vue';
import type { ManagerOrderDetailResponse } from '../client';
import type {
  OrderDrawerDraft,
  OrderLogisticsComponent,
  ProductLine,
  ProductLogisticsTemplateComponent,
  ServiceLine,
} from '../components/orders/order-editor-types';

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
}: UseOrderDrawerPersistenceOptions) => {
  const expandedDrawerSections = ref(createDefaultDrawerSections());
  const initializedOrderId = ref<number | null>(null);
  const pendingDraftClearOrderId = ref<number | null>(null);
  const draftKey = computed(() => (
    order.value ? `manager_order_drawer_draft_${order.value.id}_${activeProposalId.value || 'default'}` : ''
  ));
  const drawerSectionsKey = computed(() => (
    order.value ? `manager_order_drawer_sections_${order.value.id}` : ''
  ));
  const hasUnsavedChanges = computed(() => (
    Boolean(order.value?.id)
    && (
      (Boolean(savedLinesSnapshot.value) && currentLinesSnapshot() !== savedLinesSnapshot.value)
      || (Boolean(savedFormSnapshot.value) && currentFormSnapshot() !== savedFormSnapshot.value)
    )
  ));

  const persistDraft = () => {
    if (!draftKey.value) return;
    try {
      const payload: OrderDrawerDraft = {
        productLines: productLines.value.map((line) => ({ ...line })),
        serviceLines: serviceLines.value.map((line) => ({ ...line })),
      };
      window.sessionStorage.setItem(draftKey.value, JSON.stringify(payload));
    } catch (error) {
      console.warn('Failed to persist order drawer draft', error);
    }
  };

  const restoreDraft = () => {
    if (!draftKey.value) return;
    try {
      const raw = window.sessionStorage.getItem(draftKey.value);
      if (!raw) return;
      const payload = JSON.parse(raw) as Partial<OrderDrawerDraft>;
      if (Array.isArray(payload.productLines)) {
        productLines.value = payload.productLines.map((line) => ({
          link_id: Number((line as any).link_id || 0) || null,
          product_id: Number(line.product_id || 0),
          product_query: String(line.product_query || ''),
          quantity: Number(line.quantity || 1),
          price: Number(line.price || 0),
          cost: Number(line.cost || 0),
          product_country: (line as any).product_country || null,
          product_logistics_components: Array.isArray((line as any).product_logistics_components)
            ? [...((line as any).product_logistics_components as ProductLogisticsTemplateComponent[])]
            : [],
          logistics_components: Array.isArray((line as any).logistics_components)
            ? [...((line as any).logistics_components as OrderLogisticsComponent[])]
            : null,
        }));
      }
      if (Array.isArray(payload.serviceLines)) {
        serviceLines.value = payload.serviceLines.map((line) => ({
          service_id: line.service_id ?? null,
          title: String(line.title || ''),
          quantity: Number(line.quantity || 1),
          price: Number(line.price || 0),
          cost: Number(line.cost || 0),
          tariff_id: Number(line.tariff_id || 0) || null,
          template_short_name: line.template_short_name || null,
          template_full_description: line.template_full_description || null,
          template_applied_text: line.template_applied_text || null,
          description_mode: line.description_mode === 'full' ? 'full' : 'short',
        }));
      }
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
    if (!draftKey.value) return;
    try {
      window.sessionStorage.removeItem(draftKey.value);
    } catch (error) {
      console.warn('Failed to clear order drawer draft', error);
    }
  };

  watch(productLines, persistDraft, { deep: true });
  watch(serviceLines, persistDraft, { deep: true });
  watch(expandedDrawerSections, persistDrawerSections, { deep: true });

  return {
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
