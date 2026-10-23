import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { PersonalTask } from '../src/services/personal-tasks-api';

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  get: vi.fn(),
  assignees: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  changeStatus: vi.fn(),
}));

vi.mock('../src/services/personal-tasks-api', async (original) => ({
  ...(await original<typeof import('../src/services/personal-tasks-api')>()),
  listPersonalTasks: mocks.list,
  getPersonalTask: mocks.get,
  listPersonalTaskAssignees: mocks.assignees,
  createPersonalTask: mocks.create,
  updatePersonalTask: mocks.update,
  changePersonalTaskStatus: mocks.changeStatus,
}));

import PersonalTasksView from '../src/views/PersonalTasksView.vue';
import PersonalTaskCard from '../src/components/tasks/PersonalTaskCard.vue';
import { OpenAPI } from '../src/client/core/OpenAPI';

const task = (status: PersonalTask['status'] = 'active'): PersonalTask => ({
  id: 7,
  text: 'Перезвонить клиенту',
  description: null,
  status,
  version: 4,
  author_staff_user_id: 11,
  author_name: 'Анна',
  assignee_staff_user_id: 11,
  assignee_name: 'Анна',
  due_at: null,
  reminder_at: null,
  reminder_due: false,
  lead_id: null,
  customer_id: null,
  order_id: null,
  equipment_id: null,
  completed_at: null,
  cancelled_at: null,
  created_at: '2026-10-06T08:00:00Z',
  updated_at: '2026-10-06T08:00:00Z',
});

const listResult = (items: PersonalTask[]) => ({
  items,
  total: items.length,
  limit: 100,
  offset: 0,
  filter: 'active' as const,
  due_reminder_count: 0,
});

const wrappers: VueWrapper[] = [];

const mountView = async (item: PersonalTask = task()) => {
  mocks.list.mockResolvedValue(listResult([item]));
  const wrapper = mount(PersonalTasksView);
  wrappers.push(wrapper);
  await flushPromises();
  return wrapper;
};

beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState({}, '', '/manager/tasks');
  mocks.assignees.mockResolvedValue({ items: [{ id: 11, display_name: 'Анна' }] });
  mocks.create.mockResolvedValue(task());
  mocks.update.mockResolvedValue(task());
  mocks.changeStatus.mockResolvedValue(task('completed'));
});

afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  vi.unstubAllGlobals();
});

