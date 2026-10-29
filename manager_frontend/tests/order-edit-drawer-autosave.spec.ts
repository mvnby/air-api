import { commitLineEdit } from '../src/components/orders/order-line-drafts';
import { nextTick } from 'vue';
import { registerUnsavedNavigationGuard } from '../src/services/unsaved-navigation-guard';
import { startManagerNavigation } from '../src/services/manager-navigation-history';
import { shallowMount, flushPromises, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import OrderWaitingDialog from '../src/components/orders/OrderWaitingDialog.vue';
import { orderWaitingApi } from '../src/services/order-waiting';
import OrderWorkerAssignmentsPanel from '../src/components/orders/OrderWorkerAssignmentsPanel.vue';
import { orderWorkerAssignmentsApi } from '../src/services/order-worker-assignments';
import OrderResponsiblePanel from '../src/components/orders/OrderResponsiblePanel.vue';
import { orderResponsibilityApi } from '../src/services/order-responsibility';
import OrderEditDrawer from '../src/components/orders/OrderEditDrawer.vue';
import OrderCustomerContext from '../src/components/orders/OrderCustomerContext.vue';
import OrderProposalWorkspace from '../src/components/orders/OrderProposalWorkspace.vue';
import OrderDocumentsWorkspace from '../src/components/orders/OrderDocumentsWorkspace.vue';
import OrderPaymentsPanel from '../src/components/orders/OrderPaymentsPanel.vue';
import OrderPaymentWorkspace from '../src/components/orders/OrderPaymentWorkspace.vue';
import OrderWorkWorkspace from '../src/components/orders/OrderWorkWorkspace.vue';
import OrderDraftRecovery from '../src/components/orders/OrderDraftRecovery.vue';
import OrderWorkspaceHeader from '../src/components/orders/OrderWorkspaceHeader.vue';
import OrderWorkspaceNav from '../src/components/orders/OrderWorkspaceNav.vue';
import OrderRequestSourceCard from '../src/components/orders/OrderRequestSourceCard.vue';
import LeadSourceReviewModal from '../src/components/leads/LeadSourceReviewModal.vue';
import { ManagerOrdersService, ManagerMailService, ManagerSettingsService, ManagerDocumentSystemService, ManagerRepairComplaintsService } from '../src/client';
import { ManagerOrderUsageService, CancelablePromise } from '../src/client';
import { managerSession } from '../src/services/manager-session';
import { managerStorefrontSelection } from '../src/services/manager-storefront-selection';
import type { ManagerOrderDetailResponse } from '../src/client';

const apiMock = vi.hoisted(() => ({
  getManagerCustomerBranches: vi.fn(), getManagerInstallers: vi.fn(), listManagerServiceEstimates: vi.fn(), listSupplyRequests: vi.fn(),
}));
vi.mock('../src/api', () => ({ api: apiMock }));
vi.mock('../src/composables/useSmartStickyHeader', async () => {
  const { ref } = await import('vue');
  return { useSmartStickyHeader: () => ({ compact: ref(false), reset: vi.fn() }) };
});
vi.mock('../src/services/ui-feedback', () => ({ confirmDialog: vi.fn().mockResolvedValue(false), promptDialog: vi.fn() }));

const initialOrder = (): ManagerOrderDetailResponse => ({
  id: 395, title: 'Обслуживание', status: 'negotiation', workflow_type: 'maintenance',
  negotiation_status: 'awaiting_offer', execution_status: 'needs_schedule',
  created_at: '2026-09-10T08:00:00Z', is_paid: false,
  total_amount: 0, total_cost: 0, margin: 0, payments: [], documents: [],
  product_lines: [], service_lines: [],
  customer: { id: 12, name: 'Лаборатория', type: 'company' },
  proposals: [{ id: 25, name: 'Основное', status: 'draft', is_selected: true, is_archived: false,
    product_lines: [], service_lines: [], total_amount: 0 }],
} as ManagerOrderDetailResponse);
let wrapper: VueWrapper;
let stored: ManagerOrderDetailResponse;
const commit = (payload: any) => {
  stored = { ...stored, ...payload, delivery_address: payload.customer_delivery_address ?? stored.delivery_address };
  if (payload.services) { const index = Math.max(0, stored.proposals!.findIndex(item => item.id === payload.line_proposal_id)); stored.proposals![index] = { ...stored.proposals![index]!, service_lines: payload.services }; }
  return structuredClone(stored);
};
const mountDrawer = async (presentation: 'page' | 'dialog' = 'dialog', realCustomer = false, openContext = true, realHeader = false, realProposal = false) => {
  wrapper = shallowMount(OrderEditDrawer, {
    attachTo: realHeader ? document.body : undefined,
    props: { modelValue: false, presentation, order: stored, onUpdated: (order: ManagerOrderDetailResponse) => { void wrapper.setProps({ order }); } },
    global: { components: { OrderPaymentWorkspace, OrderWorkWorkspace }, stubs: { OrderWorkspaceHeader: !realHeader, OrderAsyncPanel: false, OrderPaymentWorkspace: false, OrderCustomerContext: !realCustomer, OrderWorkspaceContext: !realCustomer, OrderProposalWorkspace: !realProposal, OrderProposalToolbar: !realProposal, OrderProductLinesEditor: !realProposal, OrderServiceLinesEditor: !realProposal } },
  });
  await wrapper.setProps({ modelValue: true });
  await flushPromises();
  if (openContext) await openCustomerContext();
};
const openCustomerContext = async () => {
  const disclosure = wrapper.get('[aria-controls="order-context-details"]');
  if (disclosure.attributes('aria-expanded') !== 'true') await disclosure.trigger('click');
  await flushPromises();
};
const customer = () => wrapper.findComponent(OrderCustomerContext);
const header = () => wrapper.findComponent(OrderWorkspaceHeader);
const payments = () => wrapper.findComponent(OrderPaymentsPanel);
const openSection = async (section: 'proposal' | 'documents' | 'work' | 'payments') => {
  wrapper.findComponent(OrderWorkspaceNav).vm.$emit('select', section);
  await flushPromises();
};
const openDocuments = () => openSection('documents');

beforeEach(() => {
  vi.useFakeTimers();
  Object.values(apiMock).forEach((mock) => mock.mockResolvedValue({ items: [] }));
  localStorage.clear(); sessionStorage.clear();
  stored = initialOrder();
  vi.spyOn(ManagerMailService, 'listManagerOrderOutgoingEmails').mockResolvedValue({ items: [] } as any);
  vi.spyOn(ManagerDocumentSystemService, 'listManagerManagedOrderDocuments').mockResolvedValue({ items: [] });
  vi.spyOn(ManagerOrdersService, 'getManagerOrderDetail').mockImplementation(async () => structuredClone(stored));
  vi.spyOn(ManagerOrdersService, 'patchManagerOrder').mockImplementation(async (_id, payload) => commit(payload));
});
afterEach(() => { wrapper?.unmount(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); managerSession.auth.value = null; managerStorefrontSelection.selectedSlug.value = null; });

describe('unfinished line actions with the real proposal editors', () => {
  const editNewService = async () => {
    await mountDrawer('dialog', false, false, false, true);
    Object.assign(wrapper.get('[data-order-scroll]').element, { scrollTo: vi.fn() });
    const commercial = wrapper.findComponent(OrderProposalWorkspace).props('commercial') as any;
    commercial.addServiceLine();
    Object.assign(commercial.serviceLines.value[0], { title: 'Введённая услуга', price: 125.5 });
    await nextTick();
    return commercial.serviceLines.value[0];
  };
  it('warns when changing tabs and keeps the input visible and uncommitted on continue editing', async () => {
    const line = await editNewService();
    const { confirmDialog } = await import('../src/services/ui-feedback');
    vi.mocked(confirmDialog).mockResolvedValueOnce(false);
    await openDocuments();
    expect(confirmDialog).toHaveBeenCalledWith(expect.objectContaining({ confirmText: 'Применить и сохранить' }));
    expect(wrapper.findComponent(OrderWorkspaceNav).props('active')).toBe('proposal');
    expect(line.editor).toBeDefined(); expect(line.title).toBe('Введённая услуга');
    expect(header().props('pendingLineEdits')).toBe(true);
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
  });
  it.each([true, false])('applies and saves before switching tabs with autosave %s', async automatic => {
    const line = await editNewService();
    if (!automatic) { header().vm.$emit('toggle-autosave'); await nextTick(); }
    const { confirmDialog } = await import('../src/services/ui-feedback');
    vi.mocked(confirmDialog).mockResolvedValueOnce(true);
    await openDocuments();
    expect(wrapper.findComponent(OrderWorkspaceNav).props('active')).toBe('documents');
    expect(line.editor).toBeUndefined();
    expect(stored.proposals![0].service_lines).toEqual(expect.arrayContaining([expect.objectContaining({ title: 'Введённая услуга', price: 125.5 })]));
    expect(header().props('pendingLineEdits')).toBe(false);
  });
  it('explicit Save applies the open row instead of reporting success while omitting it', async () => {
    const line = await editNewService();
    const { confirmDialog } = await import('../src/services/ui-feedback');
    vi.mocked(confirmDialog).mockClear();
    header().vm.$emit('save'); await flushPromises();
    expect(line.editor).toBeUndefined(); expect(confirmDialog).not.toHaveBeenCalled();
    expect(stored.proposals![0].service_lines).toEqual(expect.arrayContaining([expect.objectContaining({ title: 'Введённая услуга', price: 125.5 })]));
    expect(header().props('pendingLineEdits')).toBe(false);
  });
  it('keeps the editor on declined preview, then includes the accepted row in the preview', async () => {
    const line = await editNewService();
    const { confirmDialog } = await import('../src/services/ui-feedback');
    const workspace = wrapper.findComponent(OrderProposalWorkspace);
    const previewButton = () => workspace.findAll('button').find(button => button.text() === 'Предпросмотр для клиента')!;
    vi.mocked(confirmDialog).mockResolvedValueOnce(false);
    await previewButton().trigger('click'); await flushPromises();
    expect(workspace.props('clientPreview')).toBe(false); expect(line.editor).toBeDefined();
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    vi.mocked(confirmDialog).mockResolvedValueOnce(true);
    await previewButton().trigger('click'); await flushPromises();
    expect(workspace.props('clientPreview')).toBe(true); expect(line.editor).toBeUndefined();
    expect(stored.proposals![0].service_lines).toEqual(expect.arrayContaining([expect.objectContaining({ title: 'Введённая услуга', price: 125.5 })]));
  });
  it('retries a failed save on the next tab click after the line editor has already committed', async () => {
    const line = await editNewService();
    const { confirmDialog } = await import('../src/services/ui-feedback');
    vi.mocked(confirmDialog).mockClear().mockResolvedValueOnce(true);
    vi.mocked(ManagerOrdersService.patchManagerOrder).mockRejectedValueOnce(new Error('offline'));
    await openDocuments();
    expect(line.editor).toBeUndefined(); expect(header().props('pendingLineEdits')).toBe(false);
    expect(wrapper.findComponent(OrderWorkspaceNav).props('active')).toBe('proposal');
    expect(header().props('saveFailed')).toBe(true);
    await openDocuments();
    expect(wrapper.findComponent(OrderWorkspaceNav).props('active')).toBe('documents');
    expect(ManagerOrdersService.patchManagerOrder).toHaveBeenCalledTimes(2);
    expect(confirmDialog).toHaveBeenCalledOnce();
    expect(stored.proposals![0].service_lines).toEqual(expect.arrayContaining([expect.objectContaining({ title: 'Введённая услуга', price: 125.5 })]));
  });
});


// This fixture enforces the backend's proposal-line ownership boundary.
let assignedLinkId = 1000;
const strictCommit = (payload: any) => {
  const proposal = stored.proposals!.find(item => item.id === payload.line_proposal_id)!;
  for (const [field, response] of [['products','product_lines'],['services','service_lines']] as const) {
    if (!payload[field]) continue;
    const ids = new Set((proposal[response] || []).map(row => row.id));
    const requested = payload[field].filter((row: any) => row.link_id != null).map((row: any) => row.link_id);
    if (new Set(requested).size !== requested.length || requested.some((id: number) => !ids.has(id))) throw new Error('Line does not belong to the target proposal');
  }
  const { products, services, line_proposal_id: _id, ...form } = payload;
  stored = { ...stored, ...form };
  const updated = { ...proposal };
  if (products) updated.product_lines = products.map((row: any) => ({ ...row, id: row.link_id ?? assignedLinkId++, product_title: 'Тестовый товар' }));
  if (services) updated.service_lines = services.map((row: any) => ({ ...row, id: row.link_id ?? assignedLinkId++, service_title: row.title }));
  stored.proposals = stored.proposals!.map(item => item.id === proposal.id ? updated : item);
  return structuredClone(stored);
};
const draftPanel = () => wrapper.findComponent(OrderDraftRecovery);
const seedConflict = async () => {
  managerSession.auth.value = { tenant_id: 1, staff_user_id: 99, username: 'draft-test' } as any;
  await mountDrawer('page'); header().vm.$emit('toggle-autosave'); await nextTick();
  header().vm.$emit('update:title', 'Мой заголовок'); customer().vm.$emit('update:comment', 'Мой комментарий');
  await nextTick(); wrapper.unmount();
  stored = { ...stored, title: 'Заголовок коллеги', comment: 'Комментарий коллеги' };
  await mountDrawer('page');
};

const seedDeletedDraft = async (kind: 'services' | 'products') => {
  sessionStorage.clear(); localStorage.clear(); assignedLinkId = 1000; stored = initialOrder();
  managerSession.auth.value = { tenant_id: 1, staff_user_id: 99, username: 'draft-test' } as any;
  const field = kind === 'services' ? 'service_lines' : 'product_lines';
  stored.proposals![0]![field] = [
    { id:81, service_id:7, service_title:'Моя услуга', product_id:9, product_title:'Тестовый товар', quantity:1, price:1200, cost:100, description:'Описание клиента', client_description:'Описание товара', installation_estimate_revision_id:55, installation_projection_mode:'combined', installation_display_lines:[{title:'Часть расчёта',quantity:1,price:1200}] },
    { id:82, service_id:8, service_title:'Другая услуга', product_id:10, product_title:'Другой товар', quantity:1, price:300, cost:50 },
  ] as any;
  await mountDrawer(); header().vm.$emit('toggle-autosave'); await nextTick();
  const rows = wrapper.findComponent(OrderProposalWorkspace).props('commercial')[kind === 'services' ? 'serviceLines' : 'productLines'];
  rows.value[0]!.price = 1400; await nextTick(); wrapper.unmount();
  stored = structuredClone(stored); stored.comment = 'Свежий комментарий';
  stored.proposals![0]![field]!.shift(); stored.proposals![0]![field]![0]!.price = 600;
  vi.mocked(ManagerOrdersService.patchManagerOrder).mockClear().mockImplementation(async (_id,payload) => strictCommit(payload));
  await mountDrawer();
  return field;
};

describe('initial focus before background loading', () => {
  it.each([false,true])('preserves the active input, selection and scroll after background completion (failure %s)', async failure => {
    let finish!: (result:any)=>void, fail!: (reason:any)=>void;
    apiMock.listSupplyRequests.mockImplementationOnce(()=>new Promise((resolve,reject)=>{finish=resolve;fail=reject;}));
    await mountDrawer('page',false,false,true);
    await header().get('[aria-label="Автосохранение заказа"]').trigger('click');
    await header().get('[aria-label^="Изменить название:"]').trigger('click');
    const input=header().get<HTMLInputElement>('[aria-label="Название заказа"]');
    await input.setValue('Продолжаю ввод');input.element.focus();input.element.setSelectionRange(3,8);
    const scroller=wrapper.get('[data-order-scroll]').element;scroller.scrollTop=123;
    vi.spyOn(console,'error').mockImplementation(()=>{});
    if(failure) fail(new Error('background offline'));else finish({items:[]});
    await flushPromises();
    expect(document.activeElement).toBe(input.element);
    expect(input.element.value).toBe('Продолжаю ввод');
    expect([input.element.selectionStart,input.element.selectionEnd]).toEqual([3,8]);
    expect(scroller.scrollTop).toBe(123);
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
  });
  it('does not move focus from a newer order when an earlier request completes', async () => {
    let finish!: (result:any)=>void;
    apiMock.listSupplyRequests.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
    await mountDrawer('page',false,false,true);
    await wrapper.setProps({order:{...stored,id:396,title:'Другой заказ'}});await flushPromises();
    await header().get('[aria-label="Автосохранение заказа"]').trigger('click');
    await header().get('[aria-label^="Изменить название:"]').trigger('click');
    const input=header().get<HTMLInputElement>('[aria-label="Название заказа"]');await input.setValue('Другой ввод');input.element.focus();input.element.setSelectionRange(2,5);
    finish({items:[]});await flushPromises();
    expect(document.activeElement).toBe(input.element);
    expect([input.element.selectionStart,input.element.selectionEnd]).toEqual([2,5]);
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
  });
  it('sets initial focus while requests are pending and does not focus after leaving', async () => {
    let finish!: (result:any)=>void;
    apiMock.listSupplyRequests.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
    await mountDrawer('page',false,false,true);
    expect(document.activeElement).toBe(wrapper.get('aside').element);
    await wrapper.setProps({modelValue:false});
    const outside=document.createElement('input');document.body.append(outside);outside.focus();
    finish({items:[]});await flushPromises();
    expect(document.activeElement).toBe(outside);outside.remove();
  });
});

describe('discard with the real title editor', () => {
  const input = () => header().find<HTMLInputElement>('[aria-label="Название заказа"]');
  const draftEntries = () => Object.fromEntries(Object.entries(sessionStorage).filter(([key])=>key.startsWith('manager_order_drawer_draft_395_25_')));
  const edit = async (automatic: boolean) => {
    managerSession.auth.value = { tenant_id: 1, staff_user_id: 99, username: 'title-test' } as any;
    await mountDrawer('page',false,false,true);
    if (!automatic) { await header().get('[aria-label="Автосохранение заказа"]').trigger('click'); }
    await header().get('[aria-label^="Изменить название:"]').trigger('click');
    await input().setValue('Отменённое название');
  };
  it.each([true,false])('ends title editing after successful delayed cancellation without replaying cancelled input (autosave %s)', async automatic => {
    await edit(automatic);
    let finish!: (order: ManagerOrderDetailResponse) => void;
    vi.mocked(ManagerOrdersService.getManagerOrderDetail).mockImplementationOnce(()=>new Promise(resolve=>{ finish=resolve; }) as any);
    await header().get('[aria-label="Отменить изменения"]').trigger('click');
    await vi.advanceTimersByTimeAsync(2000);
    expect(input().element.value).toBe('Отменённое название');
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    finish({ ...stored, title:'Актуальное серверное название' }); await flushPromises();
    expect(wrapper.text()).toContain('Изменения отменены');
    expect(input().exists()).toBe(false);
    const trigger = header().get('[aria-label="Изменить название: Актуальное серверное название"]');
    expect(document.activeElement).toBe(trigger.element);
    expect(Object.keys(draftEntries())).toHaveLength(0);
    await trigger.trigger('keydown',{key:'Enter'});
    for (const action of ['enter','apply','blur']) {
      await trigger.trigger('click');
      expect(input().element.value).toBe('Актуальное серверное название');
      if (action==='enter') await input().trigger('keydown',{key:'Enter'});
      if (action==='apply') await header().get('[aria-label="Применить название"]').trigger('click');
      if (action==='blur') await input().trigger('blur');
      await vi.advanceTimersByTimeAsync(1200);
    }
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    expect(JSON.stringify(draftEntries())).not.toContain('Отменённое название');
    expect(header().get('[role="status"]').text()).toBe('Сохранено');
  });
  it.each([true,false])('keeps the open editor and scoped draft when cancellation GET fails and allows safe exit (autosave %s)', async automatic => {
    await edit(automatic); const before=draftEntries();
    vi.mocked(ManagerOrdersService.getManagerOrderDetail).mockRejectedValueOnce(new Error('offline'));
    await header().get('[aria-label="Отменить изменения"]').trigger('click'); await flushPromises();
    await vi.advanceTimersByTimeAsync(2000);
    expect(input().element.value).toBe('Отменённое название');
    expect(draftEntries()).toEqual(before);
    expect(wrapper.text()).toContain('Не удалось отменить черновик:');
    expect(await (wrapper.vm as any).prepareToLeave()).toBe(true);
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    expect(draftEntries()).toEqual(before);
  });
  it('keeps focus, selection and newer title input when a normal autosave response arrives', async () => {
    await edit(true);
    let finish!: (order: ManagerOrderDetailResponse) => void;
    let sent: any;
    vi.mocked(ManagerOrdersService.patchManagerOrder).mockImplementationOnce((_id,payload)=>{sent=payload;return new Promise(resolve=>{finish=resolve;}) as any;});
    await vi.advanceTimersByTimeAsync(700);
    await input().setValue('Ещё более новое название');
    input().element.focus(); input().element.setSelectionRange(3,8);
    const element=input().element;
    finish(commit(sent)); await flushPromises();
    expect(input().element).toBe(element);
    expect(element.value).toBe('Ещё более новое название');
    expect(document.activeElement).toBe(element);
    expect([element.selectionStart,element.selectionEnd]).toEqual([3,8]);
    await vi.advanceTimersByTimeAsync(1000);
    expect(stored.title).toBe('Ещё более новое название');
  });
});

describe('draft recovery follow-up regressions', () => {
  it.each(['services','products'] as const)('sends restored deleted %s with a new identity in manual and automatic modes', async kind => {
    for (const automatic of [false, true]) {
      const field = await seedDeletedDraft(kind);
      if (automatic) { header().vm.$emit('toggle-autosave'); await nextTick(); }
      const conflict = draftPanel().props('conflicts')[0]!;
      draftPanel().vm.$emit('resolve', conflict.id, 'local'); await nextTick();
      if (!automatic) { header().vm.$emit('save'); await flushPromises(); }
      else await vi.advanceTimersByTimeAsync(1000);
      expect(ManagerOrdersService.patchManagerOrder).toHaveBeenCalledWith(395, expect.objectContaining({
        [kind]: expect.arrayContaining([expect.objectContaining({link_id:null,price:1400,cost:100,quantity:1})]),
      }));
      expect(header().props('saveFailed')).toBe(false);
      expect(stored.comment).toBe('Свежий комментарий');
      expect(stored.proposals![0]![field]).toHaveLength(2);
      expect(stored.proposals![0]![field]!.find(row=>row.id===82)!.price).toBe(600);
      const restored = wrapper.findComponent(OrderProposalWorkspace).props('commercial')[kind === 'services' ? 'serviceLines' : 'productLines'].value.find((row:any)=>row.price===1400)!;
      expect(restored.link_id).toBe(1000);
      if (kind === 'services') {
        expect(restored.description).toBe('Описание клиента');
        expect(restored.installation_estimate_revision_id).toBeNull();
        expect(restored.installation_projection_mode).toBeNull();
        expect(restored.installation_display_lines).toBeUndefined();
      }
      restored.quantity=2; await nextTick(); header().vm.$emit('save'); await flushPromises();
      expect(stored.proposals![0]![field]).toHaveLength(2);
      expect(stored.proposals![0]![field]!.find(row=>row.id===1000)!.quantity).toBe(2);
      wrapper.unmount();
    }
  });
  it.each(['services','products'] as const)('preserves restored %s across failed save, reload and lost acknowledgement without duplicates', async kind => {
    for (const lostAck of [false, true]) {
      const field = await seedDeletedDraft(kind);
      draftPanel().vm.$emit('resolve', draftPanel().props('conflicts')[0]!.id, 'local'); await nextTick();
      vi.mocked(ManagerOrdersService.patchManagerOrder).mockImplementationOnce(async (_id,payload) => {
        if (lostAck) strictCommit(payload);
        throw new Error('offline');
      });
      header().vm.$emit('save'); await flushPromises();
      expect(header().props('saveFailed')).toBe(true);
      expect(wrapper.findComponent(OrderProposalWorkspace).props('commercial')[kind === 'services' ? 'serviceLines' : 'productLines'].value.some((row:any)=>row.price===1400)).toBe(true);
      wrapper.unmount();
      vi.mocked(ManagerOrdersService.patchManagerOrder).mockClear();
      await mountDrawer();
      if (lostAck) {
        expect(draftPanel().props('conflicts')).toHaveLength(1);
        draftPanel().vm.$emit('resolve', draftPanel().props('conflicts')[0]!.id, 'server'); await nextTick();
        await vi.advanceTimersByTimeAsync(1000);
        expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
      } else {
        expect(draftPanel().exists()).toBe(false);
        header().vm.$emit('save'); await flushPromises();
        expect(ManagerOrdersService.patchManagerOrder).toHaveBeenCalledExactlyOnceWith(395, expect.objectContaining({[kind]:expect.arrayContaining([expect.objectContaining({link_id:null,price:1400})])}));
      }
      expect(stored.proposals![0]![field]).toHaveLength(2);
      expect(stored.proposals![0]![field]!.filter(row=>row.price===1400)).toHaveLength(1);
      expect(stored.comment).toBe('Свежий комментарий');
      wrapper.unmount(); await mountDrawer();
      expect(draftPanel().exists()).toBe(false);
      expect(stored.proposals![0]![field]).toHaveLength(2);
      wrapper.unmount();
    }
  });
  it.each(['services','products'] as const)('keeps server-deleted %s deleted after the server choice', async kind => {
    const field = await seedDeletedDraft(kind);
    draftPanel().vm.$emit('resolve',draftPanel().props('conflicts')[0]!.id,'server'); await nextTick();
    header().vm.$emit('save'); await flushPromises(); await vi.advanceTimersByTimeAsync(1500);
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    expect(stored.proposals![0]![field]).toHaveLength(1);
    expect(stored.proposals![0]![field]![0]!.id).toBe(82);
  });
  it('leaves unresolved recovery without writing or clearing earlier choices', async () => {
    await seedConflict();
    const title = draftPanel().props('conflicts').find(item=>item.path.at(-1)==='title')!;
    draftPanel().vm.$emit('resolve',title.id,'local'); await nextTick();
    const entries = JSON.stringify({...sessionStorage});
    expect(await (wrapper.vm as any).prepareToLeave()).toBe(true);
    await vi.advanceTimersByTimeAsync(1500);
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    expect(JSON.stringify({...sessionStorage})).toBe(entries);
    wrapper.unmount(); await mountDrawer('page');
    expect(draftPanel().props('conflicts')).toHaveLength(1);
    expect(header().props('title')).toBe('Мой заголовок');
  });
  it('does not replace newer order data while cancellation waits for ancillary loading', async () => {
    await seedConflict();
    const fresh = { ...stored, title: 'Название при отмене' };
    vi.mocked(ManagerOrdersService.getManagerOrderDetail).mockResolvedValue(fresh);
    let finishLoading!: (result: any) => void;
    apiMock.listSupplyRequests.mockImplementationOnce(() => new Promise(resolve => { finishLoading = resolve; }));
    header().vm.$emit('discard'); await flushPromises();
    const newer = { ...stored, title: 'Более новое название', comment: 'Более новый комментарий' };
    await wrapper.setProps({ order: newer }); await flushPromises();
    finishLoading({ items: [] }); await flushPromises();
    expect(wrapper.props('order')).toEqual(newer);
    expect(wrapper.emitted('updated')).toBeUndefined();
    expect(header().props('title')).toBe(newer.title);
    expect(customer().props('comment')).toBe(newer.comment);
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
  });
  it('cancels recovery using fresh server data, preserves other drafts, and never schedules a PATCH', async () => {
    await seedConflict();
    sessionStorage.setItem('manager_order_drawer_draft_999_17_other','other input');
    stored = { ...stored, title:'Самое свежее название', comment:'Самый свежий комментарий' };
    vi.spyOn(ManagerOrdersService,'getManagerOrderDetail').mockResolvedValue(structuredClone(stored));
    expect(header().attributes('inert')).toBeUndefined();
    header().vm.$emit('save'); await flushPromises();
    expect(wrapper.text()).toContain('Сначала выберите значения в восстановленном черновике.');
    header().vm.$emit('discard'); await flushPromises(); await vi.advanceTimersByTimeAsync(2000);
    expect(draftPanel().exists()).toBe(false);
    expect(wrapper.text()).not.toContain('Сначала выберите значения в восстановленном черновике.');
    expect(header().props('title')).toBe('Самое свежее название');
    expect(customer().props('comment')).toBe('Самый свежий комментарий');
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    expect(sessionStorage.getItem('manager_order_drawer_draft_999_17_other')).toBe('other input');
    expect(Object.keys(sessionStorage).filter(key=>key.startsWith('manager_order_drawer_draft_395_25_'))).toEqual([]);
  });
});

describe('order drawer autosave integration', () => {
  it.each([true, false])('restores only a failed local title edit over fresh server fields and estimate (autosave %s)', async automatic => {
    managerSession.auth.value = { tenant_id: 1, staff_user_id: 99, username: 'draft-test' } as any;
    managerStorefrontSelection.selectedSlug.value = 'main';
    vi.spyOn(ManagerSettingsService, 'getFxRate').mockResolvedValue({ eur_byn: 3.5, usd_byn: 3 } as any);
    stored.proposals![0]!.service_lines = [{ id: 81, service_title: 'Диагностика', quantity: 1, price: 1200, cost: 0 } as any];
    await mountDrawer();
    if (!automatic) { header().vm.$emit('toggle-autosave'); await nextTick(); }
    vi.mocked(ManagerOrdersService.patchManagerOrder).mockRejectedValueOnce(new Error('offline'));
    header().vm.$emit('update:title', 'Моё название');
    await nextTick();
    await vi.advanceTimersByTimeAsync(1000);
    if (!automatic) { header().vm.$emit('save'); await flushPromises(); }
    expect(header().props('saveFailed')).toBe(true);
    wrapper.unmount();
    stored = { ...stored, comment: 'Новый комментарий коллеги', installation_date: '2026-11-15T12:00:00',
      status: 'execution', delivery_address: 'Новый объект', target_currency: 'EUR', target_currency_amount: 1500, repair_meta: { diagnostic_notes: 'Новая диагностика' } } as any;
    stored.proposals![0]!.service_lines![0]!.price = 1800;
    vi.mocked(ManagerOrdersService.patchManagerOrder).mockClear();
    await mountDrawer();
    await vi.advanceTimersByTimeAsync(1000);
    if (!automatic) { expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled(); header().vm.$emit('save'); await flushPromises(); }
    expect(ManagerOrdersService.patchManagerOrder).toHaveBeenCalledExactlyOnceWith(395, { title: 'Моё название' });
    expect(stored.comment).toBe('Новый комментарий коллеги');
    expect(stored.installation_date).toBe('2026-11-15T12:00:00');
    expect(stored.proposals![0]!.service_lines![0]!.price).toBe(1800);
    managerSession.auth.value = null;
    managerStorefrontSelection.selectedSlug.value = null;
  });
  it.each([true, false])('keeps both conflicting title versions across reload and blocks writes (autosave %s)', async automatic => {
    managerSession.auth.value = { tenant_id: 1, staff_user_id: 99, username: 'draft-test' } as any;
    await mountDrawer();
    if (!automatic) { header().vm.$emit('toggle-autosave'); await nextTick(); }
    vi.mocked(ManagerOrdersService.patchManagerOrder).mockRejectedValueOnce(new Error('offline'));
    header().vm.$emit('update:title', 'Локальное название');
    await nextTick();
    if (automatic) await vi.advanceTimersByTimeAsync(1000);
    wrapper.unmount();
    stored = { ...stored, title: 'Название коллеги' };
    vi.mocked(ManagerOrdersService.patchManagerOrder).mockReset().mockImplementation(async (_id, payload) => commit(payload));
    await mountDrawer();
    const conflictPanel = () => wrapper.findComponent(OrderDraftRecovery);
    expect(conflictPanel().props('conflicts')).toEqual([expect.objectContaining({ local: 'Локальное название', server: 'Название коллеги' })]);
    header().vm.$emit('save');
    await vi.advanceTimersByTimeAsync(2000);
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    expect(await customer().props('beforeNavigate')!()).toBe(true);
    expect(wrapper.emitted('update:modelValue')).toEqual([[false]]);
    // An already received newer response must update the conflict, too.
    stored = { ...stored, title: 'Еще более новое название' };
    await wrapper.setProps({ order: stored }); await flushPromises();
    expect(conflictPanel().props('conflicts')[0]!.server).toBe('Еще более новое название');
    wrapper.unmount(); await mountDrawer();
    const conflict = conflictPanel().props('conflicts')[0]!;
    expect(conflict.local).toBe('Локальное название');
    conflictPanel().vm.$emit('resolve', conflict.id, 'local');
    await nextTick(); await vi.advanceTimersByTimeAsync(1000);
    if (!automatic) {
      expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
      expect(header().props('dirty')).toBe(true);
      header().vm.$emit('save'); await flushPromises();
    }
    expect(ManagerOrdersService.patchManagerOrder).toHaveBeenCalledExactlyOnceWith(395, { title: 'Локальное название' });
  });

  it('restores changed service quantity without rolling back a newer server price', async () => {
    managerSession.auth.value = { tenant_id: 1, staff_user_id: 99, username: 'draft-test' } as any;
    stored.proposals![0]!.service_lines = [{ id: 81, service_title: 'Диагностика', quantity: 1, price: 1200, cost: 0 } as any];
    await mountDrawer(); header().vm.$emit('toggle-autosave'); await nextTick();
    const commercial = wrapper.findComponent(OrderProposalWorkspace).props('commercial');
    commercial.serviceLines.value[0]!.quantity = 2; await nextTick(); wrapper.unmount();
    stored.proposals![0]!.service_lines![0]!.price = 1800;
    await mountDrawer();
    expect(wrapper.findComponent(OrderProposalWorkspace).props('commercial').serviceLines.value[0]).toMatchObject({ quantity: 2, price: 1800 });
    expect(wrapper.findComponent(OrderDraftRecovery).exists()).toBe(false);
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    header().vm.$emit('save'); await flushPromises();
    expect(ManagerOrdersService.patchManagerOrder).toHaveBeenCalledWith(395, expect.objectContaining({ services: [expect.objectContaining({ quantity: 2, price: 1800 })] }));
  });

  it('restores product quantity over the new server price and retains logistics metadata', async () => {
    managerSession.auth.value = { tenant_id: 1, staff_user_id: 99, username: 'draft-test' } as any;
    stored.proposals![0]!.product_lines = [{ id: 82, product_id: 9, product_title: 'Тестовый товар', quantity: 1, price: 1200, cost: 0, product_country: 'Китай' } as any];
    await mountDrawer(); header().vm.$emit('toggle-autosave'); await nextTick();
    wrapper.findComponent(OrderProposalWorkspace).props('commercial').productLines.value[0]!.quantity = 2;
    await nextTick(); wrapper.unmount();
    stored.proposals![0]!.product_lines![0]!.price = 1800;
    (stored.proposals![0]!.product_lines![0] as any).product_country = 'Япония';
    await mountDrawer();
    expect(wrapper.findComponent(OrderProposalWorkspace).props('commercial').productLines.value[0]).toMatchObject({ quantity: 2, price: 1800, product_country: 'Япония' });
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    header().vm.$emit('save'); await flushPromises();
    expect(ManagerOrdersService.patchManagerOrder).toHaveBeenCalledWith(395, expect.objectContaining({ products: [expect.objectContaining({ quantity: 2, price: 1800 })] }));
  });

  it('opens customer editing under the order context instead of rendering it in Work', async () => {
    await mountDrawer();
    expect(customer().props('editTarget')).toBe(null);

    customer().vm.$emit('update:editTarget', 'customer');
    await nextTick();

        expect(customer().props('editTarget')).toBe('customer');
  });

  it('preserves an unfinished object comment and proposal when request evidence is opened and closed', async () => {
    vi.stubGlobal('matchMedia', () => ({ matches: false }));
    await mountDrawer('page', true);
    customer().vm.$emit('update:editTarget', 'object'); await nextTick();
    await customer().get('[data-testid="object-comment"]').setValue('Моё несохранённое уточнение');
    const commercial = wrapper.findComponent(OrderProposalWorkspace).props('commercial') as any;
    commercial.addServiceLine(); commercial.serviceLines.value[0].title = 'Ручной состав КП';
    await wrapper.get('[data-testid="order-request-trigger"]').trigger('click');
    await wrapper.get('[data-testid="order-request-trigger"]').trigger('click');
    expect((customer().get('[data-testid="object-comment"]').element as HTMLTextAreaElement).value).toBe('Моё несохранённое уточнение');
    expect(commercial.serviceLines.value[0].title).toBe('Ручной состав КП');
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it('saves the object through the shared save queue while preserving proposal edits', async () => {
    await mountDrawer();
    const commercial = wrapper.findComponent(OrderProposalWorkspace).props('commercial') as any;
    commercial.addServiceLine();
    commercial.serviceLines.value[0].title = 'Монтаж по согласованию';
    commercial.serviceLines.value[0].price = 600;
    commitLineEdit(commercial.serviceLines.value[0]);
    await nextTick();
    expect(await customer().props('persistObject')!({ address: 'Минск, Новая, 1', branchId: null, comment: 'Вход со двора' })).toBe(true);
    expect(stored.delivery_address).toBe('Минск, Новая, 1');
    expect(stored.comment).toBe('Вход со двора');
    expect(stored.proposals![0].service_lines).toEqual(expect.arrayContaining([expect.objectContaining({ title: 'Монтаж по согласованию', price: 600 })]));
  });

  it('rolls back failed object model changes without discarding other order edits', async () => {
    await mountDrawer();
    vi.mocked(ManagerOrdersService.patchManagerOrder).mockRejectedValueOnce(new Error('offline'));
    expect(await customer().props('persistObject')!({ address: 'Несохранённый адрес', branchId: null, comment: 'Несохранённый комментарий' })).toBe(false);
    expect(customer().props('deliveryAddress')).toBe('');
    expect(customer().props('comment')).toBe('');
    expect(header().props('saveFailed')).toBe(true);
  });

  it('places the reviewed request beside customer context and outside Work', async () => {
    stored = {
      ...stored,
      lead_source: 'belzakupki',
      source_enrichment: {
        source: 'goszakupki_by', external_id: '3707082',
        work_summary: 'Обслуживание восьми кондиционеров',
        equipment_details: '6 в Витебске, 2 в Шумилино',
        objects: [
          { address: 'г. Витебск, ул. Суворова, 42/13', equipment: [] },
          { address: 'г.п. Шумилино, ул. Короткина, 10', equipment: [] },
        ],
        customer_branch_ids: [],
      },
    } as ManagerOrderDetailResponse;
    await mountDrawer();
    const source = wrapper.findComponent(OrderRequestSourceCard);
    expect(source.props('orderId')).toBe(395);
    expect(source.props('sourceEnrichment')).toEqual(stored.source_enrichment);
    expect(source.element.parentElement).toBe(customer().element.parentElement);
    await openSection('work');
    expect(wrapper.find('[data-order-usage="workspace-work-panel"]').text()).not.toContain('Данные из закупки');
    expect(wrapper.find('[data-order-usage="workspace-work-panel"]').text()).not.toContain('Дозаполнить из источника');
  });

  it('saves local edits before source review and refreshes added lines before resuming autosave', async () => {
    stored = { ...stored, lead_source: 'belzakupki' };
    await mountDrawer();
    customer().vm.$emit('update:comment', 'Сохранить перед проработкой заявки');
    await nextTick();
    wrapper.findComponent(OrderRequestSourceCard).vm.$emit('review');
    await flushPromises();
    expect(stored.comment).toBe('Сохранить перед проработкой заявки');
    const modal = wrapper.findComponent(LeadSourceReviewModal);
    expect(modal.props('open')).toBe(true);
    expect(await modal.props('beforeApply')!()).toBe(true);
    expect(wrapper.find('aside').attributes('aria-busy')).toBe('true');

    const fresh = { ...stored, attachment_count: 2 };
    vi.spyOn(ManagerOrdersService, 'getManagerOrderDetail').mockResolvedValue(fresh);
    expect(await modal.props('afterApply')!()).toBe(true);
    expect(wrapper.emitted('updated')?.at(-1)).toEqual([fresh]);
    modal.props('endApply')!();
    await nextTick();
    expect(wrapper.find('aside').attributes('aria-busy')).toBe('false');
  });

  it('counts opening once with the hydrated scenario, before any user edit', async () => {
    managerSession.isAuthenticated.value = true;
    managerSession.auth.value = { tenant_id: 1, staff_user_id: 99, username: 'usage-test' } as any;
    managerStorefrontSelection.selectedSlug.value = 'main';
    const record = vi.spyOn(ManagerOrderUsageService, 'recordManagerOrderUsage')
      .mockImplementation(() => new CancelablePromise((resolve) => resolve({ accepted: 1 })));
    try {
      await mountDrawer();
      await vi.advanceTimersByTimeAsync(2_000);
      expect(record).toHaveBeenCalledOnce();
      expect(record.mock.calls[0]?.[0].events).toEqual([{
        metric: 'order_open', workflow: 'maintenance', party_kind: 'company', viewport: 'desktop',
      }]);
      expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    } finally {
      managerSession.isAuthenticated.value = false;
      managerSession.auth.value = null;
      managerStorefrontSelection.selectedSlug.value = null;
    }
  });
  it('flushes edits before navigating to the customer profile', async () => {
    await mountDrawer();
    customer().vm.$emit('update:comment', 'Сохранить перед переходом');
    await nextTick();
    expect(await customer().props('beforeNavigate')!()).toBe(true);
    expect(stored.comment).toBe('Сохранить перед переходом');
    expect(wrapper.emitted('update:modelValue')).toEqual([[false]]);
  });
  it('persists a suggested address and added service before generating a contract', async () => {
    await mountDrawer();
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    customer().vm.$emit('update:deliveryAddress', 'Витебск, Свердлова, 15');
    const commercial = wrapper.findComponent(OrderProposalWorkspace).props('commercial');
    commercial.serviceLines.value.push({ service_id: null, title: 'Обслуживание', quantity: 11, price: 220, cost: 0 });
    await nextTick();
    await openDocuments();
    const beforeGenerate = wrapper.findComponent(OrderDocumentsWorkspace).props('beforeGenerate')!;
    expect(await beforeGenerate('contract')).toEqual({ mutated: true });
    expect(ManagerOrdersService.patchManagerOrder).toHaveBeenCalledOnce();
    expect(ManagerOrdersService.patchManagerOrder).toHaveBeenCalledWith(395, expect.objectContaining({
      customer_delivery_address: 'Витебск, Свердлова, 15', line_proposal_id: 25,
      services: [expect.objectContaining({ title: 'Обслуживание', quantity: 11, price: 220, proposal_id: 25 })],
    }));
    expect(header().props('dirty')).toBe(false);
    expect(header().props('saveStatusText')).toBe('Сохранено');
  });

  it('does not autosave a saved EUR deal while the unavailable FX rate loads', async () => {
    stored = {
      ...stored,
      target_currency: 'EUR',
      target_currency_amount: 1_250.75,
    };
    vi.spyOn(ManagerSettingsService, 'getFxRate').mockResolvedValue({
      usd_byn: 3.2,
      eur_byn: null,
    } as any);

    await mountDrawer();
    await vi.advanceTimersByTimeAsync(1_000);

    await openSection('payments');
    expect(payments().props('targetCurrency')).toBe('EUR');
    expect(payments().props('targetCurrencyAmount')).toBe(1_250.75);
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    expect(header().props('dirty')).toBe(false);
  });

  it('saves a comment on a saved EUR deal while its live FX rate is unavailable', async () => {
    stored = {
      ...stored,
      target_currency: 'EUR',
      target_currency_amount: 1_250.75,
    };
    vi.spyOn(ManagerSettingsService, 'getFxRate').mockResolvedValue({
      usd_byn: 3.2,
      eur_byn: null,
    } as any);

    await mountDrawer();
    customer().vm.$emit('update:comment', 'Комментарий без изменения суммы');
    await nextTick();
    await vi.advanceTimersByTimeAsync(1_000);

    expect(ManagerOrdersService.patchManagerOrder).toHaveBeenCalledWith(395, {
      comment: 'Комментарий без изменения суммы',
    });
    expect(stored.target_currency).toBe('EUR');
    expect(stored.target_currency_amount).toBe(1_250.75);
  });

  it('blocks an edited currency amount while its live FX rate is unavailable', async () => {
    stored = {
      ...stored,
      target_currency: 'EUR',
      target_currency_amount: 1_250.75,
    };
    vi.spyOn(ManagerSettingsService, 'getFxRate').mockResolvedValue({
      usd_byn: 3.2,
      eur_byn: null,
    } as any);

    await mountDrawer();
    await openSection('payments');
    payments().vm.$emit('update:targetCurrencyAmount', 1_300);
    await nextTick();
    await vi.advanceTimersByTimeAsync(1_000);

    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    expect(header().props('dirty')).toBe(true);
  });

  it('keeps input typed during a slow save after the parent publishes the old response', async () => {
    let finish: () => void = () => {};
    vi.mocked(ManagerOrdersService.patchManagerOrder).mockImplementationOnce((_id, payload) => {
      const first = commit(payload);
      return new Promise((resolve) => { finish = () => resolve(first); }) as any;
    });
    await mountDrawer();
    customer().vm.$emit('update:comment', 'Первый текст');
    await nextTick();
    await vi.advanceTimersByTimeAsync(750);
    customer().vm.$emit('update:comment', 'Новый текст во время запроса');
    await nextTick();
    finish();
    await flushPromises();
    expect(customer().props('comment')).toBe('Новый текст во время запроса');
    expect(ManagerOrdersService.patchManagerOrder).toHaveBeenCalledTimes(2);
    expect(stored.comment).toBe('Новый текст во время запроса');
    expect(header().props('dirty')).toBe(false);
  });

  it('preserves edits made during attachment and saves them with the immutable line before refresh', async () => {
    await mountDrawer();
    const attached = { id: 88, proposal_id: 25, service_id: null, service_title: 'Монтаж по книге',
      quantity: 1, price: 530.25, cost: 0, line_total: 530.25,
      installation_estimate_revision_id: 21, installation_projection_mode: 'collapsed' };
    vi.spyOn(ManagerOrdersService, 'getManagerOrderDetail').mockImplementation(async () => {
      const order = structuredClone(stored);
      order.proposals![0]!.service_lines = [
        ...(stored.proposals?.[0]?.service_lines || []).filter((line) => line.id !== 88).map((line, index) => ({
          id: line.id || line.link_id || 100 + index, proposal_id: 25,
          service_id: line.service_id || null, service_title: line.service_title || line.title || 'Услуга',
          quantity: line.quantity, price: line.price, cost: line.cost || 0,
          line_total: line.quantity * line.price,
        } as any)),
        attached,
      ];
      return order;
    });
    const workspace = wrapper.findComponent(OrderProposalWorkspace);
    const begin = workspace.props('beginInstallationAttach');
    const after = workspace.props('afterInstallationAttach');
    const end = workspace.props('endInstallationAttach');
    const scopeKey = 'manager.installation-order:anonymous:395:25';
    const token = 'attach-test-token';
    expect(await begin(395, 25, scopeKey, token)).toBe(true);
    expect(wrapper.get('aside').attributes('inert')).toBeDefined();
    customer().vm.$emit('update:comment', 'Новая заметка во время прикрепления');
    const commercial = workspace.props('commercial');
    commercial.serviceLines.value.push({ service_id: null, title: 'Дополнительная работа', quantity: 1, price: 40, cost: 0 });
    await nextTick();
    await vi.advanceTimersByTimeAsync(1_000);
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    expect(await after(395, 25, scopeKey, token)).toBe(true);
    end(token);
    await flushPromises();
    expect(ManagerOrdersService.patchManagerOrder).toHaveBeenCalledWith(395, expect.objectContaining({
      comment: 'Новая заметка во время прикрепления',
      services: expect.arrayContaining([
        expect.objectContaining({ title: 'Дополнительная работа' }),
        expect.objectContaining({ link_id: 88, title: 'Монтаж по книге', price: 530.25 }),
      ]),
    }));
    expect(wrapper.get('aside').attributes('inert')).toBeUndefined();
  });

  it('drains an in-flight autosave before attachment starts and rejects a stale refresh', async () => {
    let finish: () => void = () => {};
    vi.mocked(ManagerOrdersService.patchManagerOrder).mockImplementationOnce((_id, payload) => {
      const first = commit(payload);
      return new Promise((resolve) => { finish = () => resolve(first); }) as any;
    });
    await mountDrawer();
    customer().vm.$emit('update:comment', 'Первое изменение');
    await nextTick();
    await vi.advanceTimersByTimeAsync(750);
    const workspace = wrapper.findComponent(OrderProposalWorkspace);
    const scopeKey = 'manager.installation-order:anonymous:395:25';
    const token = 'pending-save-token';
    const start = workspace.props('beginInstallationAttach')(395, 25, scopeKey, token);
    await nextTick();
    expect(wrapper.get('aside').attributes('inert')).toBeDefined();
    customer().vm.$emit('update:comment', 'Второе изменение');
    await nextTick();
    finish();
    expect(await start).toBe(true);
    expect(stored.comment).toBe('Второе изменение');
    expect(ManagerOrdersService.patchManagerOrder).toHaveBeenCalledTimes(2);
    const changed = { ...stored, id: 396 } as ManagerOrderDetailResponse;
    await wrapper.setProps({ order: changed });
    expect(await workspace.props('afterInstallationAttach')(395, 25, scopeKey, token)).toBe(false);
    workspace.props('endInstallationAttach')(token);
    expect(wrapper.get('aside').attributes('inert')).toBeUndefined();
  });

  it('keeps manual mode dirty, prevents document creation, and still supports Save', async () => {
    await mountDrawer();
    header().vm.$emit('toggle-autosave');
    customer().vm.$emit('update:deliveryAddress', 'Минск, Ленина, 1');
    await nextTick();
    await vi.advanceTimersByTimeAsync(1000);
    await openDocuments();
    const beforeGenerate = wrapper.findComponent(OrderDocumentsWorkspace).props('beforeGenerate')!;
    expect(await beforeGenerate('invoice')).toBe(false);
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    header().vm.$emit('save');
    await flushPromises();
    expect(stored.delivery_address).toBe('Минск, Ленина, 1');
    expect(header().props('dirty')).toBe(false);
  });
});


describe('equipment picker navigation from the order', () => {
  const setupCatalog = async () => {
    managerSession.auth.value = { tenant_id: 1, staff_user_id: 99, username: 'catalog-test', capabilities: ['platform.manage'] } as any;
    history.replaceState({}, '', '/manager/orders/kanban?orderId=395');
    await mountDrawer();
  };
  afterEach(() => {
    managerSession.auth.value = null;
    history.replaceState({}, '', '/');
  });
  it('saves edits before opening the picker for the exact order and proposal', async () => {
    await setupCatalog();
    customer().vm.$emit('update:comment', 'Сохранить перед подбором');
    await nextTick();
    const proposal = wrapper.findComponent(OrderProposalWorkspace);
    expect(proposal.props('catalogAvailable')).toBe(true);
    proposal.vm.$emit('catalog');
    await flushPromises();
    expect(stored.comment).toBe('Сохранить перед подбором');
    expect(location.pathname).toBe('/manager/catalog-decision');
    const params = new URLSearchParams(location.search);
    expect(params.get('orderId')).toBe('395');
    expect(params.get('proposalId')).toBe('25');
    expect(wrapper.emitted('update:modelValue')).toEqual([[false]]);
  });
  it('keeps the order open when saving before the picker fails', async () => {
    await setupCatalog();
    vi.mocked(ManagerOrdersService.patchManagerOrder).mockRejectedValueOnce(new Error('save failed'));
    customer().vm.$emit('update:comment', 'Не терять');
    await nextTick();
    wrapper.findComponent(OrderProposalWorkspace).vm.$emit('catalog');
    await flushPromises();
    expect(location.pathname).toBe('/manager/orders/kanban');
    expect(wrapper.emitted('update:modelValue')).toBeUndefined();
    expect(wrapper.text()).toContain('Не удалось сохранить заказ');
  });
  it.each(['/manager/orders/395?proposalId=26', '/manager/orders/kanban?orderId=395&proposalId=26'])
  ('opens the requested alternative with its own rows and total at %s without selecting it', async (url) => {
    const service = (id: number, title: string, price: number) => ({ id, service_title: title, quantity: 1, price, cost: 0, line_total: price });
    stored.proposals![0] = { ...stored.proposals![0]!, service_lines: [service(1, 'Вариант А', 1200)] as any, total_amount: 1200 };
    stored.proposals!.push({ ...stored.proposals![0]!, id: 26, name: 'Альтернатива', is_selected: false, service_lines: [service(2, 'Вариант Б', 2300)] as any, total_amount: 2300 });
    history.replaceState({}, '', url);
    await mountDrawer('page');
    const workspace = wrapper.findComponent(OrderProposalWorkspace);
    expect(workspace.props('proposal').activeProposalId.value).toBe(26);
    expect((workspace.props('commercial') as any).serviceLines.value).toEqual([expect.objectContaining({ title: 'Вариант Б', price: 2300 })]);
    expect(header().props('total')).toBe(2300);
    expect(stored.proposals!.find(item => item.is_selected)?.id).toBe(25);
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    (workspace.props('commercial') as any).serviceLines.value[0].price = 2400;
    await nextTick(); await vi.advanceTimersByTimeAsync(700); await flushPromises();
    expect(ManagerOrdersService.patchManagerOrder).toHaveBeenLastCalledWith(395, expect.objectContaining({ line_proposal_id: 26 }));
    expect(stored.proposals![0]!.service_lines![0]!.price).toBe(1200);
    expect(stored.proposals![1]!.service_lines![0]!.price).toBe(2400);
    expect(stored.proposals![0]!.is_selected).toBe(true);
  });
  it.each(['close', 'switch order', 'close and reopen', 'dispose'])
  ('cancels the delayed document-toast refresh on %s', async (change) => {
    const managed = vi.spyOn(ManagerDocumentSystemService, 'listManagerManagedOrderDocuments').mockResolvedValue({ items: [] });
    await mountDrawer();
    await openDocuments();
    wrapper.findComponent(OrderDocumentsWorkspace).vm.$emit('toast', { message: 'Изменения из Google сохранены в истории документа.' });
    if (change === 'dispose') wrapper.unmount();
    else if (change === 'switch order') await wrapper.setProps({ order: { ...stored, id: 396 } });
    else {
      await wrapper.setProps({ modelValue: false });
      if (change === 'close and reopen') await wrapper.setProps({ modelValue: true });
    }
    await flushPromises();
    managed.mockClear();
    vi.mocked(ManagerMailService.listManagerOrderOutgoingEmails).mockClear();
    await vi.advanceTimersByTimeAsync(500);
    expect(managed).not.toHaveBeenCalled();
    expect(ManagerMailService.listManagerOrderOutgoingEmails).not.toHaveBeenCalled();
  });

  it('keeps the document-toast refresh for the same open order', async () => {
    const managed = vi.spyOn(ManagerDocumentSystemService, 'listManagerManagedOrderDocuments').mockResolvedValue({ items: [] });
    await mountDrawer();
    await openDocuments();
    managed.mockClear();
    vi.mocked(ManagerMailService.listManagerOrderOutgoingEmails).mockClear();
    wrapper.findComponent(OrderDocumentsWorkspace).vm.$emit('toast', { message: 'Документ сохранён.' });
    await vi.advanceTimersByTimeAsync(500);
    expect(managed).toHaveBeenCalledWith(395);
    expect(ManagerMailService.listManagerOrderOutgoingEmails).toHaveBeenCalledWith(395, 20);
  });

});


describe('lazy order section integration', () => {
  afterEach(() => history.replaceState({}, '', '/'));

  it('starts with Proposal only and defers work requests, documents and customer details until opened', async () => {
    const complaints = vi.spyOn(ManagerRepairComplaintsService, 'listManagerRepairComplaintPresets').mockResolvedValue({ items: [] } as any);
    stored = { ...stored, workflow_type: 'repair' };
    await mountDrawer('dialog', false, false);
    expect(wrapper.findComponent(OrderProposalWorkspace).exists()).toBe(true);
    expect(wrapper.findComponent(OrderWorkWorkspace).exists()).toBe(false);
    expect(wrapper.findComponent(OrderDocumentsWorkspace).exists()).toBe(false);
    expect(wrapper.findComponent(OrderPaymentWorkspace).exists()).toBe(false);
    expect(customer().exists()).toBe(false);
    expect(apiMock.getManagerInstallers).not.toHaveBeenCalled();
    expect(complaints).not.toHaveBeenCalled();

    await openSection('work');
    expect(wrapper.findComponent(OrderWorkWorkspace).exists()).toBe(true);
    expect(apiMock.getManagerInstallers).toHaveBeenCalledOnce();
    await openSection('proposal');
    await openSection('work');
    expect(apiMock.getManagerInstallers).toHaveBeenCalledOnce();
    await openCustomerContext();
    const context = customer().vm;
    await wrapper.get('[aria-controls="order-context-details"]').trigger('click');
    expect(customer().vm).toBe(context);
    expect(wrapper.get('#order-context-details').attributes('style')).toContain('display: none');
  });

  it('keeps the same proposal draft and manual save mode across every section', async () => {
    await mountDrawer();
    const proposal = wrapper.findComponent(OrderProposalWorkspace);
    const commercial = proposal.props('commercial');
    header().vm.$emit('toggle-autosave');
    commercial.addServiceLine();
    commercial.serviceLines.value[0].title = 'Несохранённая услуга';
    commercial.serviceLines.value[0].price = 740;
    commitLineEdit(commercial.serviceLines.value[0]);
    await nextTick();
    for (const section of ['work', 'documents', 'payments', 'proposal'] as const) {
      await openSection(section);
      expect(wrapper.findComponent(OrderWorkspaceNav).props('active')).toBe(section);
      expect(header().props('dirty')).toBe(true);
      expect(header().props('autosaveEnabled')).toBe(false);
    }
    const returned = wrapper.findComponent(OrderProposalWorkspace);
    expect(returned.vm).toBe(proposal.vm);
    expect(returned.props('commercial').serviceLines.value).toEqual(expect.arrayContaining([
      expect.objectContaining({ title: 'Несохранённая услуга', price: 740 }),
    ]));
    await vi.advanceTimersByTimeAsync(1_000);
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
    header().vm.$emit('save'); await flushPromises();
    expect(stored.proposals![0].service_lines).toEqual(expect.arrayContaining([
      expect.objectContaining({ title: 'Несохранённая услуга', price: 740 }),
    ]));
    expect(header().props('dirty')).toBe(false);
  });

  it('keeps a pending autosave alive when the manager switches sections', async () => {
    let finish!: () => void;
    vi.mocked(ManagerOrdersService.patchManagerOrder).mockImplementationOnce((_id, payload) => {
      const saved = commit(payload);
      return new Promise(resolve => { finish = () => resolve(saved); }) as any;
    });
    await mountDrawer();
    customer().vm.$emit('update:comment', 'Сохранение между разделами');
    await nextTick(); await vi.advanceTimersByTimeAsync(750);
    expect(header().props('saving')).toBe(true);
    await openSection('work'); await openSection('documents');
    expect(header().props('saving')).toBe(true);
    expect(wrapper.findComponent(OrderWorkspaceNav).props('active')).toBe('documents');
    finish(); await flushPromises();
    expect(ManagerOrdersService.patchManagerOrder).toHaveBeenCalledOnce();
    expect(stored.comment).toBe('Сохранение между разделами');
    expect(header().props('saving')).toBe(false);
    expect(header().props('dirty')).toBe(false);
  });

  it('honors the exact page section URL and keeps the draft and current section when leaving is canceled', async () => {
    history.replaceState({}, '', '/manager/orders/395?proposalId=25&section=work&source=synthetic');
    await mountDrawer('page');
    expect(wrapper.findComponent(OrderWorkspaceNav).props('active')).toBe('work');
    expect(wrapper.findComponent(OrderProposalWorkspace).exists()).toBe(false);
    expect(wrapper.findComponent(OrderDocumentsWorkspace).exists()).toBe(false);
    expect(apiMock.getManagerInstallers).toHaveBeenCalledOnce();
    await openSection('documents');
    const url = new URL(location.href);
    expect(url.pathname).toBe('/manager/orders/395');
    expect(url.searchParams.get('section')).toBe('documents');
    expect(url.searchParams.get('proposalId')).toBe('25');
    expect(url.searchParams.get('source')).toBe('synthetic');
    header().vm.$emit('toggle-autosave');
    header().vm.$emit('update:title', 'Не терять при отмене перехода');
    await nextTick();
    const { confirmDialog } = await import('../src/services/ui-feedback');
    vi.mocked(confirmDialog).mockResolvedValueOnce(false);
    expect(await (wrapper.vm as any).prepareToLeave()).toBe(false);
    expect(wrapper.findComponent(OrderWorkspaceNav).props('active')).toBe('documents');
    expect(header().props('title')).toBe('Не терять при отмене перехода');
    expect(header().props('dirty')).toBe(true);
    expect(location.href).toBe(url.href);
    expect(wrapper.emitted('update:modelValue')).toBeUndefined();
    expect(ManagerOrdersService.patchManagerOrder).not.toHaveBeenCalled();
  });
});


describe('order responsibility with the actual drawer save queue', () => {
  const person = { staff_user_id: 7, display_name: 'Мария', avatar_url: null, is_active: true };
  const responsibility = () => wrapper.findComponent(OrderResponsiblePanel);
  beforeEach(() => {
    managerSession.auth.value = { tenant_id: 2, storefront_id: 1, staff_user_id: 7, username: 'maria', capabilities: ['crm.manage'] } as any;
    managerStorefrontSelection.selectedSlug.value = 'main';
    stored = { ...initialOrder(), responsible_person: person, responsible_version: 3 } as any;
  });
  afterEach(() => { managerSession.auth.value = null; managerStorefrontSelection.selectedSlug.value = null; });
  it('drains a queued autosave before assignment and preserves newer edits made while the full response is pending', async () => {
    let finishSave!: (value: ManagerOrderDetailResponse) => void;
    let savePayload: any;
    vi.mocked(ManagerOrdersService.patchManagerOrder).mockImplementationOnce((_id, payload) => { savePayload = payload; return new Promise(resolve => { finishSave = resolve; }) as any; });
    let finishAssignment!: (value: any) => void;
    const assign = vi.spyOn(orderResponsibilityApi, 'assign').mockImplementation(() => new Promise(resolve => { finishAssignment = resolve; }) as any);
    await mountDrawer();
    customer().vm.$emit('update:comment', 'Первая правка'); await nextTick(); await vi.advanceTimersByTimeAsync(700); await flushPromises();
    const pending = responsibility().props('assign')!(8); await flushPromises(); expect(assign).not.toHaveBeenCalled();
    customer().vm.$emit('update:comment', 'Правка в очереди'); await nextTick(); finishSave(commit(savePayload)); await flushPromises();
    expect(assign).toHaveBeenCalledWith(395, 8, 3); expect(stored.comment).toBe('Правка в очереди');
    customer().vm.$emit('update:comment', 'Новая правка во время назначения'); await nextTick();
    const commercial = wrapper.findComponent(OrderProposalWorkspace).props('commercial') as any;
    commercial.addServiceLine(); commercial.serviceLines.value[0].title = 'Новая смета'; commercial.serviceLines.value[0].price = 700; commitLineEdit(commercial.serviceLines.value[0]); await nextTick();
    stored = { ...stored, responsible_person: { ...person, staff_user_id: 8, display_name: 'Андрей' }, responsible_version: 4 } as any;
    const updated = structuredClone(stored);
    finishAssignment(updated); expect(await pending).toBe(true); await flushPromises();
    expect(customer().props('comment')).toBe('Новая правка во время назначения'); expect((wrapper.props('order') as any).responsible_person.display_name).toBe('Андрей');
    await vi.advanceTimersByTimeAsync(700); await flushPromises(); expect(stored.comment).toBe('Новая правка во время назначения');
    expect(stored.proposals![0].service_lines).toEqual(expect.arrayContaining([expect.objectContaining({ title: 'Новая смета', price: 700 })]));
  });
  it('keeps the version seen at the click if a concurrent reassignment arrives while draining autosave', async () => {
    vi.mocked(ManagerOrdersService.patchManagerOrder).mockImplementation(async (_id, payload) => {
      commit(payload);
      stored = { ...stored, responsible_person: { ...person, staff_user_id: 8, display_name: 'Андрей' }, responsible_version: 4 } as any;
      return structuredClone(stored);
    });
    const assign = vi.spyOn(orderResponsibilityApi, 'assign').mockRejectedValue({ status: 409 });
    const reload = vi.spyOn(ManagerOrdersService, 'getManagerOrderDetail').mockImplementation(async () => structuredClone(stored) as any);
    await mountDrawer(); customer().vm.$emit('update:comment', 'Сохранить перед снятием ответственного'); await nextTick();
    expect(await responsibility().props('assign')!(null)).toBe(false); await flushPromises();
    expect(assign).toHaveBeenCalledExactlyOnceWith(395, null, 3); expect(reload).toHaveBeenCalledWith(395);
    expect((wrapper.props('order') as any).responsible_person.display_name).toBe('Андрей'); expect(responsibility().props('error')).toContain('Показаны текущие данные');
    expect(stored.comment).toBe('Сохранить перед снятием ответственного');
  });
  it('refreshes only responsibility after a 409, keeps unsaved fields and never replays the rejected choice', async () => {
    let rejectAssignment!: (reason: any) => void;
    const assign = vi.spyOn(orderResponsibilityApi, 'assign').mockImplementation(() => new Promise((_resolve, reject) => { rejectAssignment = reject; }) as any);
    const fresh = { ...stored, comment: 'Чужой ответ', responsible_person: null, responsible_version: 4 };
    const reload = vi.spyOn(ManagerOrdersService, 'getManagerOrderDetail').mockResolvedValue(fresh);
    await mountDrawer(); const pending = responsibility().props('assign')!(8); await flushPromises();
    customer().vm.$emit('update:comment', 'Мои несохранённые данные'); await nextTick(); rejectAssignment({ status: 409 }); expect(await pending).toBe(false); await flushPromises();
    expect(assign).toHaveBeenCalledOnce(); expect(reload).toHaveBeenCalledWith(395); expect(responsibility().props('error')).toContain('Показаны текущие данные'); expect(customer().props('comment')).toBe('Мои несохранённые данные'); expect((wrapper.props('order') as any).responsible_version).toBe(4);
  });
  it('allows clear and virtual platform support, but disables demo and a legacy identity without staff', async () => {
    const assign = vi.spyOn(orderResponsibilityApi, 'assign').mockResolvedValue({ ...stored, responsible_person: null, responsible_version: 4 } as any);
    managerSession.auth.value = { ...managerSession.auth.value!, is_platform_owner: true, tenant_membership_id: null };
    await mountDrawer(); expect(responsibility().props('canAssign')).toBe(true); expect(await responsibility().props('assign')!(null)).toBe(true); expect(assign).toHaveBeenCalledWith(395, null, 3);
    managerSession.auth.value = { ...managerSession.auth.value!, demo_read_only: true }; await nextTick(); expect(responsibility().props('canAssign')).toBe(false); expect(await responsibility().props('assign')!(8)).toBe(false);
    managerSession.auth.value = { ...managerSession.auth.value!, demo_read_only: false, staff_user_id: null, auth_source: 'legacy' }; await nextTick(); expect(responsibility().props('canAssign')).toBe(false); expect(assign).toHaveBeenCalledOnce();
  });
  it('discards an assignment response after switching person/company/site context', async () => {
    let finish!: (value: any) => void; vi.spyOn(orderResponsibilityApi, 'assign').mockImplementation(() => new Promise(resolve => { finish = resolve; }) as any);
    await mountDrawer(); const pending = responsibility().props('assign')!(8); await flushPromises();
    const emittedBefore = wrapper.emitted('updated')?.length || 0; managerStorefrontSelection.selectedSlug.value = 'other'; await nextTick();
    finish({ ...stored, responsible_person: null, responsible_version: 4 }); expect(await pending).toBe(false); expect(wrapper.emitted('updated')?.length || 0).toBe(emittedBefore);
  });
});


describe('worker instructions with the actual drawer save queue', () => {
  it('flushes queued order edits before a worker write without applying workspace data to order fields', async () => {
    managerSession.auth.value = { username: 'manager', staff_user_id: 7, tenant_id: 2, storefront_id: 1, capabilities: ['crm.manage'] } as any;
    const workspace = { order_id: stored.id, assignments: [], materials: [], collection: { version: 0, assignment_id: null, amount: null, currency: null, status: 'not_assigned', updated_at: null }, balances: [], financial_fingerprint: 'a'.repeat(64) } as any;
    vi.spyOn(orderWorkerAssignmentsApi, 'get').mockResolvedValue(workspace);
    vi.spyOn(orderWorkerAssignmentsApi, 'candidates').mockResolvedValue({ items: [{ staff_user_id: 9, display_name: 'Монтажник' }], total: 1, page: 1, limit: 100 });
    const assign = vi.spyOn(orderWorkerAssignmentsApi, 'assign').mockResolvedValue(workspace);
    wrapper = shallowMount(OrderEditDrawer, { props: { modelValue: false, order: stored, onUpdated: (order: ManagerOrderDetailResponse) => { void wrapper.setProps({ order }); } }, global: { components: { OrderWorkWorkspace }, stubs: { OrderAsyncPanel: false, OrderWorkWorkspace: false, OrderWorkerAssignmentsPanel: false } } });
    await wrapper.setProps({ modelValue: true }); await flushPromises();
    await openSection('work');
    await openCustomerContext();
    customer().vm.$emit('update:comment', 'Несохранённая информация менеджера'); await nextTick();
    const panel = wrapper.findComponent(OrderWorkerAssignmentsPanel); await panel.get('[aria-label="Исполнитель работы"]').setValue('9'); await panel.findAll('form')[0]!.trigger('submit'); await flushPromises();
    expect(ManagerOrdersService.patchManagerOrder).toHaveBeenCalled(); expect(assign).toHaveBeenCalledWith(stored.id, 9, null); expect(stored.comment).toBe('Несохранённая информация менеджера'); expect(customer().props('comment')).toBe('Несохранённая информация менеджера');
    expect(wrapper.props('order')).not.toHaveProperty('assignments'); managerSession.auth.value = null;
  });
});


describe('order page editor', () => {
  it('uses the page navigation guard once when leaving for the customer with manual saving', async () => {
    window.history.replaceState({}, '', '/manager/orders/395');
    await mountDrawer('page', true);
    customer().vm.$emit('update:editTarget', 'customer');
    await nextTick();
    header().vm.$emit('toggle-autosave');
    header().vm.$emit('update:title', 'Несохранённая правка');
    await nextTick();
    const { confirmDialog } = await import('../src/services/ui-feedback');
    vi.mocked(confirmDialog).mockClear().mockResolvedValueOnce(true);
    const unregister = registerUnsavedNavigationGuard(() => (wrapper.vm as any).prepareToLeave());
    const accept = vi.fn();
    const stopNavigation = startManagerNavigation(accept, () => window.location.pathname + window.location.search);
    try {
      await customer().get('[aria-label="Открыть полную карточку клиента"]').trigger('click');
      await flushPromises();
      expect(accept).toHaveBeenCalledOnce();
      expect(confirmDialog).toHaveBeenCalledOnce();
    } finally { unregister(); stopNavigation(); }
  });

  it('renders as a page without locking document scroll or trapping Escape', async () => {
    await mountDrawer('page');
    expect(wrapper.get('aside').attributes('role')).toBe('region');
    expect(wrapper.get('aside').attributes('aria-modal')).toBeUndefined();
    expect(document.documentElement.style.overflowX).not.toBe('hidden');
    await wrapper.get('aside').trigger('keydown', { key: 'Escape' });
    expect(wrapper.emitted('update:modelValue')).toBeUndefined();
  });
  it('flushes pending edits before page navigation without closing the editor itself', async () => {
    await mountDrawer('page');
    customer().vm.$emit('update:comment', 'Сохранить при возврате к доске');
    await nextTick();
    expect(await (wrapper.vm as any).prepareToLeave()).toBe(true);
    expect(stored.comment).toBe('Сохранить при возврате к доске');
    expect(wrapper.emitted('update:modelValue')).toBeUndefined();
  });
  it('blocks page navigation and keeps the draft on a save failure', async () => {
    await mountDrawer('page');
    vi.mocked(ManagerOrdersService.patchManagerOrder).mockRejectedValue(new Error('offline'));
    customer().vm.$emit('update:comment', 'Не потерять при ошибке');
    await nextTick();
    expect(await (wrapper.vm as any).prepareToLeave()).toBe(false);
    expect(customer().props('comment')).toBe('Не потерять при ошибке');
    expect(header().props('saveFailed')).toBe(true);
  });
});


describe('waiting save barrier', () => {
  it('saves the dirty drawer before opening waiting and preserves new input on conflict', async () => {
    stored.workflow_revision = 3;
    vi.mocked(ManagerOrdersService.patchManagerOrder).mockImplementation(async (_id, payload) => {
      const result = commit(payload); result.workflow_revision = 4; stored.workflow_revision = 4; return result;
    });
    const command = vi.spyOn(orderWaitingApi, 'command').mockRejectedValue({ status: 409, body: { detail: { message: 'Оплата изменена' } } });
    await mountDrawer('page', false, false);
    header().vm.$emit('update:title', 'Мой сохранённый заголовок'); await nextTick();
    header().vm.$emit('hold'); await flushPromises();
    expect(ManagerOrdersService.patchManagerOrder).toHaveBeenCalledWith(395, expect.objectContaining({ title: 'Мой сохранённый заголовок' }));
    const dialog = wrapper.getComponent(OrderWaitingDialog);
    expect(dialog.props('order')).toMatchObject({ workflow_revision: 4, title: 'Мой сохранённый заголовок' });
    header().vm.$emit('update:title', 'Новый ввод во время ожидания ответа'); await nextTick();
    dialog.vm.$emit('submit', { reason_code: 'other', note: 'Моя причина', next_followup_date: null }); await flushPromises();
    expect(command).toHaveBeenCalledExactlyOnceWith(395, expect.objectContaining({ expected_revision: 4, note: 'Моя причина' }));
    expect(header().props('title')).toBe('Новый ввод во время ожидания ответа');
    expect(dialog.props('error')).toContain('Оплата изменена');
    expect(header().props('dirty')).toBe(true);
  });
  it('invalidates an open waiting draft when the drawer switches order or closes', async () => {
    await mountDrawer('page', false, false);
    header().vm.$emit('hold'); await flushPromises();
    expect(wrapper.getComponent(OrderWaitingDialog).props('order')).toMatchObject({ id: 395 });
    await wrapper.setProps({ order: { ...stored, id: 396 } }); await flushPromises();
    expect(wrapper.getComponent(OrderWaitingDialog).props('order')).toBeNull();
    header().vm.$emit('hold'); await flushPromises();
    expect(wrapper.getComponent(OrderWaitingDialog).props('order')).toMatchObject({ id: 396 });
    await wrapper.setProps({ modelValue: false }); await flushPromises();
    expect(wrapper.getComponent(OrderWaitingDialog).props('order')).toBeNull();
  });
  it('ignores an old waiting command result after switching the open order', async () => {
    let resolve!: (order: ManagerOrderDetailResponse) => void;
    const pending = new Promise<ManagerOrderDetailResponse>(done => { resolve = done; });
    vi.spyOn(orderWaitingApi, 'command').mockReturnValue(pending);
    await mountDrawer('page', false, false);
    header().vm.$emit('hold'); await flushPromises();
    wrapper.getComponent(OrderWaitingDialog).vm.$emit('submit', { reason_code: 'next_stage' }); await flushPromises();
    await wrapper.setProps({ order: { ...stored, id: 396, title: 'Новый заказ' } }); await flushPromises();
    resolve({ ...stored, is_on_hold: true }); await flushPromises();
    expect(wrapper.props('order').id).toBe(396);
    expect(header().props('title')).toBe('Новый заказ');
    expect(wrapper.text()).not.toContain('Заказ в ожидании');
    expect(wrapper.getComponent(OrderWaitingDialog).props('order')).toBeNull();
  });
  it('never sends a hold command or opens its dialog after failed autosave', async () => {
    vi.mocked(ManagerOrdersService.patchManagerOrder).mockRejectedValue(new Error('Save offline'));
    const command = vi.spyOn(orderWaitingApi, 'command');
    await mountDrawer('page', false, false);
    header().vm.$emit('update:title', 'Не терять заголовок'); await nextTick();
    header().vm.$emit('hold'); await flushPromises();
    expect(command).not.toHaveBeenCalled();
    expect(wrapper.getComponent(OrderWaitingDialog).props('order')).toBeNull();
    expect(header().props('title')).toBe('Не терять заголовок');
  });
});
