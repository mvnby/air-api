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
  const documentsWorkspaceRef = ref({ openNative: vi.fn() });
  const equipmentPanelRef = ref({ collapse: vi.fn(), expand: vi.fn() });
  const expandedSections = ref(sections());
  const navigation = useOrderWorkspaceNavigation({
    status: ref(status),
    workflowType: ref('sales_installation'),
    expandedSections,
    equipmentPanelRef,
    documentsWorkspaceRef,
  });
  return { navigation, expandedSections, documentsWorkspaceRef };
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

  it('opens CRM documents from the proposal without launching an email', async () => {
    const { navigation, documentsWorkspaceRef } = createNavigation();
    await navigation.openWorkspaceTarget('documents');
    expect(navigation.activeWorkspaceSection.value).toBe('documents');
    expect(documentsWorkspaceRef.value.openNative).toHaveBeenCalledOnce();
  });

  it('opens the execution payment workspace from the focused payments tab', () => {
    const { navigation } = createNavigation('execution');

    navigation.selectWorkspaceSection('payments');

    expect(navigation.activeWorkspaceSection.value).toBe('payments');
    expect(navigation.executionWorkspaceOpen.value).toBe(true);
  });
});