describe('PersonalTasksView', () => {
  it('reaches the 101st task and resets pagination when filtering', async () => {
    const firstPage = Array.from({ length: 100 }, (_, index) => ({ ...task(), id: index + 1 }));
    mocks.list.mockResolvedValueOnce({ ...listResult(firstPage), total: 101 });
    const wrapper = mount(PersonalTasksView);
    wrappers.push(wrapper);
    await flushPromises();
    expect(wrapper.text()).toContain('1–100 из 101');
    mocks.list.mockResolvedValueOnce({ ...listResult([{ ...task(), id: 101, text: 'Последнее поручение' }]), total: 101, offset: 100 });
    await wrapper.get('[data-testid="tasks-next"]').trigger('click');
    await flushPromises();
    expect(mocks.list).toHaveBeenLastCalledWith('active', 100, 100);
    expect(wrapper.text()).toContain('Последнее поручение');
    expect(wrapper.text()).toContain('101–101 из 101');
    expect(wrapper.get('[data-testid="tasks-next"]').attributes('disabled')).toBeDefined();
    mocks.list.mockResolvedValueOnce(listResult([task('completed')]));
    await wrapper.findAll('button').find(button => button.text() === 'Завершённые')!.trigger('click');
    await flushPromises();
    expect(mocks.list).toHaveBeenLastCalledWith('completed', 100, 0);
    expect(wrapper.text()).toContain('1–1 из 1');
  });

  it('returns to a populated page after completing the final item on the last page', async () => {
    mocks.list.mockResolvedValueOnce({ ...listResult([task()]), total: 101 });
    const wrapper = mount(PersonalTasksView);
    wrappers.push(wrapper);
    await flushPromises();
    mocks.list.mockResolvedValueOnce({ ...listResult([task()]), total: 101, offset: 100 });
    await wrapper.get('[data-testid="tasks-next"]').trigger('click');
    await flushPromises();
    mocks.list.mockResolvedValueOnce({ ...listResult([]), total: 100, offset: 100 });
    mocks.list.mockResolvedValueOnce({ ...listResult([task()]), total: 100 });
    await wrapper.get('[data-testid="personal-task-toggle-7"]').trigger('click');
    await flushPromises();
    expect(mocks.list).toHaveBeenLastCalledWith('active', 100, 0);
    expect(wrapper.findComponent(PersonalTaskCard).exists()).toBe(true);
  });

  it('ignores an older response after switching filters and accepts filter links', async () => {
    window.history.replaceState({}, '', '/manager/tasks?filter=overdue');
    let resolveOld!: (value: ReturnType<typeof listResult>) => void;
    mocks.list.mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve; }));
    const wrapper = mount(PersonalTasksView);
    wrappers.push(wrapper);
    expect(mocks.list).toHaveBeenLastCalledWith('overdue', 100, 0);
    mocks.list.mockResolvedValueOnce(listResult([{ ...task('completed'), text: 'Завершено' }]));
    await wrapper.findAll('button').find(button => button.text() === 'Завершённые')!.trigger('click');
    await flushPromises();
    resolveOld(listResult([{ ...task(), text: 'Старый результат' }]));
    await flushPromises();
    expect(wrapper.text()).toContain('Завершено');
    expect(wrapper.text()).not.toContain('Старый результат');
    expect(window.location.search).toBe('?filter=completed');
  });

  it('opens a linked completed task directly even outside the active first page', async () => {
    window.history.replaceState({}, '', '/manager/tasks?taskId=91');
    mocks.get.mockResolvedValue({ ...task('completed'), id: 91, text: 'Уточнить адрес / созвониться перед выездом', lead_id: 8 });
    const wrapper = await mountView();
    expect(mocks.get).toHaveBeenCalledWith(91);
    expect(wrapper.get('[data-testid="linked-personal-task"]').text()).toContain('Уточнить адрес');
    expect(wrapper.get('[data-testid="linked-personal-task"]').text()).toContain('#91');
  });
  it('creates a text-only task from the compact form and refreshes the list', async () => {
    const wrapper = await mountView();

    await wrapper.get('[data-testid="personal-task-create-text"]').setValue('  Дослать КП  ');
    await wrapper.get('form').trigger('submit');
    await flushPromises();

    expect(mocks.create).toHaveBeenCalledWith({ text: 'Дослать КП' }, expect.any(String));
    expect(mocks.list).toHaveBeenCalledTimes(2);
    expect((wrapper.get('[data-testid="personal-task-create-text"]').element as HTMLInputElement).value).toBe('');
  });

  it.each([
    ['active', 'complete'],
    ['completed', 'reopen'],
    ['cancelled', 'reopen'],
  ] as const)('uses a direct click to %s -> %s with the visible version', async (status, action) => {
    const wrapper = await mountView(task(status));

    await wrapper.get('[data-testid="personal-task-toggle-7"]').trigger('click');
    await flushPromises();

    expect(mocks.changeStatus).toHaveBeenCalledWith(7, action, 4, expect.any(String));
  });

  it('keeps an optimistic version conflict visible after refreshing stale data', async () => {
    mocks.changeStatus.mockRejectedValueOnce({
      status: 409,
      body: { detail: { code: 'personal_task_version_conflict', message: 'Поручение уже изменилось' } },
    });
    const wrapper = await mountView();

    await wrapper.get('[data-testid="personal-task-toggle-7"]').trigger('click');
    await flushPromises();

    expect(mocks.list).toHaveBeenCalledTimes(2);
    expect(wrapper.get('[role="alert"]').text()).toContain('Поручение уже изменилось');
  });

  it('retries an unchanged create after a lost response with the same payload and key', async () => {
    mocks.create.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    const wrapper = await mountView();
    await wrapper.get('[data-testid="personal-task-create-text"]').setValue('Дослать КП');
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('Failed to fetch');
    await wrapper.get('form').trigger('submit');
    await flushPromises();

    expect(mocks.create).toHaveBeenCalledTimes(2);
    expect(mocks.create.mock.calls[1]).toEqual(mocks.create.mock.calls[0]);
    expect(mocks.list).toHaveBeenCalledTimes(2);
  });

  it('creates a new command after the user changes the draft, even when changing it back', async () => {
    mocks.create.mockRejectedValueOnce(new TypeError('timeout'));
    const wrapper = await mountView();
    const input = wrapper.get('[data-testid="personal-task-create-text"]');
    await input.setValue('Дослать КП');
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    await input.setValue('Позвонить');
    await input.setValue('Дослать КП');
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(mocks.create.mock.calls[1][0]).toEqual(mocks.create.mock.calls[0][0]);
    expect(mocks.create.mock.calls[1][1]).not.toEqual(mocks.create.mock.calls[0][1]);
  });

  it('rotates the command key after a definitive validation rejection', async () => {
    mocks.create.mockRejectedValueOnce({ status: 422, body: { detail: 'Проверьте данные' } });
    const wrapper = await mountView();
    await wrapper.get('[data-testid="personal-task-create-text"]').setValue('Дослать КП');
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(mocks.create.mock.calls[1][1]).not.toEqual(mocks.create.mock.calls[0][1]);
  });

  it('keeps a pending status command and version across an uncertain retry', async () => {
    mocks.changeStatus.mockRejectedValueOnce({ status: 504, message: 'timeout' });
    const wrapper = await mountView();
    await wrapper.get('[data-testid="personal-task-toggle-7"]').trigger('click');
    await flushPromises();
    expect(mocks.list).toHaveBeenCalledTimes(1);
    await wrapper.get('[data-testid="personal-task-toggle-7"]').trigger('click');
    await flushPromises();
    expect(mocks.changeStatus.mock.calls[1]).toEqual(mocks.changeStatus.mock.calls[0]);
  });

  it('preserves an edit retry and rotates its key when the payload changes', async () => {
    mocks.update.mockRejectedValueOnce(new TypeError('timeout')).mockRejectedValueOnce(new TypeError('timeout'));
    const wrapper = await mountView();
    const payload = { expected_version: 4, text: 'Дослать КП' };
    wrapper.getComponent(PersonalTaskCard).vm.$emit('save', task(), payload);
    await flushPromises();
    wrapper.getComponent(PersonalTaskCard).vm.$emit('save', task(), { ...payload });
    await flushPromises();
    expect(mocks.update.mock.calls[1]).toEqual(mocks.update.mock.calls[0]);
    wrapper.getComponent(PersonalTaskCard).vm.$emit('save', task(), { ...payload, text: 'Позвонить' });
    await flushPromises();
    expect(mocks.update.mock.calls[2][2]).not.toEqual(mocks.update.mock.calls[0][2]);
  });

  it('sends task commands through the shared client with its selected storefront and credentials', async () => {
    const actual = await vi.importActual<typeof import('../src/services/personal-tasks-api')>('../src/services/personal-tasks-api');
    const previous = { ...OpenAPI };
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(task()), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetch);
    OpenAPI.HEADERS = async () => ({ 'X-MVN-Manager-Storefront': 'minsk' });
    OpenAPI.WITH_CREDENTIALS = true;
    OpenAPI.CREDENTIALS = 'include';
    try {
      await actual.createPersonalTask({ text: 'Дослать КП' }, 'intended-task-command');
      const [url, options] = fetch.mock.calls[0];
      expect(url).toBe('/api/manager/personal-tasks');
      expect(options.headers.get('X-MVN-Manager-Storefront')).toBe('minsk');
      expect(options.headers.get('Idempotency-Key')).toBe('intended-task-command');
      expect(options.credentials).toBe('include');
      expect(JSON.parse(options.body)).toEqual({ text: 'Дослать КП' });
    } finally {
      Object.assign(OpenAPI, previous);
    }
  });
});
