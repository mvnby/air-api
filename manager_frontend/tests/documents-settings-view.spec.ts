import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManagerDocumentSystemService } from '../src/client';
import DocumentsSettingsView from '../src/views/DocumentsSettingsView.vue';

const NOW = '2026-09-18T00:00:00Z';
const wrappers: VueWrapper[] = [];

beforeEach(() => {
  vi.spyOn(ManagerDocumentSystemService, 'listManagerDocumentLegalEntities').mockResolvedValue({
    items: [{
      id: 5,
      tenant_id: 1,
      slug: 'mvn',
      display_name: 'ООО МВН',
      legal_name: 'ООО МВН',
      unp: '123456789',
      entity_type: 'organization',
      is_vat_payer: false,
      is_default: true,
      requisites: {},
      status: 'active',
      created_at: NOW,
      updated_at: NOW,
    }],
  });
  vi.spyOn(ManagerDocumentSystemService, 'listManagerDocumentNumberPolicies').mockResolvedValue({ items: [] });
  vi.spyOn(ManagerDocumentSystemService, 'getManagerDocumentPdfRuntime').mockResolvedValue({
    available: true,
    provider: 'gotenberg',
    detail: 'ready',
  });
});

afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount());
  vi.restoreAllMocks();
  window.history.replaceState({}, '', '/');
});

describe('DocumentsSettingsView', () => {
  it('selects the issuer from an audit deep link before opening its panel', async () => {
    const entities = await ManagerDocumentSystemService.listManagerDocumentLegalEntities();
    vi.mocked(ManagerDocumentSystemService.listManagerDocumentLegalEntities).mockResolvedValue({
      items: [...entities.items, { ...entities.items[0]!, id: 6, display_name: 'ИП Тестовый' }],
    });
    window.history.replaceState({}, '', '/manager/settings/documents?legalEntityId=6&auditReportId=99');
    const wrapper = mount(DocumentsSettingsView, {
      global: {
        stubs: {
          NativeTemplateLibrary: true,
          TemplateAuditPanel: { props: ['legalEntityId'], template: '<section data-testid="audit-panel-issuer">{{ legalEntityId }}</section>' },
          DocumentNumberPoliciesPanel: true,
          DocumentLegalEntitiesPanel: true,
        },
      },
    });
    wrappers.push(wrapper);
    await flushPromises();
    expect(wrapper.get('[data-testid="audit-panel-issuer"]').text()).toBe('6');
    expect(ManagerDocumentSystemService.listManagerDocumentNumberPolicies).toHaveBeenLastCalledWith(6);
  });

  it('opens the compact template library first and keeps requisites draft while switching tabs', async () => {
    const wrapper = mount(DocumentsSettingsView, {
      global: {
        stubs: {
          NativeTemplateLibrary: { template: '<section data-testid="template-library">Библиотека шаблонов</section>' },
          TemplateAuditPanel: { template: '<section>Проверка шаблонов</section>' },
          DocumentNumberPoliciesPanel: { template: '<section>Нумерация</section>' },
        },
      },
    });
    wrappers.push(wrapper);
    await flushPromises();

    const templatesTab = wrapper.get('#documents-settings-tab-templates');
    expect(templatesTab.attributes('aria-selected')).toBe('true');
    expect(wrapper.get('[data-testid="template-library"]').isVisible()).toBe(true);

    await templatesTab.trigger('keydown', { key: 'ArrowRight' });
    await flushPromises();
    expect(wrapper.get('#documents-settings-tab-requisites').attributes('aria-selected')).toBe('true');

    const legalName = wrapper.get<HTMLInputElement>('[data-testid="seller-legal-name"]');
    await legalName.setValue('ООО МВН Монтаж');
    await wrapper.get('#documents-settings-tab-templates').trigger('click');
    await wrapper.get('#documents-settings-tab-requisites').trigger('click');

    expect(wrapper.get<HTMLInputElement>('[data-testid="seller-legal-name"]').element.value).toBe('ООО МВН Монтаж');
  });
});
