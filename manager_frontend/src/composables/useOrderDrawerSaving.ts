import { computed, nextTick, onScopeDispose, toRaw, watch, type Ref } from 'vue';
import { ManagerOrdersService, type ManagerOrderDetailResponse, type ManagerOrderUpdatePayload } from '../client';
import { parseApiFieldErrors } from '../utils/api-errors';
import type { ProductLine, ServiceLine } from '../components/orders/order-editor-types';
import { useOrderAutosave } from './useOrderAutosave';
import { useOrderAutosavePreference } from './useOrderAutosavePreference';
import { DEMO_READ_ONLY_MESSAGE, useDemoReadOnly } from '../services/manager-demo';

type Options = {
  order: Readonly<Ref<ManagerOrderDetailResponse | null>>;
  ready: Readonly<Ref<boolean>>;
  blocked?: Readonly<Ref<boolean>>;
  autosavePaused?: Readonly<Ref<boolean>>;
  activeProposalId: Ref<number | null>;
  activeProposalLocked: Readonly<Ref<boolean>>;
  productLines: Ref<ProductLine[]>;
  serviceLines?: Ref<ServiceLine[]>;
  currentFormSnapshot: () => string;
  currentLinesSnapshot: () => string;
  savedFormSnapshot: Ref<string>;
  savedLinesSnapshot: Ref<string>;
  hasUnsavedChanges: Readonly<Ref<boolean>>;
  buildSavePayload: (
    locked: boolean,
    validate?: boolean,
    validateCurrency?: boolean,
  ) => ManagerOrderUpdatePayload | null;
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
  const demoReadOnly = useDemoReadOnly();
  const autosaveEnabled = computed(() => enabled.value && !demoReadOnly.value);
  const conflictMessage = 'Сначала выберите значения в восстановленном черновике.';
  watch(() => options.blocked?.value, blocked => {
    if (!blocked && options.localFormError.value === conflictMessage) options.localFormError.value = '';
  });
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
    if (!order || options.blocked?.value) return false;
    const fullPayload = options.buildSavePayload(
      options.activeProposalLocked.value,
      true,
      false,
    );
    if (!fullPayload) return false;
    const sent = clone(fullPayload);
    const submittedForm = options.currentFormSnapshot();
    const submittedLines = options.currentLinesSnapshot();
    const proposalId = options.activeProposalId.value;
    const requestScope = scope.value;
    const requestEpoch = epoch;
    const originalProducts = [...options.productLines.value];
    const originalServices = [...(options.serviceLines?.value || [])];
    const changedForm = Object.fromEntries(Object.entries(formPayload(sent)).filter(([key, value]) => (
      JSON.stringify(value) !== JSON.stringify(baseline[key as keyof ManagerOrderUpdatePayload])
    )));
    const currencyChanged = (
      'target_currency' in changedForm
      || 'target_currency_amount' in changedForm
    );
    if (
      currencyChanged
      && !options.buildSavePayload(options.activeProposalLocked.value, false, true)
    ) return false;
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
        const saved = JSON.parse(submittedLines);
        const reconcile = <T extends ProductLine | ServiceLine>(originals: T[], current: T[], returned: Array<{ id: number } & Record<string, any>>, snapshots: Array<Record<string, any>>, kind: 'product' | 'service') => {
          const remaining = [...returned];
          // Claim known IDs first so anonymous rows cannot steal another line's identity.
          const rows = originals.map((line, index) => ({ line, index })).sort((a,b) => Number(Boolean(b.line.link_id)) - Number(Boolean(a.line.link_id)));
          for (const {line,index} of rows) {
            const submitted = snapshots[index];
            if (!submitted) continue;
            let match = remaining.findIndex(item => line.link_id && item.id === line.link_id);
            if (match < 0 && !line.link_id) match = remaining.findIndex(item => (
              (kind === 'product' ? item.product_id === submitted.product_id : (item.service_id ?? null) === (submitted.service_id ?? null) && String(item.service_title ?? item.title ?? '').trim() === submitted.title)
              && Number(item.quantity) === submitted.quantity && Number(item.price) === submitted.price
              && Number(item.cost || 0) === Number(submitted.cost || 0)
              && String(kind === 'product' ? item.client_description || '' : item.description || '').trim() === String(kind === 'product' ? submitted.client_description || '' : submitted.description || '').trim()
            ));
            if (match < 0) continue;
            const [serverLine] = remaining.splice(match, 1);
            if (!serverLine || !Number.isSafeInteger(serverLine.id) || serverLine.id <= 0) continue;
            if (current.includes(line)) line.link_id = serverLine.id;
            submitted.link_id = serverLine.id;
          }
        };
        reconcile(originalProducts, options.productLines.value, proposal?.product_lines || updated.product_lines || [], saved.products, 'product');
        reconcile(originalServices, options.serviceLines?.value || [], proposal?.service_lines || updated.service_lines || [], saved.services, 'service');
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
    enabled: computed(() => autosaveEnabled.value && !options.autosavePaused?.value),
    ready: options.ready,
    blocked: options.blocked,
    scope,
    snapshot: computed(() => `${options.currentFormSnapshot()}\n${options.currentLinesSnapshot()}`),
    dirty: options.hasUnsavedChanges,
    save,
  });
  const beforeDocumentGenerate = async () => {
    if (demoReadOnly.value) {
      options.localFormError.value = DEMO_READ_ONLY_MESSAGE;
      return false;
    }
    if (!enabled.value && options.hasUnsavedChanges.value) {
      options.localFormError.value = 'Сохраните изменения перед созданием документа или включите автосохранение.';
      return false;
    }
    const mutated = options.hasUnsavedChanges.value || autosave.saving.value;
    if (!await autosave.flush()) return false;
    return { mutated };
  };
  const beforeClose = async () => {
    if (options.blocked?.value || options.autosavePaused?.value) {
      autosave.cancelScheduled();
      await autosave.waitForIdle();
      return true;
    }
    if (demoReadOnly.value) return true;
    if (enabled.value) return autosave.flush();
    await autosave.waitForIdle();
    return true;
  };
  return {
    ...autosave,
    flush: async () => {
      if (options.blocked?.value) { options.localFormError.value = conflictMessage; return false; }
      return autosave.flush();
    },
    enabled: autosaveEnabled,
    toggle: () => {
      if (demoReadOnly.value) {
        options.localFormError.value = DEMO_READ_ONLY_MESSAGE;
        return;
      }
      toggle();
    },
    resetBaseline, beforeDocumentGenerate, beforeClose,
    isOwnResponse: (order: ManagerOrderDetailResponse) => ownResponses.has(toRaw(order)),
  };
};
