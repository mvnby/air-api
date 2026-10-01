import { mount } from '@vue/test-utils';
import { defineComponent, h, ref } from 'vue';
import { describe, expect, it, vi } from 'vitest';
import OrderProposalWorkspace from '../src/components/orders/OrderProposalWorkspace.vue';
import OrderProductLinesEditor from '../src/components/orders/OrderProductLinesEditor.vue';

const sectionStub = {
  name: 'OrderDrawerSection',
  template: '<section><slot /></section>',
};

const toolbarStub = {
  name: 'OrderProposalToolbar',
  template: '<div><slot name="controls" /></div>',
};

const serviceCatalogStub = {
  name: 'OrderServiceCatalogPicker',
  emits: ['close'],
  template: '<div data-testid="service-catalog-picker-stub"><button type="button" @click="$emit(\'close\')">Закрыть каталог-заглушку</button></div>',
};

const installationPanelStub = (addStandard: ReturnType<typeof vi.fn>) => defineComponent({
  name: 'OrderInstallationEstimatePanel',
  setup(_, { expose }) {
    expose({ addStandard });
    return () => h('div', { 'data-testid': 'installation-panel-stub' });
  },
});

const createWorkspaceFixture = (options: {
  productLines?: unknown[];
  serviceLines?: unknown[];
  locked?: boolean;
  orderId?: number | null;
} = {}) => {
  const commercial = {
    productLines: ref(options.productLines ?? []),
    serviceLines: ref(options.serviceLines ?? []),
    searchInStock: ref(false),
    editingServiceLineIndex: ref<number | null>(null),
    showEstimateImport: ref(false),
    selectedEstimateId: ref<number | null>(null),
    estimateSearchQuery: ref(''),
    estimateImportMode: ref('detailed'),
    serviceDescriptionMode: ref('short'),
    productOptions: ref([]),
    productLookupById: ref({}),
    productLookupLoading: ref(false),
    activeSuggestionIndex: ref<number | null>(null),
    supplyActionLoadingLineId: ref<number | null>(null),
    serviceTariffOptions: ref([]),
    serviceTariffLookupLoading: ref(false),
    activeServiceSuggestionIndex: ref<number | null>(null),
    estimateOptions: ref([]),
    estimateOptionsLoading: ref(false),
    importingEstimate: ref(false),
    total: ref(0),
    supplyBadgeForLine: vi.fn(),
    addProductLine: vi.fn(),
    addServiceLine: vi.fn(),
    addServiceTariff: vi.fn(),
    addCreatedEstimate: vi.fn(),
    applyEstimateToServices: vi.fn(),
    loadEstimateOptions: vi.fn(),
    toggleEstimateImport: vi.fn(),
    setServiceLineDescriptionMode: vi.fn(),
    onProductInputFocus: vi.fn(),
    onProductQueryInput: vi.fn(),
    onProductInputBlur: vi.fn(),
    selectProductForLine: vi.fn(),
    openSelectedProduct: vi.fn(),
    removeProductLine: vi.fn(),
    fillProductClientDescription: vi.fn(),
    createSupplyFromProductLine: vi.fn(),
    onServiceTitleFocus: vi.fn(),
    onServiceTitleInput: vi.fn(),
    onServiceTitleBlur: vi.fn(),
    selectServiceTariffForLine: vi.fn(),
    removeServiceLine: vi.fn(),
  } as any;
  const proposal = {
    activeProposalLineLabel: ref('Основной'),
    activeProposal: ref({ id: 17 }),
    activeProposalLocked: ref(Boolean(options.locked)),
    activeProposalStatus: ref(options.locked ? 'approved' : 'draft'),
    proposals: ref([]),
    proposalActionLoading: ref(false),
    duplicateProposal: vi.fn(),
    changeActiveProposalStatus: vi.fn(),
    onProposalClick: vi.fn(),
    selectProposalForOrder: vi.fn(),
    createProposal: vi.fn(),
    renameProposal: vi.fn(),
    archiveProposal: vi.fn(),
  } as any;
  const props = {
    commercial,
    proposal,
    expanded: true,
    title: 'Предложения',
    orderTitle: 'Система охлаждения',
    customerName: 'Иван Петров',
    objectAddress: 'Минск, ул. Летняя, 8',
    showProductLines: true,
    formatServiceKind: (kind?: string | null) => kind || '',
    workflow: 'sales_installation',
    orderId: options.orderId === undefined ? 801 : options.orderId,
    beforeInstallationAction: vi.fn().mockResolvedValue(true),
    beforeMultiSplitSave: vi.fn().mockResolvedValue(true),
    beginInstallationAttach: vi.fn().mockResolvedValue(true),
    afterInstallationAttach: vi.fn().mockResolvedValue(true),
    endInstallationAttach: vi.fn(),
  } as any;
  return { commercial, proposal, props };
};

