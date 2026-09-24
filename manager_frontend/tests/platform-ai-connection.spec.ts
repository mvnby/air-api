import { flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), remove: vi.fn(), models: vi.fn(), test: vi.fn() }));
vi.mock('../src/client', () => ({
  ManagerPlatformAiService: {
    getPlatformAiApiManagerPlatformAiGet: mocks.get,
    putPlatformAiApiManagerPlatformAiPut: mocks.put,
    deletePlatformAiApiManagerPlatformAiDelete: mocks.remove,
    getPlatformAiModelsApiManagerPlatformAiModelsGet: mocks.models,
    testPlatformAiApiManagerPlatformAiTestPost: mocks.test,
  },
}));

import PlatformAIConnectionPanel from '../src/features/settings/platform/panels/PlatformAIConnectionPanel.vue';
import { PLATFORM_SETTINGS_CONTEXT } from '../src/features/settings/platform/platform-settings-context';

const mountPanel = () => mount(PlatformAIConnectionPanel, {
  global: { provide: { [PLATFORM_SETTINGS_CONTEXT as symbol]: { activeSettingsTab: ref('aiConnection') } } },
});

describe('platform AI connection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.get.mockResolvedValue({ configured: true, enabled: false, selected_model: null });
    mocks.put.mockResolvedValue({ configured: true, enabled: false, selected_model: 'cheap-cn' });
    mocks.models.mockResolvedValue({ items: ['cheap-cn', 'other'] });
    mocks.test.mockResolvedValue({ ok: true, model: 'cheap-cn' });
  });

  it('keeps the saved key write-only and discovers IDs without capability claims', async () => {
    const wrapper = mountPanel();
    await flushPromises();
    expect(wrapper.text()).toContain('Ключ настроен');
    expect(wrapper.get('[data-testid="platform-ai-key"]').attributes('type')).toBe('password');
    await wrapper.get('button:nth-of-type(2)').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('cheap-cn');
    expect(wrapper.text()).toContain('не подтверждает поддержку');
    await wrapper.get('[data-testid="platform-ai-model"]').setValue('cheap-cn');
    await wrapper.get('button:nth-of-type(1)').trigger('click');
    await flushPromises();
    expect(mocks.put).toHaveBeenCalledWith({ key: null, selected_model: 'cheap-cn' });
    expect(wrapper.get('[data-testid="platform-ai-key"]').element).toHaveProperty('value', '');
  });

  it('uses a synthetic inference check and direct enable toggle', async () => {
    mocks.get.mockResolvedValue({ configured: true, enabled: false, selected_model: 'cheap-cn' });
    const wrapper = mountPanel();
    await flushPromises();
    await wrapper.findAll('button').find(button => button.text().includes('Проверить текстовый запрос'))!.trigger('click');
    await flushPromises();
    expect(mocks.test).toHaveBeenCalledOnce();
    await wrapper.findAll('button').find(button => button.text() === 'Включить')!.trigger('click');
    expect(mocks.put).toHaveBeenCalledWith({ enabled: true });
  });
});
