import { ref } from 'vue';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ManagerOrdersService, type ManagerOrderDetailResponse } from '../src/client';
import { useOrderSourceCommand } from '../src/composables/useOrderSourceCommand';

const setup = () => {
  const order = ref({ id: 461 } as ManagerOrderDetailResponse);
  const open = ref(true);
  const proposalId = ref<number | null>(465);
  const otherCommandBusy = ref(false);
  const flush = vi.fn().mockResolvedValue(true);
  const clearDraft = vi.fn();
  const onUpdated = vi.fn();
  return { order, open, proposalId, otherCommandBusy, flush, clearDraft, onUpdated };
};
afterEach(() => vi.restoreAllMocks());

describe('source command and order autosave', () => {
  it('flushes pending edits once and hydrates the command result before releasing the editor', async () => {
    const options = setup();
    let finishSave!: (saved: boolean) => void;
    options.flush.mockImplementation(() => new Promise((resolve) => { finishSave = resolve; }));
    const command = useOrderSourceCommand(options);
    const first = command.before();
    expect(command.busy.value).toBe(false);
    expect(await command.before()).toBe(false);
    finishSave(true);
    expect(await first).toBe(true);
    expect(command.busy.value).toBe(true);

    const fresh = { id: 461, product_lines: [{ id: 50 }] } as ManagerOrderDetailResponse;
    vi.spyOn(ManagerOrdersService, 'getManagerOrderDetail').mockResolvedValue(fresh);
    expect(await command.after()).toBe(true);
    expect(options.onUpdated).toHaveBeenCalledWith(fresh);
    expect(options.clearDraft).toHaveBeenCalledOnce();
    expect(command.busy.value).toBe(true);
    command.end();
    expect(command.busy.value).toBe(false);
  });

  it('keeps the local draft when save fails', async () => {
    const options = setup();
    options.flush.mockResolvedValue(false);
    const command = useOrderSourceCommand(options);
    expect(await command.before()).toBe(false);
    expect(command.busy.value).toBe(false);
    expect(options.clearDraft).not.toHaveBeenCalled();
  });

  it('ignores a late result after opening another proposal', async () => {
    const options = setup();
    const command = useOrderSourceCommand(options);
    expect(await command.before()).toBe(true);
    let finishRead!: (order: ManagerOrderDetailResponse) => void;
    vi.spyOn(ManagerOrdersService, 'getManagerOrderDetail').mockImplementation(() => new Promise((resolve) => { finishRead = resolve; }));
    const refresh = command.after();
    options.proposalId.value = 466;
    finishRead({ id: 461 } as ManagerOrderDetailResponse);
    expect(await refresh).toBe(false);
    expect(options.onUpdated).not.toHaveBeenCalled();
    expect(options.clearDraft).not.toHaveBeenCalled();
    command.end();
  });
});
