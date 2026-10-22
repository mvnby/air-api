import { ref } from 'vue';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ManagerOrderDetailResponse } from '../src/client';
import { useOrderDrawerActions } from '../src/composables/useOrderDrawerActions';

const apiMock = vi.hoisted(() => ({ patchManagerOrder: vi.fn() }));
const ordersMock = vi.hoisted(() => ({ deleteManagerOrder: vi.fn() }));
const holdCommand = vi.hoisted(() => vi.fn());
vi.mock('../src/services/order-waiting', () => ({ orderWaitingApi: { command: holdCommand } }));
const confirmDialog = vi.hoisted(() => vi.fn());

vi.mock('../src/api', () => ({ api: apiMock }));
vi.mock('../src/client', () => ({ ManagerOrdersService: ordersMock }));
vi.mock('../src/services/ui-feedback', () => ({ confirmDialog }));

const order = ref({ id: 42, status: 'execution', workflow_revision: 3, is_on_hold: false } as ManagerOrderDetailResponse);

const createActions = (dirty = false, beforeClose?: () => Promise<boolean>) => {
  const options = {
    order,
    displayOrderTitle: ref('Монтаж в офисе'),
    hasUnsavedChanges: ref(dirty),
    localFormError: ref(''),
    persistDraft: vi.fn(),
    clearDraft: vi.fn(),
    setToast: vi.fn(),
    beforeClose,
    beforeHold: beforeClose,
    onBeforeClose: vi.fn(),
    onModelValue: vi.fn(),
    onUpdated: vi.fn(),
    onDeleted: vi.fn(),
  };
  return { actions: useOrderDrawerActions(options), options };
};

afterEach(() => vi.clearAllMocks());

describe('useOrderDrawerActions', () => {
  it('keeps the drawer open when autosave cannot finish', async () => {
    const { actions, options } = createActions(true, async () => false);
    await actions.closeDrawer();
    expect(options.onModelValue).not.toHaveBeenCalled();
    expect(options.clearDraft).not.toHaveBeenCalled();
    expect(confirmDialog).not.toHaveBeenCalled();
  });
  it('keeps the drawer open when the manager rejects discarding a dirty draft', async () => {
    confirmDialog.mockResolvedValue(false);
    const { actions, options } = createActions(true);

    await actions.closeDrawer();

    expect(options.persistDraft).toHaveBeenCalledOnce();
    expect(options.clearDraft).not.toHaveBeenCalled();
    expect(options.onModelValue).not.toHaveBeenCalled();
  });

  it('does not start waiting when the save barrier fails', async () => {
    const { actions, options } = createActions(true, async () => false);
    await actions.toggleHold();
    expect(holdCommand).not.toHaveBeenCalled();
    expect(actions.waiting.selected.value).toBeNull();
    expect(options.clearDraft).not.toHaveBeenCalled();
  });
  it('uses the current revision after the pending save completes', async () => {
    const { actions } = createActions(true, async () => { order.value = { ...order.value, workflow_revision: 9 }; return true; });
    await actions.toggleHold();
    await actions.waiting.submit({ reason_code: 'next_stage' });
    expect(holdCommand).toHaveBeenCalledWith(42, expect.objectContaining({ expected_revision: 9 }));
    order.value = { ...order.value, workflow_revision: 3 };
  });
  it('opens waiting without a command, then submits the selected reason and optional date', async () => {
    holdCommand.mockResolvedValue({ ...order.value, is_on_hold: true });
    const { actions, options } = createActions();
    await actions.toggleHold();
    expect(holdCommand).not.toHaveBeenCalled();
    expect(actions.waiting.selected.value?.id).toBe(42);
    await actions.waiting.submit({ reason_code: 'next_stage', note: 'Second visit', next_followup_date: null });
    expect(holdCommand).toHaveBeenCalledWith(42, { action: 'wait', expected_revision: 3,
      reason_code: 'next_stage', note: 'Second visit', next_followup_date: null });
    expect(options.onUpdated).toHaveBeenCalledWith(expect.objectContaining({ is_on_hold: true }));
  });
});
