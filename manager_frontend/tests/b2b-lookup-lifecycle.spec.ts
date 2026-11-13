import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { effectScope } from 'vue';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../src/api';
import { useB2BLookup } from '../src/composables/useB2BLookup';
import CreateCustomerModal from '../src/components/customers/CreateCustomerModal.vue';
import CustomerDetailsPanel from '../src/components/customers/CustomerDetailsPanel.vue';
import LeadQualifyModal from '../src/components/leads/LeadQualifyModal.vue';
import DocumentLegalEntitiesPanel from '../src/features/documents/settings/DocumentLegalEntitiesPanel.vue';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const companyResult = (name: string) => ({ row: { vnaimp: name, vpadres: `Address ${name}` } });
const bankResult = (name: string) => ({ name, bic: `${name}BIC` });
const wrappers: VueWrapper[] = [];
const scopes: ReturnType<typeof effectScope>[] = [];
const companyA = '123456789';
const companyB = '987654321';
const bankA = 'BY12AAAA00000000';
const bankB = 'BY12BBBB00000000';

beforeEach(() => {
  vi.spyOn(api, 'getCompanyByUnp').mockResolvedValue(companyResult('Current company'));
  vi.spyOn(api, 'getBankBySearch').mockResolvedValue(bankResult('Current bank'));
  vi.spyOn(api, 'getManagerCustomers').mockResolvedValue({ items: [], meta: { page: 1, limit: 10, total: 0, pages: 1 } });
  vi.spyOn(api, 'getManagerOrderScenarios').mockResolvedValue({ items: [] });
  vi.spyOn(api, 'getManagerCustomerBranches').mockResolvedValue({ items: [] } as never);
  vi.spyOn(console, 'error').mockImplementation(() => {});
});
afterEach(() => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount());
  scopes.splice(0).forEach(scope => scope.stop());
  vi.restoreAllMocks();
});

for (const kind of ['company', 'bank'] as const) {
  describe(`shared ${kind} lookup ownership`, () => {
    function setup() {
      const scope = effectScope();
      scopes.push(scope);
      const lookup = scope.run(useB2BLookup)!;
      return {
        scope,
        run: kind === 'company' ? lookup.lookupCompany : lookup.lookupBank,
        api: kind === 'company' ? vi.mocked(api.getCompanyByUnp) : vi.mocked(api.getBankBySearch),
        loading: kind === 'company' ? lookup.isEgrLoading : lookup.isBankLoading,
        error: kind === 'company' ? lookup.egrError : lookup.bankError,
        result: kind === 'company' ? companyResult : bankResult,
        a: kind === 'company' ? companyA : bankA,
        b: kind === 'company' ? companyB : bankB,
      };
    }
    it.each(['resolve', 'reject'] as const)('ignores an older %s while the current lookup is pending', async outcome => {
      const subject = setup();
      const old = deferred<any>();
      const current = deferred<any>();
      subject.api.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
      const first = subject.run(subject.a);
      const second = subject.run(subject.b);
      if (outcome === 'resolve') old.resolve(subject.result('Old'));
      else old.reject(new Error('Old failure'));
      expect(await first).toBeNull();
      expect(subject.loading.value).toBe(true);
      expect(subject.error.value).toBe('');
      current.resolve(subject.result('Current'));
      expect(await second).toBeTruthy();
      expect(subject.loading.value).toBe(false);
    });
    it('keeps the latest error when an older successful response arrives last', async () => {
      const subject = setup();
      const old = deferred<any>();
      const current = deferred<any>();
      subject.api.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
      const first = subject.run(subject.a);
      const second = subject.run(subject.b);
      current.reject(new Error('Current failure'));
      expect(await second).toBeNull();
      expect(subject.error.value).toContain('Current failure');
      old.resolve(subject.result('Old'));
      expect(await first).toBeNull();
      expect(subject.error.value).toContain('Current failure');
    });
    it('invalidates a pending request when the next lookup input is invalid', async () => {
      const subject = setup();
      const old = deferred<any>();
      subject.api.mockReturnValueOnce(old.promise);
      const first = subject.run(subject.a);
      expect(await subject.run('')).toBeNull();
      expect(subject.loading.value).toBe(false);
      old.resolve(subject.result('Old'));
      expect(await first).toBeNull();
      expect(subject.error.value).toBe('');
    });
    it('invalidates pending results when its owner is disposed', async () => {
      const subject = setup();
      const old = deferred<any>();
      subject.api.mockReturnValueOnce(old.promise);
      const first = subject.run(subject.a);
      subject.scope.stop();
      expect(subject.loading.value).toBe(false);
      old.resolve(subject.result('Old'));
      expect(await first).toBeNull();
    });
  });
}

