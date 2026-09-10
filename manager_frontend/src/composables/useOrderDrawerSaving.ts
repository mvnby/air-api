import { computed, nextTick, onScopeDispose, toRaw, watch, type Ref } from 'vue';
import { ManagerOrdersService, type ManagerOrderDetailResponse, type ManagerOrderUpdatePayload } from '../client';
import { parseApiFieldErrors } from '../utils/api-errors';
import type { ProductLine } from '../components/orders/order-editor-types';
import { useOrderAutosave } from './useOrderAutosave';
import { useOrderAutosavePreference } from './useOrderAutosavePreference';

type Options = {
  order: Readonly<Ref<ManagerOrderDetailResponse | null>>;
  ready: Readonly<Ref<boolean>>;
  activeProposalId: Ref<number | null>;
  activeProposalLocked: Readonly<Ref<boolean>>;
  productLines: Ref<ProductLine[]>;
  currentFormSnapshot: () => string;
  currentLinesSnapshot: () => string;
  savedFormSnapshot: Ref<string>;
  savedLinesSnapshot: Ref<string>;
  hasUnsavedChanges: Readonly<Ref<boolean>>;
  buildSavePayload: (locked: boolean, validate?: boolean) => ManagerOrderUpdatePayload | null;
  hydrateOrder: (order: ManagerOrderDetailResponse) => void;
  localFormError: Ref<string>;
  localServerErrors: Ref<Record<string, string>>;
  clearDraft: () => void;
  onUpdated: (order: ManagerOrderDetailResponse) => void;
};

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value));
const formPayload = (payload: ManagerOrderUpdatePayload) => {
  const { products: _products, services: _services, ...form } = payload;
  return form;
};

export const useOrderDrawerSaving = (options: Options) => {
  const { enabled, toggle, identity } = useOrderAutosavePreference();
  let baseline: ManagerOrderUpdatePayload = {};
  const ownResponses = new WeakSet<object>();
  const scope = computed(() => `${identity.value}:${options.order.value?.id}:${options.activeProposalId.value}`);
  let epoch = 0;
  let disposed = false;
  watch([scope, options.ready], () => { epoch += 1; }, { flush: 'sync' });
  onScopeDispose(() => { disposed = true; });
  const resetBaseline = () => {
    baseline = clone(formPayload(options.buildSavePayload(options.activeProposalLocked.value, false) || {}));
    options.savedFormSnapshot.value = options.currentFormSnapshot();
    options.savedLinesSnapshot.value = options.currentLinesSnapshot();
  };

  const save = async () => {
    const order = options.order.value;
    if (!order) return false;
    const fullPayload = options.buildSavePayload(options.activeProposalLocked.value);
    if (!fullPayload) return false;
    const sent = clone(fullPayload);
    const submittedForm = options.currentFormSnapshot();
    const submittedLines = options.currentLinesSnapshot();
    const proposalId = options.activeProposalId.value;
    const requestScope = scope.value;
    const requestEpoch = epoch;
    const originalProducts = [...options.productLines.value];
    const changedForm = Object.fromEntries(Object.entries(formPayload(sent)).filter(([key, value]) => (
      JSON.stringify(value) !== JSON.stringify(baseline[key as keyof ManagerOrderUpdatePayload])
    )));
    const linesChanged = submittedLines !== options.savedLinesSnapshot.value && !options.activeProposalLocked.value;
    const payload: ManagerOrderUpdatePayload = {
      ...changedForm,
      ...(linesChanged ? { products: sent.products, services: sent.services, line_proposal_id: proposalId } : {}),
    };
    try {
      const updated = Object.keys(payload).length
        ? await ManagerOrdersService.patchManagerOrder(order.id, payload)
        : order;
      if (disposed || !options.ready.value || scope.value !== requestScope || epoch !== requestEpoch) return false;
      baseline = clone(formPayload(sent));
      if (options.currentFormSnapshot() === submittedForm) {
        options.hydrateOrder(updated);
        await nextTick();
        baseline = clone(formPayload(options.buildSavePayload(options.activeProposalLocked.value, false) || {}));
        options.savedFormSnapshot.value = options.currentFormSnapshot();
      } else {
        options.savedFormSnapshot.value = submittedForm;
      }
      if (linesChanged) {
        // Keep input objects and editor focus. Only reconcile server-assigned link IDs.
        const proposal = updated.proposals?.find((item) => item.id === proposalId);
        const returnedProducts = [...(proposal?.product_lines || updated.product_lines || [])];
        const saved = JSON.parse(submittedLines);
        originalProducts.forEach((line, index) => {
          let match = returnedProducts.findIndex((item) => line.link_id && item.id === line.link_id);
          if (match < 0) match = returnedProducts.findIndex((item) => item.product_id === saved.products[index]?.product_id);
          if (match < 0) return;
          const [serverLine] = returnedProducts.splice(match, 1);
          if (!serverLine) return;
          if (options.productLines.value.includes(line) && line.product_id === serverLine.product_id) line.link_id = serverLine.id;
          saved.products[index].link_id = serverLine.id;
        });
        options.savedLinesSnapshot.value = JSON.stringify(saved);
      }
      if (!options.hasUnsavedChanges.value) options.clearDraft();
      ownResponses.add(toRaw(updated));
      options.onUpdated(updated);
      await nextTick();
      return true;
    } catch (error) {
      if (disposed || scope.value !== requestScope || epoch !== requestEpoch) return false;
      const parsed = parseApiFieldErrors(error, Object.keys(fullPayload));
      options.localServerErrors.value = parsed.fieldErrors;
      options.localFormError.value = `Не удалось сохранить заказ: ${parsed.message}`;
      return false;
    }
  };

  const autosave = useOrderAutosave({
    enabled,
    ready: options.ready,
    scope,
    snapshot: computed(() => `${options.currentFormSnapshot()}\n${options.currentLinesSnapshot()}`),
    dirty: options.hasUnsavedChanges,
    save,
  });
  const beforeDocumentGenerate = async () => {
    if (!enabled.value && options.hasUnsavedChanges.value) {
      options.localFormError.value = 'Сохраните изменения перед созданием документа или включите автосохранение.';
      return false;
    }
    const mutated = options.hasUnsavedChanges.value || autosave.saving.value;
    if (!await autosave.flush()) return false;
    return { mutated };
  };
  const beforeClose = async () => {
    if (enabled.value) return autosave.flush();
    await autosave.waitForIdle();
    return true;
  };
  return {
    ...autosave, enabled, toggle, resetBaseline, beforeDocumentGenerate, beforeClose,
    isOwnResponse: (order: ManagerOrderDetailResponse) => ownResponses.has(toRaw(order)),
  };
};
