import { ref } from 'vue';
import type { OrderWorkspaceSection } from '../src/components/orders/OrderWorkspaceNav.vue';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useOrderWorkspaceNavigation } from '../src/composables/useOrderWorkspaceNavigation';
import { startManagerNavigation } from '../src/services/manager-navigation-history';
import { normalizeOrderLocation } from '../src/services/order-navigation';
import { registerUnsavedNavigationGuard } from '../src/services/unsaved-navigation-guard';

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

const createNavigation = (status = 'negotiation', page = false, orderId = 477, ensureSection?: (section: OrderWorkspaceSection) => Promise<void>) => {
  const documentsWorkspaceRef = ref({ openNative: vi.fn() });
  const equipmentPanelRef = ref({ collapse: vi.fn(), expand: vi.fn() });
  const expandedSections = ref(sections());
  const navigation = useOrderWorkspaceNavigation({
    status: ref(status),
    syncLocation: ref(page),
    orderId: ref(orderId),
    ensureSection,
    workflowType: ref('sales_installation'),
    expandedSections,
    equipmentPanelRef,
    documentsWorkspaceRef,
  });
  return { navigation, expandedSections, documentsWorkspaceRef };
};

afterEach(() => { window.history.replaceState({}, '', '/manager/orders'); vi.restoreAllMocks(); });

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


describe('order page workspace location', () => {
  it.each(['proposal', 'documents', 'work', 'payments'] as const)('restores %s on direct entry, reset and reload', section => {
    window.history.replaceState({}, '', `/manager/orders/477?section=${section}&proposalId=25`);
    const first = createNavigation('execution', true);
    expect(first.navigation.activeWorkspaceSection.value).toBe(section);
    first.navigation.resetWorkspaceNavigation();
    expect(first.navigation.activeWorkspaceSection.value).toBe(section);
    const reloaded = createNavigation('execution', true);
    expect(reloaded.navigation.activeWorkspaceSection.value).toBe(section);
    if (section === 'documents') expect(first.expandedSections.value.documents).toBe(true);
    if (section === 'payments') expect(first.navigation.executionWorkspaceOpen.value).toBe(true);
  });

  it.each(['', '?section=unknown', '?section=work&section=payments'])('defaults missing or invalid sections to proposal: %s', search => {
    window.history.replaceState({}, '', `/manager/orders/477${search}`);
    expect(createNavigation('negotiation', true).navigation.activeWorkspaceSection.value).toBe('proposal');
  });

  it('replaces only section while preserving proposal, tenant, return URL, history and without invoking the leave guard', () => {
    const query = new URLSearchParams({ section: 'proposal', proposalId: '25', company: '42', site: 'minsk', returnTo: '/manager/orders/list?search=office' });
    window.history.replaceState({ orderOrigin: { id: 'board' } }, '', `/manager/orders/477?${query}`);
    const accepted = vi.fn();
    const stop = startManagerNavigation(accepted, normalizeOrderLocation);
    const guard = vi.fn(() => false);
    const unregister = registerUnsavedNavigationGuard(guard);
    try {
      const { navigation } = createNavigation('negotiation', true);
      const state = window.history.state;
      const length = window.history.length;
      navigation.selectWorkspaceSection('documents');
      navigation.selectWorkspaceSection('work');
      const actual = new URLSearchParams(window.location.search);
      expect(actual.get('section')).toBe('work');
      for (const key of ['proposalId', 'company', 'site', 'returnTo']) expect(actual.get(key)).toBe(query.get(key));
      expect(window.history.state).toEqual(state);
      expect(window.history.length).toBe(length);
      expect(accepted).not.toHaveBeenCalled();
      expect(guard).not.toHaveBeenCalled();
    } finally { unregister(); stop(); }
  });

  it('keeps drawer and mismatched order navigation local', () => {
    window.history.replaceState({}, '', '/manager/orders/477?section=documents');
    for (const navigation of [createNavigation('negotiation').navigation, createNavigation('negotiation', true, 478).navigation]) {
      expect(navigation.activeWorkspaceSection.value).toBe('proposal');
      navigation.selectWorkspaceSection('payments');
      expect(new URLSearchParams(window.location.search).get('section')).toBe('documents');
    }
  });
});


describe('async workspace targets', () => {
  it('waits for the requested section before calling its component handle', async () => {
    let ready!: () => void;
    const ensureSection = vi.fn(() => new Promise<void>(resolve => { ready = resolve; }));
    const { navigation, documentsWorkspaceRef } = createNavigation('negotiation', false, 477, ensureSection);
    const opened = navigation.openWorkspaceTarget('documents');
    expect(ensureSection).toHaveBeenCalledExactlyOnceWith('documents');
    expect(documentsWorkspaceRef.value.openNative).not.toHaveBeenCalled();
    ready();
    await opened;
    expect(documentsWorkspaceRef.value.openNative).toHaveBeenCalledOnce();
  });
});
