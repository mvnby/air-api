import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../src/api';
import { ManagerDocumentSystemService, ManagerService, OpenAPI } from '../src/client';
import EnvelopePrintDialog from '../src/components/envelopes/EnvelopePrintDialog.vue';
import { envelopeAddresses, splitPostalAddress } from '../src/components/envelopes/envelope-addresses';
import * as printing from '../src/components/envelopes/envelope-print-api';
import OrderWorkspaceHeader from '../src/components/orders/OrderWorkspaceHeader.vue';
import PostcodeLookup from '../src/components/envelopes/PostcodeLookup.vue';

const customer = { id: 7, name: 'Клиент', full_legal_name: 'ООО Клиент', legal_address: '220030, г. Минск, ул. Ленина, 1', actual_address: 'г. Минск, ул. Ленина, 2', branches: [{ id: 9, name: 'Филиал', delivery_address: '210001, г. Витебск, ул. Доватора, 2' }] };
const entity = { id: 2, display_name: 'Наша компания', legal_name: 'ООО Отправитель', status: 'active', is_default: true, requisites: { legal_address: '220004, г. Минск, ул. Тестовая, 3' } };
let wrapper: VueWrapper | undefined;
beforeEach(() => {
  vi.spyOn(api, 'getManagerCustomerDetail').mockResolvedValue(customer as never);
  vi.spyOn(ManagerDocumentSystemService, 'listManagerDocumentLegalEntities').mockResolvedValue({ items: [entity] } as never);
  vi.spyOn(ManagerService, 'previewManagerCustomerEnvelope').mockImplementation(async (_id, payload) => ({
    sender: { delivery_lines: [payload.sender.address], postal_line: `${payload.sender.postal_code}, г. Минск`, area_lines: [], country: 'Республика Беларусь', warnings: [] },
    recipient: { delivery_lines: ['ул. Ленина, 1'], postal_line: `${payload.recipient.postal_code}, г. Минск`, area_lines: [], country: 'Республика Беларусь', warnings: [] },
  }));
});
afterEach(() => { wrapper?.unmount(); wrapper = undefined; document.body.replaceChildren(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
async function open() {
  wrapper = mount(EnvelopePrintDialog, { attachTo: document.body, props: { customerId: 7, orderAddress: 'г. Минск, ул. Объектная, 5' } });
  await vi.waitFor(() => expect(document.querySelector('.envelope-dialog form')).not.toBeNull());
  return new DOMWrapper(document.querySelector<HTMLElement>('.envelope-dialog')!);
}

describe('envelope preparation', () => {
  it('defaults to DL and changes format, preview proportions and download without losing one-time data', async () => {
    const download = vi.spyOn(printing, 'downloadEnvelope').mockResolvedValue(new Blob(['%PDF-test']));
    vi.stubGlobal('URL', { createObjectURL: vi.fn().mockReturnValue('blob:test'), revokeObjectURL: vi.fn() });
    const filenames: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) { filenames.push(this.download); });
    const w = await open();
    expect((w.get('#envelope-format').element as HTMLSelectElement).value).toBe('DL');
    expect(w.get('#envelope-format').text()).toContain('C5 · 229 × 162 мм — A4, сложенный пополам');
    await w.get('#envelope-recipient-address').setValue('г. Минск, ул. Домашняя, д. 8');
    await w.get('#envelope-recipient-index').setValue('220040');
    await w.get('#envelope-brand-name').setValue('Разовая подпись');
    for (const [code, width, height] of [['C6', 162, 114], ['C5', 229, 162], ['C4', 324, 229], ['DL', 220, 110]] as const) {
      await w.get('#envelope-format').setValue(code);
      expect(w.get('.envelope-preview').attributes('style')).toContain(`aspect-ratio: ${width} / ${height}`);
      expect(w.get('header p').text()).toContain(`${code} · ${width} × ${height} мм`);
      await w.get('form').trigger('submit'); await flushPromises();
      expect(download).toHaveBeenLastCalledWith(7, expect.objectContaining({
        format: code, recipient: { name: 'ООО Клиент', address: 'г. Минск, ул. Домашняя, д. 8', postal_code: '220040' },
        branding: { name: 'Разовая подпись', logo_data_url: null },
      }));
      expect(filenames.at(-1)).toBe(`envelope-${code.toLowerCase()}-7.pdf`);
    }
  });
  it('waits for logo decoding and ignores an old upload after switching the sender', async () => {
    let finish!: () => void;
    vi.stubGlobal('Image', class {
      src = ''; naturalWidth = 80; naturalHeight = 30;
      decode() { return new Promise<void>(resolve => { finish = resolve; }); }
    });
    vi.mocked(ManagerDocumentSystemService.listManagerDocumentLegalEntities).mockResolvedValue({ items: [
      entity, { ...entity, id: 3, is_default: false, envelope_branding: { name: 'Вторая марка' } },
    ] } as never);
    const w = await open();
    await w.get('#envelope-address').setValue('legal');
    const input = w.get('#envelope-brand-logo');
    Object.defineProperty(input.element, 'files', { value: [new File(['png'], 'logo.png', { type: 'image/png' })], configurable: true });
    await input.trigger('change');
    await vi.waitFor(() => expect(finish).toBeTypeOf('function'));
    expect(w.get('button[type="submit"]').attributes('disabled')).toBeDefined();
    await w.get('#envelope-sender').setValue('3');
    finish(); await flushPromises();
    expect(w.get('.preview-branding strong').text()).toBe('Вторая марка');
    expect(w.find('.preview-branding img').exists()).toBe(false);
    expect(w.get('button[type="submit"]').attributes('disabled')).toBeUndefined();
  });
  it('automatically fills each sender branding, preserves saved defaults, and clears them for a custom sender', async () => {
    const saved = { name: 'Первая марка', logo_data_url: 'data:image/png;base64,dGVzdA==' };
    vi.mocked(ManagerDocumentSystemService.listManagerDocumentLegalEntities).mockResolvedValue({ items: [
      { ...entity, envelope_branding: saved },
      { ...entity, id: 3, is_default: false, display_name: 'Вторая компания', envelope_branding: { name: 'Вторая марка', logo_data_url: null } },
    ] } as never);
    const download = vi.spyOn(printing, 'downloadEnvelope').mockRejectedValue(new Error('offline'));
    const w = await open();
    await w.get('#envelope-address').setValue('legal');
    expect(w.get('.preview-branding strong').text()).toBe('Первая марка');
    expect(w.get('.preview-branding img').attributes('src')).toBe(saved.logo_data_url);
    await w.get('#envelope-brand-name').setValue('Разовая подпись');
    await w.get('form').trigger('submit'); await flushPromises();
    expect(download).toHaveBeenCalledWith(7, expect.objectContaining({ branding: { ...saved, name: 'Разовая подпись' } }));
    await w.get('#envelope-sender').setValue('3');
    expect(w.get('.preview-branding strong').text()).toBe('Вторая марка');
    expect(w.find('.preview-branding img').exists()).toBe(false);
    await w.get('#envelope-sender').setValue('2');
    expect(w.get('.preview-branding strong').text()).toBe('Первая марка');
    expect(saved.name).toBe('Первая марка');
    await w.get('#envelope-sender').setValue('');
    expect(w.find('.preview-branding').exists()).toBe(false);
  });
  it('extracts only an unambiguous standalone postcode', () => {
    expect(splitPostalAddress('Беларусь, 220030, Минск')).toEqual({ address: 'Беларусь, Минск', postal_code: '220030' });
    expect(splitPostalAddress('220030, г. Минск')).toEqual({ address: 'г. Минск', postal_code: '220030' });
    expect(splitPostalAddress('ул. Тестовая, 1234567').postal_code).toBe('');
    expect(splitPostalAddress('220030, Минск, 220004').postal_code).toBe('');
  });
  it('offers legal, postal, branch and order addresses and requires a selection', async () => {
    const w = await open();
    const choices = w.get('#envelope-address');
    expect(choices.text()).toContain('Юридический адрес');
    expect(choices.text()).toContain('Фактический / почтовый адрес');
    expect(choices.text()).toContain('Филиал');
    expect(choices.text()).toContain('Адрес из заказа');
    expect(w.get('button[type="submit"]').attributes('disabled')).toBeDefined();
    await choices.setValue('legal');
    expect((w.get('#envelope-recipient-index').element as HTMLInputElement).value).toBe('220030');
    expect((w.get('#envelope-recipient-address').element as HTMLTextAreaElement).value).not.toContain('220030');
    expect(w.get('button[type="submit"]').attributes('disabled')).toBeUndefined();
    await choices.setValue('actual');
    expect((w.get('#envelope-recipient-index').element as HTMLInputElement).value).toBe('');
    expect(w.text()).toContain('индекс получателя (6 цифр)');
    expect(w.get('button[type="submit"]').attributes('disabled')).toBeDefined();
  });
  it('deduplicates saved addresses', () => {
    const choices = envelopeAddresses({ ...customer, actual_address: ` ${customer.legal_address} ` } as never, customer.legal_address);
    expect(choices).toHaveLength(2);
  });
  it('prints a one-time manually typed address without first selecting a saved one', async () => {
    const download = vi.spyOn(printing, 'downloadEnvelope').mockResolvedValue(new Blob(['%PDF-test']));
    vi.stubGlobal('URL', { createObjectURL: vi.fn().mockReturnValue('blob:test'), revokeObjectURL: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const w = await open();
    await w.get('#envelope-recipient-name').setValue('Директор лично');
    await w.get('#envelope-recipient-address').setValue('г. Минск, ул. Домашняя, д. 8, кв. 15');
    await w.get('#envelope-recipient-index').setValue('220040');
    expect((w.get('#envelope-address').element as HTMLSelectElement).value).toBe('custom');
    expect(w.get('button[type="submit"]').attributes('disabled')).toBeUndefined();
    expect((w.get('form').element as HTMLFormElement).checkValidity()).toBe(true);
    await w.get('form').trigger('submit'); await flushPromises();
    expect(download).toHaveBeenCalledWith(7, expect.objectContaining({ recipient: { name: 'Директор лично', address: 'г. Минск, ул. Домашняя, д. 8, кв. 15', postal_code: '220040' } }));
    expect(customer.legal_address).toBe('220030, г. Минск, ул. Ленина, 1');
  });
  it('keeps a selected address when switching to manual editing', async () => {
    const w = await open();
    await w.get('#envelope-address').setValue('legal');
    await w.get('#envelope-address').setValue('custom');
    expect((w.get('#envelope-recipient-address').element as HTMLTextAreaElement).value).toBe('г. Минск, ул. Ленина, 1');
    await w.get('#envelope-recipient-address').setValue('г. Минск, ул. Ленина, 2');
    expect(w.get('button[type="submit"]').attributes('disabled')).toBeUndefined();
  });
  it('uses server-normalized postal lines in the preview and includes optional branding in PDF', async () => {
    const download = vi.spyOn(printing, 'downloadEnvelope').mockRejectedValue(new Error('offline'));
    const w = await open();
    await w.get('#envelope-address').setValue('legal');
    await vi.waitFor(() => expect(w.get('.preview-recipient').text()).toContain('220030, г. Минск'));
    expect(w.get('.preview-recipient strong').text()).toBe('ООО Клиент');
    await w.get('#envelope-brand-name').setValue('Наша организация');
    expect(w.get('.preview-branding').text()).toBe('Наша организация');
    await w.get('form').trigger('submit'); await flushPromises();
    expect(download).toHaveBeenCalledWith(7, expect.objectContaining({ branding: { name: 'Наша организация', logo_data_url: null } }));
  });
  it('discards preview responses for an address edited while the request was running', async () => {
    let resolve!: (value: any) => void;
    vi.mocked(ManagerService.previewManagerCustomerEnvelope).mockReturnValueOnce(new Promise(done => { resolve = done; }) as never);
    const w = await open();
    await w.get('#envelope-address').setValue('legal');
    await vi.waitFor(() => expect(ManagerService.previewManagerCustomerEnvelope).toHaveBeenCalledOnce());
    await w.get('#envelope-recipient-address').setValue('г. Минск, ул. Новая, 5');
    resolve({ sender: {}, recipient: { postal_line: '999999, Старый адрес', delivery_lines: [], area_lines: [], country: 'Беларусь', warnings: [] } });
    await flushPromises();
    expect(w.get('.preview-recipient').text()).not.toContain('Старый адрес');
  });
  it('allows missing address and sender details to be completed manually', async () => {
    vi.mocked(api.getManagerCustomerDetail).mockResolvedValue({ ...customer, legal_address: null, actual_address: null, branches: [] } as never);
    vi.mocked(ManagerDocumentSystemService.listManagerDocumentLegalEntities).mockRejectedValue(new Error('offline'));
    const w = await open();
    await w.get('#envelope-address').setValue('custom');
    await w.get('#envelope-recipient-address').setValue('г. Минск, ул. Новая, 5');
    await w.get('#envelope-recipient-index').setValue('220030');
    await w.get('#envelope-sender-name').setValue('Иван Иванов');
    await w.get('#envelope-sender-address').setValue('г. Минск, ул. Старая, 6');
    await w.get('#envelope-sender-index').setValue('220004');
    expect(w.get('button[type="submit"]').attributes('disabled')).toBeUndefined();
    expect(w.text()).toContain('Заполните данные вручную');
  });
  it('submits reviewed data and preserves edits when PDF generation fails', async () => {
    const download = vi.spyOn(printing, 'downloadEnvelope').mockRejectedValue(new Error('Получатель: текст не помещается'));
    const w = await open();
    await w.get('#envelope-address').setValue('legal');
    await w.get('#envelope-recipient-name').setValue('Для бухгалтерии');
    await w.get('form').trigger('submit'); await flushPromises();
    expect(download).toHaveBeenCalledWith(7, expect.objectContaining({ format: 'DL', recipient: { name: 'Для бухгалтерии', address: 'г. Минск, ул. Ленина, 1', postal_code: '220030' } }));
    expect(w.get('[role="alert"]').text()).toContain('текст не помещается');
    expect((w.get('#envelope-recipient-name').element as HTMLInputElement).value).toBe('Для бухгалтерии');
    expect(w.get('button[type="submit"]').attributes('disabled')).toBeUndefined();
  });
  it('contains Escape within the print dialog', async () => {
    const w = await open();
    await w.trigger('keydown', { key: 'Escape' });
    expect(wrapper!.emitted('close')).toHaveLength(1);
  });
  it('requests Belpost only on demand and applies only the explicitly selected postcode', async () => {
    const search = vi.spyOn(ManagerService, 'lookupManagerCustomerPostcodes').mockResolvedValue({ items: [
      { postal_code: '220030', address: 'Минск, ул. Ленина', buildings: '2, 3, 4' },
      { postal_code: '220008', address: 'Минск, ул. Ленина', buildings: '14' },
    ], source: 'Белпочта' });
    const w = await open();
    await w.get('#envelope-address').setValue('actual');
    expect(search).not.toHaveBeenCalled();
    const lookup = wrapper!.findAllComponents(PostcodeLookup)[0]!;
    await lookup.get('.lookup-toggle').trigger('click');
    await lookup.get('input').setValue('Минск, улица Ленина');
    await lookup.get('.btn-mini-outline').trigger('click'); await flushPromises();
    expect(search).toHaveBeenCalledWith(7, { address: 'Минск, улица Ленина' });
    expect((w.get('#envelope-recipient-index').element as HTMLInputElement).value).toBe('');
    expect(lookup.text()).toContain('Дома: 14');
    await lookup.findAll('li button')[1]!.trigger('click');
    expect((w.get('#envelope-recipient-index').element as HTMLInputElement).value).toBe('220008');
  });
  it('ignores postcode results for an address changed during the lookup', async () => {
    let resolve!: (value: any) => void;
    vi.spyOn(ManagerService, 'lookupManagerCustomerPostcodes').mockReturnValue(new Promise(done => { resolve = done; }) as never);
    const w = await open(); await w.get('#envelope-address').setValue('actual');
    const lookup = wrapper!.findAllComponents(PostcodeLookup)[0]!;
    await lookup.get('.lookup-toggle').trigger('click');
    await lookup.get('.btn-mini-outline').trigger('click');
    await w.get('#envelope-address').setValue('legal');
    resolve({ items: [{ postal_code: '999999', address: 'Старый адрес', buildings: '1' }] }); await flushPromises();
    expect(lookup.findAll('li')).toHaveLength(0);
    expect((w.get('#envelope-recipient-index').element as HTMLInputElement).value).toBe('220030');
  });
  it('keeps manual postcode entry available after a provider error', async () => {
    vi.spyOn(ManagerService, 'lookupManagerCustomerPostcodes').mockRejectedValue(new Error('Справочник недоступен'));
    const w = await open(); await w.get('#envelope-address').setValue('actual');
    const lookup = wrapper!.findAllComponents(PostcodeLookup)[0]!;
    await lookup.get('.lookup-toggle').trigger('click'); await lookup.get('.btn-mini-outline').trigger('click'); await flushPromises();
    expect(lookup.get('[role="alert"]').text()).toContain('недоступен');
    await w.get('#envelope-recipient-index').setValue('220030');
    expect(w.get('button[type="submit"]').attributes('disabled')).toBeUndefined();
  });
  it('sends authenticated PDF requests and returns the response blob', async () => {
    const oldToken = OpenAPI.TOKEN;
    OpenAPI.TOKEN = 'test-token';
    const blob = new Blob(['%PDF-test'], { type: 'application/pdf' });
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, blob: async () => blob });
    vi.stubGlobal('fetch', fetchMock);
    try {
      const party = { name: 'Тест', address: 'Минск, ул. Тестовая, 1', postal_code: '220030' };
      expect(await printing.downloadEnvelope(7, { sender: party, recipient: party })).toBe(blob);
      expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/customers/7/envelope-pdf'), expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer test-token' }), credentials: expect.any(String) }));
    } finally { OpenAPI.TOKEN = oldToken; }
  });
  it('opens printing from the order action menu when a customer is selected', async () => {
    wrapper = mount(OrderWorkspaceHeader, { props: {
      title: 'Заказ', workflow: 'supply', viewModel: { stageLabel: 'Новый', nextAction: { label: 'Продолжить' } } as never,
      total: 0, paid: 0, balance: 0, canPrintEnvelope: true,
    } });
    await wrapper.get('[aria-label="Дополнительные действия"]').trigger('click');
    await wrapper.findAll('button').find(button => button.text() === 'Печать конверта')!.trigger('click');
    expect(wrapper.emitted('envelope')).toHaveLength(1);
    await wrapper.setProps({ canPrintEnvelope: false });
    await wrapper.get('[aria-label="Дополнительные действия"]').trigger('click');
    expect(wrapper.findAll('button').some(button => button.text() === 'Печать конверта')).toBe(false);
  });
});
