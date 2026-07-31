import { ref } from 'vue';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ManagerOrderDetailResponse } from '../src/client';
import { useOrderDrawerActions } from '../src/composables/useOrderDrawerActions';

const apiMock = vi.hoisted(() => ({ patchManagerOrder: vi.fn() }));
const ordersMock = vi.hoisted(() => ({ deleteManagerOrder: vi.fn() }));
const confirmDialog = vi.hoisted(() => vi.fn());

vi.mock('../src/api', () => ({ api: apiMock }));
vi.mock('../src/client', () => ({ ManagerOrdersService: ordersMock }));
vi.mock('../src/services/ui-feedback', () => ({ confirmDialog }));

const order = ref({ id: 42, is_on_hold: false } as ManagerOrderDetailResponse);

const createActions = (dirty = false) => {
  const options = {
    order,
    displayOrderTitle: ref('Монтаж в офисе'),
    hasUnsavedChanges: ref(dirty),
    localFormError: ref(''),
    persistDraft: vi.fn(),
    clearDraft: vi.fn(),
    setToast: vi.fn(),
    onBeforeClose: vi.fn(),
    onModelValue: vi.fn(),
    onUpdated: vi.fn(),
    onDeleted: vi.fn(),
  };
  return { actions: useOrderDrawerActions(options), options };
};

afterEach(() => vi.clearAllMocks());

describe('useOrderDrawerActions', () => {
  it('keeps the drawer open when the manager rejects discarding a dirty draft', async () => {
    confirmDialog.mockResolvedValue(false);
    const { actions, options } = createActions(true);

    await actions.closeDrawer();

    expect(options.persistDraft).toHaveBeenCalledOnce();
    expect(options.clearDraft).not.toHaveBeenCalled();
    expect(options.onModelValue).not.toHaveBeenCalled();
  });

  it('updates the hold flag through the order command and reports the new state', async () => {
    apiMock.patchManagerOrder.mockResolvedValue({ ...order.value, is_on_hold: true });
    const { actions, options } = createActions();

    await actions.toggleHold();

    expect(apiMock.patchManagerOrder).toHaveBeenCalledWith(42, {
      is_on_hold: true,
      on_hold_reason: 'Переговоры / Ручная пауза',
    });
    expect(options.onUpdated).toHaveBeenCalledWith(expect.objectContaining({ is_on_hold: true }));
  });
});
