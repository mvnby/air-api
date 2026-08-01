import { mount } from '@vue/test-utils';
import { ref } from 'vue';
import { describe, expect, it, vi } from 'vitest';
import OrderProposalWorkspace from '../src/components/orders/OrderProposalWorkspace.vue';

const sectionStub = {
  name: 'OrderDrawerSection',
  template: '<section><slot /></section>',
};

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
    await wrapper.findAll('button').find((button) => button.text().includes('Создать копию'))?.trigger('click');
    await wrapper.findAll('button').find((button) => button.text().includes('В черновик'))?.trigger('click');

    expect(duplicateProposal).toHaveBeenCalledOnce();
    expect(changeActiveProposalStatus).toHaveBeenCalledWith('draft');
  });
});
