import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { PersonalTask } from '../src/services/personal-tasks-api';

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  assignees: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  changeStatus: vi.fn(),
}));

vi.mock('../src/services/personal-tasks-api', async (original) => ({
  ...(await original<typeof import('../src/services/personal-tasks-api')>()),
  listPersonalTasks: mocks.list,
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