type Caller = 'create' | 'details' | 'lead' | 'seller';
const customer = { id: 7, name: 'Customer', type: 'company', inn: companyA, order_count: 0 };
const lead = { id: 7, customer_type: 'company', customer_inn: companyA, customer_name: '', attachment_count: 0 };
const seller = (id: number) => ({ id, display_name: 'Seller', legal_name: '', unp: companyA, entity_type: 'organization', requisites: { iban: bankA }, status: 'active' });
const globalOptions = { stubs: { teleport: true, transition: false, AddressSuggestInput: true, RegistrationCertificatePanel: true, OrderAttachmentsPanel: true } };
const button = (wrapper: VueWrapper, label: string) => wrapper.findAll('button').find(item => item.text() === label)!;
const labelledInput = (wrapper: VueWrapper, label: string) => wrapper.findAll('label').find(item => item.text().trim().startsWith(label))!.get('input');

async function mountCaller(kind: Caller) {
  let wrapper: VueWrapper;
  if (kind === 'create') {
    wrapper = mount(CreateCustomerModal, { global: globalOptions });
    await wrapper.findAll('button').find(item => item.text().includes('Юрлицо'))!.trigger('click');
  } else if (kind === 'details') {
    wrapper = mount(CustomerDetailsPanel, { props: { customer: customer as never }, global: globalOptions });
    await button(wrapper, 'Изменить').trigger('click');
  } else if (kind === 'lead') {
    wrapper = mount(LeadQualifyModal, { props: { lead: lead as never }, global: globalOptions });
    await wrapper.findAll('button').find(item => item.text().includes('Реквизиты бизнеса'))!.trigger('click');
  } else {
    wrapper = mount(DocumentLegalEntitiesPanel, { props: { items: [seller(7)] as never, selectedId: 7, loading: false, saving: false }, global: globalOptions });
  }
  wrappers.push(wrapper);
  await flushPromises();
  return {
    wrapper,
    companyInput: () => kind === 'create' ? wrapper.get('input[placeholder="123456789"]') : kind === 'details' ? wrapper.get('input[inputmode="numeric"]') : kind === 'lead' ? wrapper.get('input[placeholder="9 цифр"]') : wrapper.get('[data-testid="seller-unp"]'),
    companyOutput: () => kind === 'create' ? wrapper.get('input[placeholder="Заполнится по УНП или вручную"]') : kind === 'details' ? wrapper.get('input[placeholder="Полное наименование"]') : kind === 'lead' ? labelledInput(wrapper, 'Полное юридическое название') : wrapper.get('[data-testid="seller-legal-name"]'),
    bankInput: () => kind === 'details' ? wrapper.get('input[placeholder="IBAN"]') : kind === 'lead' ? labelledInput(wrapper, 'IBAN') : wrapper.get('[data-testid="seller-iban"]'),
    bankOutput: () => kind === 'details' ? wrapper.get('input[placeholder="Название банка"]') : kind === 'lead' ? labelledInput(wrapper, 'Банк') : wrapper.get('[data-testid="seller-bank-name"]'),
    async changeTypeAndBack() {
      if (kind === 'seller') {
        await button(wrapper, 'ИП').trigger('click');
        await button(wrapper, 'Организация').trigger('click');
      } else if (kind === 'details') {
        await wrapper.get('[aria-label="Тип клиента"]').findAll('button')[0]!.trigger('click');
        await wrapper.get('[aria-label="Тип клиента"]').findAll('button')[2]!.trigger('click');
      } else {
        await wrapper.findAll('button').find(item => item.text().includes('Физлицо'))!.trigger('click');
        await wrapper.findAll('button').find(item => item.text().includes('Юрлицо'))!.trigger('click');
      }
    },
    async resetSession() {
      if (kind === 'create') await button(wrapper, 'Отмена').trigger('click');
      else if (kind === 'details') {
        await button(wrapper, 'Отмена').trigger('click');
        await button(wrapper, 'Изменить').trigger('click');
      } else if (kind === 'lead') await wrapper.setProps({ lead: { ...lead, id: 8 } });
      else await wrapper.setProps({ items: [seller(8)], selectedId: 8 });
    },
  };
}
const value = (input: ReturnType<Awaited<ReturnType<typeof mountCaller>>['companyInput']>) => (input.element as HTMLInputElement).value;

