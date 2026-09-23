import { mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ManagerDocumentSystemService } from '../src/client';
import AdditionalConditionsPanel from '../src/features/documents/components/AdditionalConditionsPanel.vue';
import { createDefaultBusinessDocumentTerms } from '../src/features/documents/model/business-document-terms';

afterEach(() => vi.restoreAllMocks());

describe('AdditionalConditionsPanel', () => {
  it('shows inherited order text and saves a custom clause for future documents', async () => {
    vi.spyOn(ManagerDocumentSystemService, 'listManagerDocumentConditionPresets').mockResolvedValue({ items: [] });
    const create = vi.spyOn(ManagerDocumentSystemService, 'createManagerDocumentConditionPreset')
      .mockResolvedValue({ id: 8, text: 'Леса оплачиваются отдельно.' });
    const wrapper = mount(AdditionalConditionsPanel, {
      props: { terms: createDefaultBusinessDocumentTerms(), orderConditions: 'Оборудование предоставит клиент.' },
    });
    await vi.waitFor(() => expect(wrapper.get('[data-testid="order-conditions-preview"]').text())
      .toContain('Оборудование предоставит клиент.'));

    await wrapper.get('[data-testid="additional-conditions-source-toggle"]').findAll('button')[1]!.trigger('click');
    await wrapper.setProps({ terms: { ...createDefaultBusinessDocumentTerms(), additional_conditions_overridden: true } });
    await wrapper.get('textarea').setValue('Леса оплачиваются отдельно.');
    await wrapper.setProps({ terms: { ...createDefaultBusinessDocumentTerms(), additional_conditions_overridden: true, additional_conditions: 'Леса оплачиваются отдельно.' } });
    await wrapper.get('[data-testid="save-condition-preset"]').trigger('click');
    await vi.waitFor(() => expect(create).toHaveBeenCalledWith({ text: 'Леса оплачиваются отдельно.' }));
    expect(wrapper.text()).toContain('Условие сохранено для будущих документов.');
    wrapper.unmount();
  });
});
