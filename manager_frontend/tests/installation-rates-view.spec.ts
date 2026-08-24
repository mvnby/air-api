import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  listRates: vi.fn(),
  updateRate: vi.fn(),
}));

vi.mock('../src/api', () => ({
  api: {
    listManagerInstallationRates: mocks.listRates,
    updateManagerInstallationRate: mocks.updateRate,
  },
}));

import InstallationRateEditModal from '../src/components/InstallationRateEditModal.vue';
import InstallationRatesView from '../src/views/InstallationRatesView.vue';

const wallRate = {
  id: 1,
  category: 'Wall',
  power_range: 'area-20, area-25, area-35',
  base_price: 600,
  extra_pipe_price: 50,
  included_pipe_meters: 3,
  is_fixed: true,
  comment: null,
  title: 'Монтаж настенной сплит-системы',
  equipment_label: 'Настенная сплит-система',
  power_label: '2–4 кВт',
  selection_status: 'automatic_fixed' as const,
  selection_note: 'Безопасный автоматический расчёт.',
};

const ductRate = {
  id: 5,
  category: 'Duct',
  power_range: 'All',
  base_price: 1500,
  extra_pipe_price: 85,
  included_pipe_meters: 3,
  is_fixed: false,
  comment: 'После осмотра',
  title: 'Монтаж канального кондиционера',
  equipment_label: 'Канальный кондиционер',
  power_label: 'Любая мощность',
  selection_status: 'matched_manual_quote' as const,
  selection_note: 'Тариф распознаётся по форм-фактору, цену подтвердит менеджер.',
};

const unsupportedRate = {
  id: 7,
  category: 'Multisplit',
  power_range: 'All',
  base_price: 500,
  extra_pipe_price: 60,
  included_pipe_meters: 3,
  is_fixed: false,
  comment: null,
  title: 'Монтаж мульти-сплит-системы',
  equipment_label: 'Мульти-сплит-система',
  power_label: 'Любая мощность',
  selection_status: 'unsupported' as const,
  selection_note: 'Эта категория не участвует в автоматическом подборе.',
};

describe('public installation rates manager UX', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.listRates.mockResolvedValue({ items: [wallRate, ductRate, unsupportedRate] });
    mocks.updateRate.mockResolvedValue(ductRate);
  });

  it('shows a readable product-to-rate mapping and separates checkout modes', async () => {
    const wrapper = mount(InstallationRatesView, {
      global: { stubs: { teleport: true } },
    });
    await flushPromises();

    const text = wrapper.text();
    expect(text).toContain('Карточка товара');
    expect(text).toContain('Канальный кондиционер');
    expect(text).toContain('Монтаж канального кондиционера');
    expect(text).toContain('от 1500 BYN');
    expect(text).toContain('Подбирается, цену уточнит менеджер');
    expect(text).toContain('Не участвует в автоподборе');
    expect(text).toContain('Не подключено к публичному подбору');
    expect(text).toContain('600 BYN');
    expect(wrapper.findAll('button[title="Изменить цену"]')).toHaveLength(2);
  });

  it('edits only public price fields while keeping resolver keys read-only', async () => {
    const wrapper = mount(InstallationRateEditModal, {
      props: { modelValue: true, rate: ductRate },
      global: { stubs: { teleport: true } },
    });

    const inputs = wrapper.findAll('input[type="number"]');
    await inputs[0]!.setValue(1550);
    await inputs[1]!.setValue(4);
    await inputs[2]!.setValue(90);
    await wrapper.find('textarea').setValue('Точная цена после осмотра');
    const saveButton = wrapper.findAll('button').find((button) => button.text().includes('Сохранить цену'));
    expect(saveButton).toBeDefined();
    await saveButton!.trigger('click');
    await flushPromises();

    expect(mocks.updateRate).toHaveBeenCalledWith(5, {
      base_price: 1550,
      extra_pipe_price: 90,
      included_pipe_meters: 4,
      comment: 'Точная цена после осмотра',
    });
    expect(wrapper.text()).toContain('Форм-фактор, диапазон мощности и режим расчёта здесь защищены');
    expect(wrapper.find('input[value="Duct"]').exists()).toBe(false);
  });
});
