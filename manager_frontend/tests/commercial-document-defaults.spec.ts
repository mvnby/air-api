import { effectScope, ref } from 'vue';
import { flushPromises } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManagerDocumentSystemService } from '../src/client';
import { commercialTermsApi } from '../src/services/commercial-terms-api';
import { useManagedDocumentWorkspace } from '../src/features/documents/composables/use-managed-document-workspace';

vi.mock('../src/services/commercial-terms-api', async (original) => ({
  ...await original<typeof import('../src/services/commercial-terms-api')>(),
  commercialTermsApi: { defaults: vi.fn() },
}));
const deferred = () => {
  let resolve!: (value: Awaited<ReturnType<typeof commercialTermsApi.defaults>>) => void;
  const promise = new Promise<Awaited<ReturnType<typeof commercialTermsApi.defaults>>>((done) => { resolve = done; });
  return { promise, resolve };
};
const accepted = { order_id: 42, revision: 1, business_terms: { payment_schedule: [{ share_percent: 100, due_event: 'after_work' as const, due_days: 50, due_day_kind: 'working' as const, note: null }] } };
const scopes: ReturnType<typeof effectScope>[] = [];
const create = () => {
  const scope = effectScope(); scopes.push(scope);
  const proposal = ref<number | null>(7);
  const workspace = scope.run(() => useManagedDocumentWorkspace({orderId:() => 42, workflowType:() => 'service_work', proposalId:() => proposal.value, proposalTotalCents:() => 10000, notify:vi.fn(), refresh:vi.fn()}))!;
  return { workspace, proposal };
};
beforeEach(() => {
  vi.mocked(commercialTermsApi.defaults).mockReset();
  vi.spyOn(ManagerDocumentSystemService, 'listManagerDocumentLegalEntities').mockResolvedValue({items:[]});
  vi.spyOn(ManagerDocumentSystemService, 'getManagerDocumentPdfRuntime').mockResolvedValue({available:true} as never);
  vi.spyOn(ManagerDocumentSystemService, 'listManagerManagedOrderDocuments').mockResolvedValue({items:[]} as never);
});
afterEach(() => { scopes.splice(0).forEach((scope) => scope.stop()); vi.restoreAllMocks(); });

describe('commercial document defaults integration', () => {
  it('preserves manual edits made before a repeated workspace load', async () => {
    vi.mocked(commercialTermsApi.defaults).mockResolvedValue(accepted);
    const {workspace} = create();
    await workspace.loadWorkspace(); await flushPromises();
    workspace.businessTerms.value.payment_schedule = [{...workspace.businessTerms.value.payment_schedule[0]!, due_days: 12}];
    await workspace.loadWorkspace(); await flushPromises();
    expect(workspace.businessTerms.value.payment_schedule[0]?.due_days).toBe(12);
  });
  it('rejects a response for the previous proposal', async () => {
    const old = deferred(); const next = deferred();
    vi.mocked(commercialTermsApi.defaults).mockReturnValueOnce(old.promise as never).mockReturnValueOnce(next.promise as never);
    const {workspace, proposal} = create();
    await workspace.loadWorkspace();
    proposal.value = 8;
    old.resolve(accepted); await flushPromises();
    expect(workspace.businessTerms.value.payment_schedule[0]?.due_days).toBeNull();
    next.resolve({...accepted, business_terms:{payment_schedule:[{...accepted.business_terms.payment_schedule[0]!,due_days:20}]}});
    await flushPromises();
    expect(workspace.businessTerms.value.payment_schedule[0]?.due_days).toBe(20);
  });
  it('invalidates pending defaults after a form reset or replacement', async () => {
    const old = deferred(); vi.mocked(commercialTermsApi.defaults).mockReturnValue(old.promise as never);
    const {workspace} = create();
    await workspace.loadWorkspace();
    workspace.resetBusinessTerms();
    workspace.replacesDocumentId.value = 91;
    old.resolve(accepted); await flushPromises();
    expect(workspace.businessTerms.value.payment_schedule[0]?.due_days).toBeNull();
  });
  it('invalidates pending defaults on document type change', async () => {
    const old = deferred(); vi.mocked(commercialTermsApi.defaults).mockReturnValue(old.promise as never);
    const {workspace} = create();
    await workspace.loadWorkspace();
    workspace.documentType.value = 'b2c_supply_installation_contract';
    old.resolve(accepted); await flushPromises();
    expect(workspace.businessTerms.value.payment_schedule[0]?.due_days).toBeNull();
  });
});
