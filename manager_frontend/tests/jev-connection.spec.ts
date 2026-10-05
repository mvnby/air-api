import { flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), remove: vi.fn(), test: vi.fn(), report: vi.fn(), confirm: vi.fn() }));
vi.mock('../src/services/ui-feedback', () => ({ confirmDialog: mocks.confirm }));
vi.mock('../src/client', () => ({
  ManagerPlatformAiService: {
    getJevConnection: mocks.get,
    putJevConnection: mocks.put,
    deleteJevConnection: mocks.remove,
    testJevConnection: mocks.test,
    getJevShadowReport: mocks.report,
  },
}));

import JevConnectionPanel from '../src/features/settings/platform/panels/JevConnectionPanel.vue';
import { PLATFORM_SETTINGS_CONTEXT } from '../src/features/settings/platform/platform-settings-context';

const mountPanel = () => mount(JevConnectionPanel, {
  global: { provide: { [PLATFORM_SETTINGS_CONTEXT as symbol]: { activeSettingsTab: ref('aiConnection') } } },
});
const connection = (overrides: Record<string, unknown> = {}) => ({
  configured: true,
  enabled: false,
  model: '1.13.0',
  daily_budget_usd: 0.05,
  max_daily_requests: 20,
  ...overrides,
});
const report = (items: unknown[] = [], overrides: Record<string, unknown> = {}) => ({
  queued: 0,
  running: 0,
  completed: 1,
  failed: 0,
  comparable: 0,
  agreements: 0,
  disagreements: 0,
  estimated_usd: 0.001,
  input_tokens: 30,
  median_duration_ms: null,
  items,
  ...overrides,
});

describe('Jev shadow connection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.get.mockResolvedValue(connection());
    mocks.put.mockImplementation(async (payload: Record<string, unknown>) => connection({ enabled: payload.enabled ?? false, daily_budget_usd: payload.daily_budget_usd ?? 0.05 }));
    mocks.remove.mockResolvedValue(connection({ configured: false }));
    mocks.test.mockResolvedValue({ ok: true, model: '1.13.0' });
    mocks.report.mockResolvedValue(report());
  });

  it('keeps the key write-only, saves the default budget, and clears the key field', async () => {
    const wrapper = mountPanel();
    await flushPromises();
    expect(wrapper.text()).toContain('Лимит по умолчанию — $0.05');
    const input = wrapper.get('[data-testid="jev-key"]');
    expect(input.attributes('type')).toBe('password');
    await input.setValue('jev-secret');
    await wrapper.get('[data-testid="jev-save"]').trigger('click');
    await flushPromises();
    expect(mocks.put).toHaveBeenCalledWith({ key: 'jev-secret', daily_budget_usd: 0.05 });
    expect(wrapper.get('[data-testid="jev-key"]').element).toHaveProperty('value', '');
    expect(wrapper.text()).not.toContain('jev-secret');
  });

  it('toggles directly, requires shared deletion confirmation, and discloses paid test requests', async () => {
    const wrapper = mountPanel();
    await flushPromises();
    await wrapper.get('[data-testid="jev-toggle"]').trigger('click');
    expect(mocks.put).toHaveBeenCalledWith({ enabled: true });
    expect(wrapper.text()).toContain('отправляет платный запрос');
    mocks.confirm.mockResolvedValueOnce(false);
    await wrapper.get('[data-testid="jev-remove"]').trigger('click');
    await flushPromises();
    expect(mocks.confirm).toHaveBeenCalledOnce();
    expect(mocks.remove).not.toHaveBeenCalled();
    mocks.confirm.mockResolvedValueOnce(true);
    await wrapper.get('[data-testid="jev-remove"]').trigger('click');
    await flushPromises();
    expect(mocks.remove).toHaveBeenCalledOnce();
  });

  it('shows report counts and nullable outcomes without calling agreements accuracy', async () => {
    mocks.report.mockResolvedValue(report([{
      id: 7,
      source: 'email',
      subject: 'Request title',
      state: 'Original request details',
      created_at: '2026-10-05T10:00:00Z',
      status: 'completed',
      primary_provider: 'deepseek',
      primary_model_requested: null,
      primary_is_relevant: null,
      primary_duration_ms: null,
      model: '1.13.0',
      kind: null,
      kind_confidence: null,
      hvac_probability: null,
      jev_is_relevant: false,
      duration_ms: null,
      estimated_usd: null,
      error_code: null,
    }], { disagreements: 1, comparable: 2 }));
    const wrapper = mountPanel();
    await flushPromises();
    expect(mocks.report).toHaveBeenCalledWith(undefined, false, 20);
    expect(wrapper.text()).toContain('1 / 2 сравнимых');
    expect(wrapper.text()).toContain('— / Нет');
    expect(wrapper.text()).toContain('Original request details');
    expect(wrapper.text()).toContain('Jev: 1.13.0');
    expect(wrapper.text().toLowerCase()).not.toContain('точность');
    await wrapper.get('[data-testid="jev-disagreements-toggle"]').trigger('click');
    await flushPromises();
    expect(mocks.report).toHaveBeenLastCalledWith(undefined, true, 20);
  });

  it('retains report rows when refresh fails and renders missing measurements safely', async () => {
    mocks.report.mockResolvedValueOnce(report([{
      id: 8,
      source: 'belzakupki',
      subject: 'Tender',
      state: 'Tender source text',
      created_at: '2026-10-05T10:00:00Z',
      status: 'failed',
      primary_provider: 'deepseek',
      primary_model_requested: null,
      primary_is_relevant: null,
      primary_duration_ms: null,
      model: null,
      kind: null,
      kind_confidence: null,
      hvac_probability: null,
      jev_is_relevant: null,
      duration_ms: null,
      estimated_usd: null,
      error_code: 'timeout',
    }]));
    const wrapper = mountPanel();
    await flushPromises();
    expect(wrapper.text()).toContain('Tender');
    expect(wrapper.text()).toContain('Ошибка · Истекло время ожидания');
    expect(wrapper.text()).toContain('— / —');
    mocks.report.mockRejectedValueOnce(new Error('private provider failure'));
    await wrapper.get('[data-testid="jev-report-refresh"]').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('Tender');
    expect(wrapper.text()).toContain('Не удалось загрузить отчёт теневых проверок.');
    expect(wrapper.text()).not.toContain('private provider failure');
  });
});