const sharedStubs = (addStandard: ReturnType<typeof vi.fn>) => ({
  OrderDrawerSection: sectionStub,
  OrderProposalToolbar: toolbarStub,
  OrderInstallationEstimatePanel: installationPanelStub(addStandard),
  OrderServiceCatalogPicker: serviceCatalogStub,
  OrderMultiSplitConfigurator: true,
});

describe('OrderProposalWorkspace', () => {
  it('keeps locked-revision actions inside the proposal workspace', async () => {
    const duplicateProposal = vi.fn();
    const changeActiveProposalStatus = vi.fn();
    const proposal = {
      activeProposalLineLabel: ref('Основной · принят'),
      activeProposal: ref({ id: 17 }),
      activeProposalLocked: ref(true),
      activeProposalStatus: ref('approved'),
      proposals: ref([]),
      proposalActionLoading: ref(false),
      duplicateProposal,
      changeActiveProposalStatus,
      onProposalClick: vi.fn(),
      selectProposalForOrder: vi.fn(),
      createProposal: vi.fn(),
      renameProposal: vi.fn(),
      archiveProposal: vi.fn(),
    } as any;
    const commercial = {
      productLines: ref([]),
      serviceLines: ref([]),
      searchInStock: ref(false),
      editingServiceLineIndex: ref(null),
      showEstimateImport: ref(false),
      selectedEstimateId: ref(null),
      estimateSearchQuery: ref(''),
      estimateImportMode: ref('detailed'),
      serviceDescriptionMode: ref('short'),
      productOptions: ref([]),
      productLookupById: ref({}),
      productLookupLoading: ref(false),
      activeSuggestionIndex: ref(null),
      supplyActionLoadingLineId: ref(null),
      serviceTariffOptions: ref([]),
      serviceTariffLookupLoading: ref(false),
      activeServiceSuggestionIndex: ref(null),
      estimateOptions: ref([]),
      estimateOptionsLoading: ref(false),
      importingEstimate: ref(false),
      total: ref(550),
      supplyBadgeForLine: vi.fn(),
    } as any;
    const wrapper = mount(OrderProposalWorkspace, {
      props: {
        commercial,
        proposal,
        expanded: true,
        title: 'Предложения',
        showProductLines: true,
        formatServiceKind: (kind?: string | null) => kind || '',
        workflow: 'sales_installation',
        orderId: null,
        beforeInstallationAction: vi.fn().mockResolvedValue(true),
        beforeMultiSplitSave: vi.fn().mockResolvedValue(true),
        beginInstallationAttach: vi.fn().mockResolvedValue(true),
        afterInstallationAttach: vi.fn().mockResolvedValue(true),
        endInstallationAttach: vi.fn(),
      },
      global: {
        stubs: {
          OrderDrawerSection: sectionStub,
          OrderProposalToolbar: true,
          OrderProductLinesEditor: true,
          OrderServiceLinesEditor: true,
        },
      },
    });

    expect(wrapper.text()).toContain('принята клиентом');
    expect(wrapper.get('fieldset').element.disabled).toBe(true);
    expect((wrapper.get('[data-testid="add-product-line"]').element as HTMLButtonElement).matches(':disabled')).toBe(true);
    await wrapper.get('[data-testid="proposal-to-documents"]').trigger('click');
    expect(wrapper.emitted('documents')).toEqual([[]]);
    await wrapper.findAll('button').find((button) => button.text().includes('Создать копию'))?.trigger('click');
    await wrapper.findAll('button').find((button) => button.text().includes('В черновик'))?.trigger('click');

    expect(duplicateProposal).toHaveBeenCalledOnce();
    expect(changeActiveProposalStatus).toHaveBeenCalledWith('draft');

    commercial.serviceLines.value = [{ title: 'Монтаж', quantity: 1, price: 500, cost: 0,
      installation_estimate_revision_id: 21 }];
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain('новый пустой черновик');
    expect(wrapper.text()).not.toContain('Создать копию');
    await wrapper.findAll('button').find((button) => button.text().includes('Новый черновик'))?.trigger('click');
    expect(proposal.createProposal).toHaveBeenCalledOnce();
  });

  it('keeps the real product editor and its edits mounted while switching to the client preview', async () => {
    const productLine = {
      link_id: 301,
      product_id: 501,
      product_query: 'Кондиционер Nova',
      client_description: 'Исходное описание для клиента',
      quantity: 1,
      price: 1_200,
      cost: 777,
    };
    const serviceLine = {
      title: 'Монтаж по согласованному составу',
      description: 'Трасса до 3 м',
      quantity: 1,
      price: 500,
      cost: 250,
    };
    const fixture = createWorkspaceFixture({ productLines: [productLine], serviceLines: [serviceLine] });
    const wrapper = mount(OrderProposalWorkspace, {
      props: { ...fixture.props, showCosts: true },
      slots: {
        'source-equipment': '<div data-testid="source-equipment-only">Внутренний источник оборудования</div>',
      },
      global: { stubs: sharedStubs(vi.fn()) },
    });
    const editorBefore = wrapper.findComponent(OrderProductLinesEditor);

    await editorBefore.get('[aria-label="Редактировать товар #1"]').trigger('click');
    await editorBefore.get('input[type="number"]').setValue('1850');
    await editorBefore.get('[data-order-usage="order_product_description"]').setValue('Комплект и параметры согласованы с клиентом.');
    expect(productLine.price).toBe(1850);
    expect(productLine.client_description).toBe('Комплект и параметры согласованы с клиентом.');

    await wrapper.findAll('button').find((button) => button.text().includes('Предпросмотр для клиента'))?.trigger('click');

    const preview = wrapper.get('[data-testid="proposal-client-preview"]');
    const previewText = preview.text().replace(/\s/g, '');
    expect(preview.text()).toContain('Кондиционер Nova');
    expect(preview.text()).toContain('Комплект и параметры согласованы с клиентом.');
    expect(preview.text()).toContain('Монтаж по согласованному составу');
    expect(previewText).toContain('1850BYN');
    expect(previewText).not.toContain('777');
    expect(previewText).not.toContain('250');
    expect(preview.text()).not.toContain('Себест.');
    expect(preview.findAll('button, input, textarea')).toHaveLength(0);
    expect(wrapper.get('[data-testid="source-equipment-only"]').isVisible()).toBe(false);
    expect(wrapper.get('[data-testid="add-product-line"]').isVisible()).toBe(false);

    await wrapper.get('button[aria-pressed="true"]').trigger('click');
    const editorAfter = wrapper.findComponent(OrderProductLinesEditor);
    expect(wrapper.find('[data-testid="proposal-client-preview"]').exists()).toBe(false);
    expect(wrapper.get('#order-workspace-proposal > div.min-w-0').attributes('style') || '').not.toContain('display: none');
    expect(editorAfter.get('input[type="number"]').element).toHaveProperty('value', '1850');
    expect((editorAfter.get('[data-order-usage="order_product_description"]').element as HTMLTextAreaElement).value)
      .toBe('Комплект и параметры согласованы с клиентом.');
    expect(editorAfter.get('[aria-label="Готово: товар #1"]').exists()).toBe(true);
  });

  it('routes shared add actions through the real editors and the installation panel capability', async () => {
    const addStandard = vi.fn();
    const fixture = createWorkspaceFixture({
      productLines: [{ link_id: 88, product_id: 501, product_query: 'Nova', quantity: 1, price: 1_200, cost: 700 }],
    });
    const wrapper = mount(OrderProposalWorkspace, {
      props: fixture.props,
      global: { stubs: sharedStubs(addStandard) },
    });

    await wrapper.get('[data-testid="add-product-line"]').trigger('click');
    expect(fixture.commercial.addProductLine).toHaveBeenCalledOnce();

    await wrapper.get('[data-testid="add-service-line"]').trigger('click');
    expect(wrapper.get('[data-testid="service-catalog-picker-stub"]').isVisible()).toBe(true);
    await wrapper.get('[data-testid="service-catalog-picker-stub"] button').trigger('click');

    await wrapper.get('[data-testid="installation-standard-add"]').trigger('click');
    expect(addStandard).toHaveBeenCalledOnce();
    expect(wrapper.find('[data-testid="service-catalog-picker-stub"]').exists()).toBe(false);

    fixture.commercial.productLines.value = [];
    await wrapper.get('[data-testid="installation-standard-add"]').trigger('click');
    expect(addStandard).toHaveBeenCalledOnce();
    expect(wrapper.get('[data-testid="service-catalog-picker-stub"]').isVisible()).toBe(true);
  });
});