for (const kind of ['create', 'details', 'lead', 'seller'] as const) {
  describe(`${kind} company autofill lifecycle`, () => {
    it('does not apply a response after input changes without a second blur', async () => {
      const old = deferred<any>();
      vi.mocked(api.getCompanyByUnp).mockReturnValueOnce(old.promise);
      const subject = await mountCaller(kind);
      await subject.companyInput().setValue(companyA);
      await subject.companyInput().trigger('blur');
      await subject.companyInput().setValue(companyB);
      expect(subject.wrapper.find('.animate-spin').exists()).toBe(false);
      old.resolve(companyResult('Old company'));
      await flushPromises();
      expect(value(subject.companyOutput())).toBe('');
      expect(subject.wrapper.find('.animate-spin').exists()).toBe(false);
    });
    it.each([true, false])('keeps the current lookup when old response arrives first: %s', async oldFirst => {
      const old = deferred<any>();
      const current = deferred<any>();
      vi.mocked(api.getCompanyByUnp).mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
      const subject = await mountCaller(kind);
      await subject.companyInput().setValue(companyA);
      await subject.companyInput().trigger('blur');
      await subject.companyInput().setValue(companyB);
      await subject.companyInput().trigger('blur');
      if (oldFirst) {
        old.resolve(companyResult('Old company'));
        await flushPromises();
        expect(value(subject.companyOutput())).toBe('');
        current.resolve(companyResult('Current company'));
      } else {
        current.resolve(companyResult('Current company'));
        await flushPromises();
        old.resolve(companyResult('Old company'));
      }
      await flushPromises();
      expect(value(subject.companyOutput())).toBe('Current company');
    });
    it('does not revive an old response after input changes A to B to A', async () => {
      const old = deferred<any>();
      vi.mocked(api.getCompanyByUnp).mockReturnValueOnce(old.promise);
      const subject = await mountCaller(kind);
      await subject.companyInput().setValue(companyA);
      await subject.companyInput().trigger('blur');
      await subject.companyInput().setValue(companyB);
      await subject.companyInput().setValue(companyA);
      old.resolve(companyResult('Old company'));
      await flushPromises();
      expect(value(subject.companyOutput())).toBe('');
    });
    it('invalidates a response across a customer type round trip', async () => {
      const old = deferred<any>();
      vi.mocked(api.getCompanyByUnp).mockReturnValueOnce(old.promise);
      const subject = await mountCaller(kind);
      await subject.companyInput().setValue(companyA);
      await subject.companyInput().trigger('blur');
      await subject.changeTypeAndBack();
      old.resolve(companyResult('Old company'));
      await flushPromises();
      expect(value(subject.companyOutput())).toBe('');
    });
    it('invalidates a response across sessions even when the UNP stays the same', async () => {
      const old = deferred<any>();
      vi.mocked(api.getCompanyByUnp).mockReturnValueOnce(old.promise);
      const subject = await mountCaller(kind);
      await subject.companyInput().setValue(companyA);
      await subject.companyInput().trigger('blur');
      await subject.resetSession();
      old.resolve(companyResult('Old company'));
      await flushPromises();
      expect(value(subject.companyOutput())).toBe('');
    });
  });
}

for (const kind of ['details', 'lead', 'seller'] as const) {
  describe(`${kind} bank autofill lifecycle`, () => {
    it('does not apply a response after IBAN changes without a second blur', async () => {
      const old = deferred<any>();
      vi.mocked(api.getBankBySearch).mockReturnValueOnce(old.promise);
      const subject = await mountCaller(kind);
      await subject.bankInput().setValue(bankA);
      await subject.bankInput().trigger('blur');
      await subject.bankInput().setValue(bankB);
      expect(subject.wrapper.find('.animate-spin').exists()).toBe(false);
      old.resolve(bankResult('Old bank'));
      await flushPromises();
      expect(value(subject.bankOutput())).toBe('');
      expect(subject.wrapper.find('.animate-spin').exists()).toBe(false);
    });
    it('ignores the older response while a current bank lookup is pending', async () => {
      const old = deferred<any>();
      const current = deferred<any>();
      vi.mocked(api.getBankBySearch).mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
      const subject = await mountCaller(kind);
      await subject.bankInput().setValue(bankA);
      await subject.bankInput().trigger('blur');
      await subject.bankInput().setValue(bankB);
      await subject.bankInput().trigger('blur');
      old.resolve(bankResult('Old bank'));
      await flushPromises();
      expect(value(subject.bankOutput())).toBe('');
      expect(subject.wrapper.find('.animate-spin').exists()).toBe(true);
      current.resolve(bankResult('Current bank'));
      await flushPromises();
      expect(value(subject.bankOutput())).toBe('Current bank');
    });
    it('invalidates a response across sessions even when the IBAN stays the same', async () => {
      const old = deferred<any>();
      vi.mocked(api.getBankBySearch).mockReturnValueOnce(old.promise);
      const subject = await mountCaller(kind);
      await subject.bankInput().setValue(bankA);
      await subject.bankInput().trigger('blur');
      await subject.resetSession();
      old.resolve(bankResult('Old bank'));
      await flushPromises();
      expect(value(subject.bankOutput())).toBe('');
    });
  });
}


