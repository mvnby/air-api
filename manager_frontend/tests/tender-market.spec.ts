import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ManagerTenderModuleService } from '../src/client';
import { isManagerPathAllowed, MANAGER_CAPABILITY } from '../src/manager-capabilities';
import TenderMarketView from '../src/views/TenderMarketView.vue';

describe('Tender market', () => {
  afterEach(() => vi.restoreAllMocks());

  it('requires the selected company module for the Manager route', () => {
    expect(isManagerPathAllowed({ capabilities: [MANAGER_CAPABILITY.crmManage] }, '/manager/tenders')).toBe(false);
    expect(isManagerPathAllowed({ capabilities: [MANAGER_CAPABILITY.tenderMarket] }, '/manager/tenders')).toBe(true);
  });

  it('paginates the selected profile and starts a fresh scan when switching to review', async () => {
    const load = vi.spyOn(ManagerTenderModuleService, 'listManagerTenderMarket')
      .mockResolvedValueOnce({
        items: [{ id: 699, title: 'Перенос кондиционера', source: 'goszakupki_by',
          source_url: 'https://goszakupki.by/single-source/view/3876716', profiles: [] }],
        next_before_id: 699, settings_version: 2, profile_names: ['Все HVAC'],
      })
      .mockResolvedValue({ items: [], settings_version: 2, profile_names: ['Все HVAC'] });
    const page = mount(TenderMarketView);
    await flushPromises();
    expect(page.get('a').attributes('href')).toBe('https://goszakupki.by/single-source/view/3876716');
    await page.findAll('button').find((button) => button.text() === 'Следующие публикации')!.trigger('click');
    await flushPromises();
    expect(load).toHaveBeenNthCalledWith(2, 'match', undefined, 699, 2);
    await page.findAll('button').find((button) => button.text() === 'На проверке')!.trigger('click');
    await flushPromises();
    expect(load).toHaveBeenNthCalledWith(3, 'review', undefined, undefined, undefined);
    expect(page.text()).not.toContain('Перенос кондиционера');
    page.unmount();
  });
});
