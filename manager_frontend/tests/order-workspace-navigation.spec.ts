import { ref } from 'vue';
import { describe, expect, it, vi } from 'vitest';
import { useOrderWorkspaceNavigation } from '../src/composables/useOrderWorkspaceNavigation';

const sections = () => ({
  website: false,
  clientDetails: false,
  planningDetails: false,
  repair: true,
  proposals: false,
  documents: false,
  payments: false,
  execution: false,
});

const createNavigation = (status = 'negotiation') => {
  const documentsWorkspaceRef = ref({ openSend: vi.fn(), openCreate: vi.fn() });
  const equipmentPanelRef = ref({ collapse: vi.fn(), expand: vi.fn() });
  const setToast = vi.fn();
  const expandedSections = ref(sections());
  const navigation = useOrderWorkspaceNavigation({
    status: ref(status),
    workflowType: ref('sales_installation'),
    expandedSections,
    equipmentPanelRef,
    documentsWorkspaceRef,
    setToast,
  });
  return { navigation, expandedSections, documentsWorkspaceRef, setToast };
};

describe('useOrderWorkspaceNavigation', () => {
  it('opens one sales workspace target and supports direct toggle close', async () => {
    const { navigation, expandedSections } = createNavigation();

    await navigation.openWorkspaceTarget('proposal', true);
    expect(navigation.activeWorkspaceTarget.value).toBe('proposal');
    expect(expandedSections.value.proposals).toBe(true);

    await navigation.openWorkspaceTarget('proposal', true);
    expect(navigation.activeWorkspaceTarget.value).toBeNull();
  });

  it('routes proposal sending to create or send based on an existing offer', async () => {
    const { navigation, documentsWorkspaceRef, setToast } = createNavigation();
    const proposal = { id: 17 } as any;

    await navigation.openProposalSend(proposal, []);
    expect(documentsWorkspaceRef.value.openCreate).toHaveBeenCalledOnce();
    expect(setToast).toHaveBeenCalledWith(
      'Сначала создайте коммерческое предложение для активного варианта',
      'error',
    );

    await navigation.openProposalSend(proposal, [{ doc_type: 'offer', proposal_id: 17 }] as any);
    expect(documentsWorkspaceRef.value.openSend).toHaveBeenCalledOnce();
  });
});