describe('current lookup behavior', () => {
  it('keeps company and bank loading independent', async () => {
    const pendingCompany = deferred<any>();
    const pendingBank = deferred<any>();
    vi.mocked(api.getCompanyByUnp).mockReturnValueOnce(pendingCompany.promise);
    vi.mocked(api.getBankBySearch).mockReturnValueOnce(pendingBank.promise);
    const scope = effectScope();
    scopes.push(scope);
    const lookup = scope.run(useB2BLookup)!;
    const company = lookup.lookupCompany(companyA);
    const bank = lookup.lookupBank(bankA);
    pendingBank.resolve(bankResult('Bank'));
    await bank;
    expect(lookup.isBankLoading.value).toBe(false);
    expect(lookup.isEgrLoading.value).toBe(true);
    pendingCompany.resolve(companyResult('Company'));
    await company;
    expect(lookup.isEgrLoading.value).toBe(false);
  });

  it.each(['create', 'details', 'lead', 'seller'] as const)('%s preserves its legal name overwrite/fill-empty behavior', async kind => {
    const subject = await mountCaller(kind);
    await subject.companyInput().setValue(companyA);
    await subject.companyOutput().setValue('Manual company');
    await subject.companyInput().trigger('blur');
    await flushPromises();
    expect(value(subject.companyOutput())).toBe(kind === 'create' ? 'Current company' : 'Manual company');
  });

  it.each(['details', 'lead', 'seller'] as const)('%s preserves manually entered bank details', async kind => {
    const subject = await mountCaller(kind);
    await subject.bankInput().setValue(bankA);
    await subject.bankOutput().setValue('Manual bank');
    await subject.bankInput().trigger('blur');
    await flushPromises();
    expect(value(subject.bankOutput())).toBe('Manual bank');
  });

  it.each(['create', 'seller'] as const)('%s clears current errors when input changes and hides stale errors', async kind => {
    const subject = await mountCaller(kind);
    vi.mocked(api.getCompanyByUnp).mockRejectedValueOnce(new Error('Current failure'));
    await subject.companyInput().setValue(companyA);
    await subject.companyInput().trigger('blur');
    await flushPromises();
    expect(subject.wrapper.text()).toContain('Current failure');
    const old = deferred<any>();
    vi.mocked(api.getCompanyByUnp).mockReturnValueOnce(old.promise);
    await subject.companyInput().trigger('blur');
    await subject.companyInput().setValue(companyB);
    expect(subject.wrapper.text()).not.toContain('Current failure');
    old.reject(new Error('Stale failure'));
    await flushPromises();
    expect(subject.wrapper.text()).not.toContain('Stale failure');
  });

  it('invalidates customer details lookup when another customer has the same UNP', async () => {
    const old = deferred<any>();
    vi.mocked(api.getCompanyByUnp).mockReturnValueOnce(old.promise);
    const subject = await mountCaller('details');
    await subject.companyInput().trigger('blur');
    await subject.wrapper.setProps({ customer: { ...customer, id: 8 } });
    old.resolve(companyResult('Old customer'));
    await flushPromises();
    expect(value(subject.companyOutput())).toBe('');
  });

  it('invalidates lead lookup as soon as the dialog closes', async () => {
    const old = deferred<any>();
    vi.mocked(api.getCompanyByUnp).mockReturnValueOnce(old.promise);
    const subject = await mountCaller('lead');
    await subject.companyInput().trigger('blur');
    await button(subject.wrapper, 'close').trigger('click');
    old.resolve(companyResult('Old customer'));
    await flushPromises();
    expect(value(subject.companyOutput())).toBe('');
    expect(subject.wrapper.emitted('close')).toHaveLength(1);
  });
});
