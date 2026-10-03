import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { nextTick } from 'vue';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManagerService } from '../src/client';
import CustomerIntakeDialog from '../src/components/customers/CustomerIntakeDialog.vue';

const customer = {
  id: 7, name: 'ООО Исходное', type: 'company', inn: '123456789',
  phone: '+375291112233', bank_name: 'Старый банк', order_count: 0,
};
const recognition = (duplicate_customer: unknown = null) => ({
  id: 91, source: 'manager', status: 'recognized', raw_text: 'ООО Исходное УНП 123456789',
  extracted: { name: 'ООО Исходное', customer_type: 'company', inn: '123456789', bank_name: 'Новый банк' },
  validation_flags: { field_errors: {}, warnings: {}, is_valid: true },
  duplicate_customer,
});
const wrappers: VueWrapper[] = [];

function mountDialog() {
  const wrapper = mount(CustomerIntakeDialog, {
    props: { customer: customer as never },
    attachTo: document.body,
    global: { stubs: { transition: false, CreateCustomerModal: true } },
  });
  wrappers.push(wrapper);
  return wrapper;
}
function dialog() { return new DOMWrapper(document.body.querySelector('[role="dialog"]')!); }
async function enterDraft() {
  await dialog().get('textarea').setValue('ООО Исходное УНП 123456789');
  const recognize = dialog().findAll('button').find((button) => button.text() === 'Распознать');
  expect(recognize).toBeDefined();
  await recognize!.trigger('click');
  await flushPromises();
  await nextTick();
  expect(ManagerService.recognizeManagerCustomerRequisitesText).toHaveBeenCalled();
  expect(ManagerService.getManagerCustomerDetail).toHaveBeenCalled();
}

beforeEach(() => {
  vi.spyOn(ManagerService, 'recognizeManagerCustomerRequisitesText').mockResolvedValue(recognition() as never);
  vi.spyOn(ManagerService, 'getManagerCustomerDetail').mockResolvedValue(customer as never);
  vi.spyOn(ManagerService, 'confirmManagerCustomerRequisites').mockResolvedValue({ customer } as never);
});
afterEach(() => { wrappers.splice(0).forEach((wrapper) => wrapper.unmount()); vi.restoreAllMocks(); });

describe('CustomerIntakeDialog', () => {
  it('saves corrected selected fields with their original values', async () => {
    const wrapper = mountDialog();
    await enterDraft();
    await dialog().get('input[aria-label="Банк"]').setValue('Исправленный банк');
    await dialog().get('button[type="submit"]').trigger('click');
    await flushPromises();

    expect(ManagerService.recognizeManagerCustomerRequisitesText).toHaveBeenCalledWith({ text: 'ООО Исходное УНП 123456789' });
    expect(ManagerService.confirmManagerCustomerRequisites).toHaveBeenCalledWith(91, expect.objectContaining({
      action: 'update', customer_id: 7, selected_fields: ['bank_name'],
      baseline: { bank_name: 'Старый банк' }, extracted: { bank_name: 'Исправленный банк' },
    }));
    expect(wrapper.emitted('created')?.[0]).toEqual([customer]);
  });

  it('keeps the corrected draft available after a failed save', async () => {
    vi.mocked(ManagerService.confirmManagerCustomerRequisites).mockRejectedValueOnce(new Error('offline'));
    const wrapper = mountDialog();
    await enterDraft();
    await dialog().get('input[aria-label="Банк"]').setValue('Исправленный банк');
    await dialog().get('button[type="submit"]').trigger('click');
    await flushPromises();

    expect(dialog().get('[role="alert"]').text()).toContain('offline');
    expect((dialog().get('input[aria-label="Банк"]').element as HTMLInputElement).value).toBe('Исправленный банк');
    expect(wrapper.emitted('created')).toBeUndefined();
    await dialog().get('button[type="submit"]').trigger('click');
    await flushPromises();
    expect(wrapper.emitted('created')).toHaveLength(1);
  });

  it.each([
    [['phone'], false],
    [['inn'], true],
  ])('blocks another customer only for a strong duplicate match %j', async (matched_fields, blocked) => {
    vi.mocked(ManagerService.recognizeManagerCustomerRequisitesText).mockResolvedValueOnce(recognition({
      id: 9, name: 'Другая компания', inn: '987654321', matched_fields,
    }) as never);
    mountDialog();
    await enterDraft();

    expect((dialog().get('button[type="submit"]').element as HTMLButtonElement).disabled).toBe(blocked);
    expect(dialog().text().includes('Реквизиты относятся к другому клиенту')).toBe(blocked);
  });
});
