import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import LeadSourceReviewModal from '../src/components/leads/LeadSourceReviewModal.vue';

const sourceApi = vi.hoisted(() => ({ preview: vi.fn(), apply: vi.fn(), analyze: vi.fn() }));
const scenariosApi = vi.hoisted(() => ({ getManagerOrderScenarios: vi.fn() }));
vi.mock('../src/services/order-source-review', () => ({ orderSourceReviewApi: sourceApi }));
vi.mock('../src/api', () => ({ api: scenariosApi }));

const preview = {
  order_id: 41,
  source_code: 'belzakupki', external_id: 'T-12', source_url: 'https://example.test/tender', title: 'Поставка',
  customer: { name: 'ООО Заказчик', inn: '123456789', type: 'company', email: 'office@example.test' },
  existing_customer_id: null, work_summary: 'Обслуживание кондиционеров', equipment_details: '2 блока',
  current_scenario: { workflow_type: 'sales_installation', service_type: 'turnkey', label: 'Продажа + монтаж' },
  suggested_scenario: { workflow_type: 'maintenance', service_type: 'maintenance', label: 'Обслуживание' },
  objects: [{ address: 'Минск, Ленина, 1', equipment: [{ brand: 'Daikin', model: 'A1', quantity: 2 }] }],
  field_sources: { 'customer.name': 'Карточка закупки', 'customer.inn': 'Текст документа', 'objects.0.address': 'Текст документа', 'objects.0.equipment.0': 'Текст документа' },
  documents: [{ id: 'doc-1', name: 'ТЗ.pdf', download_url: '/api/manager/orders/41/source-documents/doc-1', extracted_text: 'Техническое задание' }],
  warnings: [],
};

