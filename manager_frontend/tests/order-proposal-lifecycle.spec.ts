import { effectScope, ref, type EffectScope } from 'vue';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ManagerOrderDetailResponse } from '../src/client';
import { useOrderProposalLifecycle } from '../src/composables/useOrderProposalLifecycle';

const ordersMock = vi.hoisted(() => ({
  patchManagerOrder: vi.fn(),
  patchManagerOrderProposal: vi.fn(),
}));
const dialogMock = vi.hoisted(() => ({
  confirmDialog: vi.fn().mockResolvedValue(true),
  promptDialog: vi.fn(),
}));

vi.mock('../src/client', () => ({ ManagerOrdersService: ordersMock }));
vi.mock('../src/services/ui-feedback', () => dialogMock);

const proposal = {
  id: 17,
  name: 'Основной вариант',
  status: 'draft',
  is_selected: true,
  is_archived: false,
  sort_order: 0,
  total_amount: 3_000,
  product_lines: [],
  service_lines: [],
};
const order = ref({
  id: 42,
  proposals: [proposal],
  product_lines: [],
  service_lines: [],
} as ManagerOrderDetailResponse);
let scope: EffectScope;

const createLifecycle = (overrides: Partial<Parameters<typeof useOrderProposalLifecycle>[0]> = {}) => {
  scope = effectScope();
  const options = {
    order,
    negotiationStatus: ref('awaiting_offer'),
    total: ref(3_000),
    localFormError: ref(''),
    buildLinesPayload: vi.fn().mockReturnValue({ products: [], services: [] }),
    validateLines: vi.fn().mockReturnValue(''),
    loadLines: vi.fn(),
    resetLookupState: vi.fn(),
    loadSupplyRequests: vi.fn().mockResolvedValue(undefined),
    clearDraft: vi.fn(),
    currentLinesSnapshot: vi.fn().mockReturnValue('snapshot'),
    savedLinesSnapshot: ref(''),
    setToast: vi.fn(),
    onUpdated: vi.fn(),
    onReload: vi.fn(),
    ...overrides,
  };
  const lifecycle = scope.run(() => useOrderProposalLifecycle(options))!;
  return { lifecycle, options };
};

beforeEach(() => {
  ordersMock.patchManagerOrder.mockResolvedValue(order.value);
  ordersMock.patchManagerOrderProposal.mockResolvedValue(order.value);
});

afterEach(() => {
  scope?.stop();
  vi.clearAllMocks();
});

describe('useOrderProposalLifecycle', () => {
  it('loads the selected proposal and saves its lines as one proposal command', async () => {
    const { lifecycle, options } = createLifecycle();
    lifecycle.loadProposalLines(proposal as any, order.value);

    expect(lifecycle.activeProposalId.value).toBe(17);
    expect(options.loadLines).toHaveBeenCalledWith([], []);

    await lifecycle.saveCurrentProposalLines();

    expect(options.buildLinesPayload).toHaveBeenCalledWith(17);
    expect(ordersMock.patchManagerOrder).toHaveBeenCalledWith(42, { products: [], services: [] });
    expect(options.clearDraft).toHaveBeenCalledOnce();
    expect(options.savedLinesSnapshot.value).toBe('snapshot');
  });

  it('blocks ready-to-send when the commercial boundary reports invalid lines', async () => {
    const validateLines = vi.fn().mockReturnValue('Выберите товар');
    const setToast = vi.fn();
    const { lifecycle } = createLifecycle({ validateLines, setToast });
    lifecycle.loadProposalLines(proposal as any, order.value);

    await lifecycle.changeActiveProposalStatus('ready_to_send');

    expect(ordersMock.patchManagerOrderProposal).not.toHaveBeenCalled();
    expect(setToast).toHaveBeenCalledWith('Выберите товар', 'error');
  });
});
