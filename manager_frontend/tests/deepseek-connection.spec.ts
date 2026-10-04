import { flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), remove: vi.fn(), importKey: vi.fn(), test: vi.fn(), confirm: vi.fn() }));
vi.mock('../src/services/ui-feedback', () => ({ confirmDialog: mocks.confirm }));
vi.mock('../src/client', () => ({
  ManagerPlatformAiService: {
    getDeepseekConnection: mocks.get,
    putDeepseekConnection: mocks.put,
    deleteDeepseekConnection: mocks.remove,
    importDeepseekEnvironmentKey: mocks.importKey,
    testDeepseekConnection: mocks.test,
  },
}));

import DeepSeekConnectionPanel from '../src/features/settings/platform/panels/DeepSeekConnectionPanel.vue';
import { PLATFORM_SETTINGS_CONTEXT } from '../src/features/settings/platform/platform-settings-context';

const mountPanel = () => mount(DeepSeekConnectionPanel, {
  global: { provide: { [PLATFORM_SETTINGS_CONTEXT as symbol]: { activeSettingsTab: ref('aiConnection') } } },
});
const status = (overrides: Record<string, unknown> = {}) => ({
  configured: true,
  enabled: false,
  source: 'settings',
  environment_key_available: false,
  ...overrides,
});

describe('DeepSeek connection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.get.mockResolvedValue(status());
    mocks.put.mockResolvedValue(status());
    mocks.remove.mockResolvedValue(status({ configured: false }));
    mocks.importKey.mockResolvedValue(status());
    mocks.test.mockResolvedValue({ ok: true });
  });

  it('keeps the key write-only and clears the field after save', async () => {
    const wrapper = mountPanel();
    await flushPromises();
    const input = wrapper.get('[data-testid="deepseek-key"]');
    expect(input.attributes('type')).toBe('password');
    await input.setValue('secret-key');
    await wrapper.findAll('button').find(button => button.text() === 'Сохранить ключ')!.trigger('click');
    await flushPromises();
    expect(mocks.put).toHaveBeenCalledWith({ key: 'secret-key' });
    expect(wrapper.get('[data-testid="deepseek-key"]').element).toHaveProperty('value', '');
    expect(wrapper.text()).not.toContain('secret-key');
  });

  it('sends null for an empty key, imports the environment key without exposing it, and toggles directly', async () => {
    mocks.get.mockResolvedValue(status({ configured: false, source: 'environment', environment_key_available: true }));
    const wrapper = mountPanel();
    await flushPromises();
    const save = wrapper.findAll('button').find(button => button.text() === 'Сохранить ключ')!;
    expect(save.attributes('disabled')).toBeDefined();
    await wrapper.findAll('button').find(button => button.text() === 'Перенести текущий ключ')!.trigger('click');
    await flushPromises();
    expect(mocks.importKey).toHaveBeenCalledWith();
    expect(wrapper.text()).not.toContain('secret-key');
    const toggle = wrapper.findAll('button').find(button => button.text() === 'Включить')!;
    await toggle.trigger('click');
    expect(mocks.put).toHaveBeenCalledWith({ enabled: true });
  });

  it('preserves the configured key when saving an empty field', async () => {
    const wrapper = mountPanel();
    await flushPromises();
    await wrapper.findAll('button').find(button => button.text() === 'Сохранить ключ')!.trigger('click');
    await flushPromises();
    expect(mocks.put).toHaveBeenCalledWith({ key: null });
  });

  it('requires shared confirmation before deleting and describes that it disables the connection', async () => {
    const wrapper = mountPanel();
    await flushPromises();
    const remove = wrapper.findAll('button').find(button => button.text() === 'Удалить ключ')!;
    mocks.confirm.mockResolvedValueOnce(false);
    await remove.trigger('click');
    await flushPromises();
    expect(mocks.confirm).toHaveBeenCalledWith(expect.objectContaining({ description: expect.stringContaining('подключение отключено') }));
    expect(mocks.remove).not.toHaveBeenCalled();
    mocks.confirm.mockResolvedValueOnce(true);
    mocks.remove.mockResolvedValueOnce(status({ configured: false, environment_key_available: true }));
    await remove.trigger('click');
    await flushPromises();
    expect(mocks.remove).toHaveBeenCalledOnce();
    expect(wrapper.findAll('button').some(button => button.text() === 'Перенести текущий ключ')).toBe(true);
    expect(mocks.importKey).not.toHaveBeenCalled();
  });

  it('blocks duplicate actions while a request is pending', async () => {
    let resolveRequest!: (value: unknown) => void;
    mocks.put.mockReturnValueOnce(new Promise(resolve => { resolveRequest = resolve; }));
    const wrapper = mountPanel();
    await flushPromises();
    const toggle = wrapper.findAll('button').find(button => button.text() === 'Включить')!;
    await toggle.trigger('click');
    expect(toggle.attributes('disabled')).toBeDefined();
    await toggle.trigger('click');
    expect(mocks.put).toHaveBeenCalledTimes(1);
    resolveRequest(status({ enabled: true }));
    await flushPromises();
  });
});
