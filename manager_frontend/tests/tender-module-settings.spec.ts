import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import TenderModuleSettingsPanel from '../src/features/tenders/TenderModuleSettingsPanel.vue';

const api = vi.hoisted(() => ({ get: vi.fn(), update: vi.fn(), preview: vi.fn() }));
vi.mock('../src/services/tender-module', () => ({ tenderModuleApi: api }));

describe('TenderModuleSettingsPanel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows company activation separately from platform access', async () => {
    api.get.mockResolvedValue({ entitled: false, enabled: false, version: 0, profiles: [] });
    const wrapper = mount(TenderModuleSettingsPanel);
    await flushPromises();
    expect(wrapper.find('[role="switch"]').exists()).toBe(false);
    expect(wrapper.text()).toContain('Право на подключение выдаёт владелец платформы');
    expect(api.update).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('enables the broad initial profile and previews saved work combinations', async () => {
    const first = { entitled: true, enabled: false, version: 1, profiles: [] };
    const active = { ...first, enabled: true, version: 2, profiles: [{
      name: 'Поставка с монтажом', mode: 'strict', activity_combinations: [['supply', 'installation']],
      excluded_directions: ['ventilation'],
    }] };
    api.get.mockResolvedValue(first);
    api.update.mockResolvedValue(active);
    api.preview.mockResolvedValue({ items: [{
      order_id: 658, title: 'Закупка сплит-систем',
      result: { state: 'review', reason: 'unconfirmed_activity' },
    }] });
    const wrapper = mount(TenderModuleSettingsPanel);
    await flushPromises();
    await wrapper.get<HTMLInputElement>('[role="switch"]').setValue(true);
    await flushPromises();
    expect(api.update).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({
      enabled: true, version: 1, profiles: [expect.objectContaining({ name: 'Все HVAC', mode: 'broad' })],
    }));
    await wrapper.findAll('button').find((button) => button.text() === 'Проверить на полученных закупках')!.trigger('click');
    await flushPromises();
    expect(api.preview).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({
      activity_combinations: [['supply', 'installation']], excluded_directions: ['ventilation'], mode: 'strict',
    }));
    expect(wrapper.get('[aria-label="Предпросмотр профиля"]').text()).toContain('Нужно уточнить виды работ');
    wrapper.unmount();
  });
});