describe('LeadSourceReviewModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sourceApi.preview.mockResolvedValue(preview);
    sourceApi.apply.mockResolvedValue({ order_id: 41, customer_id: 9, attachment_ids: [1], applied_fields: ['customer'] });
    sourceApi.analyze.mockRejectedValue(new Error('AI unavailable'));
    scenariosApi.getManagerOrderScenarios.mockResolvedValue({ items: [
      { workflow_type: 'sales_installation', service_type: 'turnkey', label: 'Продажа + монтаж' },
      { workflow_type: 'maintenance', service_type: 'maintenance', label: 'Обслуживание' },
      { workflow_type: 'service_work', service_type: null, label: 'Работы' },
    ] });
  });

  it('requires explicit confirmation and sends reviewed data without a price', async () => {
    const wrapper = mount(LeadSourceReviewModal, { props: { open: true, orderId: 41, leadStatus: 'new_lead' } });
    await flushPromises();
    expect(wrapper.text()).toContain('ТЗ.pdf');
    expect(wrapper.get<HTMLSelectElement>('select[aria-label="Сценарий заказа"]').element.value).toBe('maintenance:maintenance');
    expect(wrapper.find('input[placeholder*="Цен"]').exists()).toBe(false);
    expect(wrapper.get('button.btn-mini').attributes('disabled')).toBeDefined();

    await wrapper.findAll('input[type="checkbox"]').at(-1)!.setValue(true);
    await wrapper.get('button.btn-mini').trigger('click');

    expect(sourceApi.apply).toHaveBeenCalledWith(41, expect.objectContaining({
      customer_action: 'create', workflow_type: 'maintenance', service_type: 'maintenance',
      document_ids: ['doc-1'], objects: [{ address: 'Минск, Ленина, 1', equipment: [{ brand: 'Daikin', model: 'A1', quantity: 2 }] }],
    }));
    expect(wrapper.emitted('applied')?.[0]?.[0]).toEqual(expect.objectContaining({ orderId: 41, customerId: 9 }));
  });

  it('does not offer skip for a new lead', async () => {
    const wrapper = mount(LeadSourceReviewModal, { props: { open: true, orderId: 41, leadStatus: 'new_lead' } });
    await flushPromises();
    expect(wrapper.text()).not.toContain('Не менять клиента');
  });

  it('switches the suggestion after AI identifies maintenance and keeps a manual choice', async () => {
    sourceApi.preview.mockResolvedValueOnce({
      ...preview,
      suggested_scenario: preview.current_scenario,
    });
    sourceApi.analyze.mockResolvedValue({
      ...preview, work_summary: 'Техническое обслуживание кондиционеров', analysis_source: 'ai',
    });
    const wrapper = mount(LeadSourceReviewModal, { props: { open: true, orderId: 41, leadStatus: 'new_lead' } });
    await flushPromises();
    const select = wrapper.get<HTMLSelectElement>('select[aria-label="Сценарий заказа"]');
    expect(select.element.value).toBe('sales_installation:turnkey');
    await wrapper.findAll('button').find((button) => button.text() === 'Обработать ИИ')!.trigger('click');
    await flushPromises();
    expect(select.element.value).toBe('maintenance:maintenance');
    await wrapper.findAll('input[type="checkbox"]').at(-1)!.setValue(true);
    await wrapper.get('button.btn-mini').trigger('click');
    expect(sourceApi.apply).toHaveBeenCalledWith(41, expect.objectContaining({
      workflow_type: 'maintenance', service_type: 'maintenance',
    }));

    await select.setValue('service_work:');
    await wrapper.findAll('button').find((button) => button.text() === 'Обработать ИИ')!.trigger('click');
    await flushPromises();
    expect(select.element.value).toBe('service_work:');
  });

  it('keeps the current scenario when reviewing an existing order', async () => {
    const wrapper = mount(LeadSourceReviewModal, { props: { open: true, orderId: 41, leadStatus: 'negotiation' } });
    await flushPromises();
    expect(wrapper.get<HTMLSelectElement>('select[aria-label="Сценарий заказа"]').element.value)
      .toBe('sales_installation:turnkey');
    expect(wrapper.text()).toContain('По смыслу работ предложено: Обслуживание');
  });

  it('requires a scenario if the source and AI cannot identify one', async () => {
    sourceApi.preview.mockResolvedValueOnce({ ...preview, suggested_scenario: null });
    const wrapper = mount(LeadSourceReviewModal, { props: { open: true, orderId: 41, leadStatus: 'new_lead' } });
    await flushPromises();
    expect(wrapper.get<HTMLSelectElement>('select[aria-label="Сценарий заказа"]').element.value).toBe('');
    await wrapper.findAll('input[type="checkbox"]').at(-1)!.setValue(true);
    expect(wrapper.get('button.btn-mini').attributes('disabled')).toBeDefined();
  });

  it('keeps the source document visible if scenario options cannot load', async () => {
    scenariosApi.getManagerOrderScenarios.mockRejectedValueOnce(new Error('unavailable'));
    const wrapper = mount(LeadSourceReviewModal, { props: { open: true, orderId: 41, leadStatus: 'new_lead' } });
    await flushPromises();
    expect(wrapper.text()).toContain('ТЗ.pdf');
    expect(wrapper.text()).toContain('Не удалось загрузить сценарии заказов');
    expect(wrapper.get('button.btn-mini').attributes('disabled')).toBeDefined();
  });

  it('lets the manager correct equipment and add a missed site before applying', async () => {
    const wrapper = mount(LeadSourceReviewModal, { props: { open: true, orderId: 41, leadStatus: 'new_lead' } });
    await flushPromises();
    expect(wrapper.text()).toContain('УНП · Текст документа');
    await wrapper.get('input[aria-label="Количество объекта 1, строка 1"]').setValue('6');
    await wrapper.findAll('button').find((button) => button.text() === 'Добавить объект')!.trigger('click');
    await wrapper.get('input[aria-label="Адрес объекта 2"]').setValue('Шумилино, Короткина, 10');
    await wrapper.findAll('button').filter((button) => button.text() === 'Добавить оборудование').at(-1)!.trigger('click');
    await wrapper.get('input[aria-label="Бренд объекта 2, строка 1"]').setValue('General Climate');
    await wrapper.get('input[aria-label="Модель объекта 2, строка 1"]').setValue('A2');
    await wrapper.get('input[aria-label="Количество объекта 2, строка 1"]').setValue('2');
    await wrapper.findAll('input[type="checkbox"]').at(-1)!.setValue(true);
    await wrapper.get('button.btn-mini').trigger('click');
    expect(sourceApi.apply).toHaveBeenCalledWith(41, expect.objectContaining({
      objects: [
        { address: 'Минск, Ленина, 1', equipment: [{ brand: 'Daikin', model: 'A1', quantity: 6 }] },
        { address: 'Шумилино, Короткина, 10', equipment: [{ brand: 'General Climate', model: 'A2', quantity: 2 }] },
      ],
    }));
  });

  it('keeps the review visible when document analysis fails', async () => {
    const wrapper = mount(LeadSourceReviewModal, { props: { open: true, orderId: 41, leadStatus: 'new_lead' } });
    await flushPromises();
    await wrapper.findAll('button').find((button) => button.text() === 'Обработать ИИ')!.trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('AI unavailable');
    expect(wrapper.text()).toContain('ТЗ.pdf');
    expect(wrapper.find('input[placeholder="Название или имя"]').exists()).toBe(true);
  });

  it('explains exact prefill only for sales and forwards added lines and warnings', async () => {
    const equipmentPrefill = {
      proposal_id: 5,
      added: [{ model: 'A1', quantity: 2, product_id: 7, message: 'A1 × 2: добавлено в черновик.' }],
      skipped: [{ model: 'A2', reason: 'insufficient_stock', message: 'A2: требуется 2, доступно 1.' }],
      warnings: ['A2: требуется 2, доступно 1.'],
    };
    sourceApi.apply.mockResolvedValueOnce({ order_id: 41, customer_id: 9, attachment_ids: [], applied_fields: ['proposal_equipment'], equipment_prefill: equipmentPrefill });
    const wrapper = mount(LeadSourceReviewModal, { props: { open: true, orderId: 41, leadStatus: 'negotiation' } });
    await flushPromises();
    expect(wrapper.text()).toContain('единственным точным совпадением и достаточным наличием');
    expect(wrapper.text()).toContain('Монтаж добавляется отдельно');
    await wrapper.findAll('input[type="checkbox"]').at(-1)!.setValue(true);
    await wrapper.get('button.btn-mini').trigger('click');
    await flushPromises();
    expect(wrapper.emitted('applied')?.[0]?.[0]).toEqual(expect.objectContaining({ equipmentPrefill }));
    await wrapper.get('select[aria-label="Сценарий заказа"]').setValue('maintenance:maintenance');
    expect(wrapper.text()).not.toContain('единственным точным совпадением и достаточным наличием');
  });

  it('shows saved pending equipment when the source review is reopened', async () => {
    sourceApi.preview.mockResolvedValueOnce({ ...preview, equipment_prefill: {
      proposal_id: 5, added: [],
      skipped: [{ model: 'A2', reason: 'insufficient_stock', message: 'A2: требуется 2, доступно 1; уточните поставку.' }],
      warnings: ['A2: требуется 2, доступно 1; уточните поставку.', 'A1: закупочная стоимость неизвестна.'],
    } });
    const wrapper = mount(LeadSourceReviewModal, { props: { open: true, orderId: 41 } });
    await flushPromises();
    expect(wrapper.get('[aria-label="Результат переноса оборудования"]').text())
      .toContain('A2: требуется 2, доступно 1; уточните поставку.');
    expect(wrapper.get('[aria-label="Результат переноса оборудования"]').text())
      .toContain('A1: закупочная стоимость неизвестна.');
  });
});
