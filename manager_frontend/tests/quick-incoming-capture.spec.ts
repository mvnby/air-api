import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  preview: vi.fn(),
  scenarios: vi.fn(),
  create: vi.fn(),
  get: vi.fn(),
  update: vi.fn(),
  key: vi.fn(),
}));

vi.mock('../src/services/incoming-api', async (original) => ({
  ...(await original<typeof import('../src/services/incoming-api')>()),
  incomingApi: { preview: mocks.preview, create: mocks.create, get: mocks.get, update: mocks.update },
  newIncomingIdempotencyKey: mocks.key,
}));

vi.mock('../src/api', () => ({ api: { getManagerOrderScenarios: mocks.scenarios } }));

import QuickIncomingCapture from '../src/components/leads/QuickIncomingCapture.vue';
import type { IncomingResponse } from '../src/services/incoming-api';

const incoming = (overrides: Partial<IncomingResponse> = {}): IncomingResponse => ({
  lead_id: 55,
  version: 3,
  intake_state: 'needs_contact',
  missing_fields: ['phone'],
  request_text: 'Исходный текст',
  original_text: 'Исходный текст',
  name: null,
  phone: null,
  email: null,
  region_text: null,
  address_text: null,
  requested_time_text: null,
  requested_at: null,
  source_occurred_at: null,
  source_timezone: 'Europe/Minsk',
  date_precision: null,
  field_sources: {},
  manager_url: '/manager/leads?incomingId=55',
  ...overrides,
});

const wrappers: VueWrapper[] = [];
const mountCapture = async (leadId?: number) => {
  const wrapper = mount(QuickIncomingCapture, { props: { leadId } });
  wrappers.push(wrapper);
  await flushPromises();
  return wrapper;
};

beforeEach(() => {
  for (const mock of Object.values(mocks)) mock.mockReset();
  mocks.key.mockReturnValueOnce('key-1').mockReturnValueOnce('key-2').mockReturnValue('key-next');
  mocks.scenarios.mockResolvedValue({ items: [
    { label: 'Обслуживание', workflow_type: 'maintenance', service_type: 'maintenance' },
    { label: 'Ремонт', workflow_type: 'repair', service_type: 'repair' },
    { label: 'Работы', workflow_type: 'service_work', service_type: null },
  ] });
  mocks.preview.mockResolvedValue(incoming({ preview: { state: 'unknown' } }));
  mocks.create.mockResolvedValue(incoming());
  mocks.get.mockResolvedValue(incoming());
  mocks.update.mockResolvedValue(incoming({ version: 4 }));
});

afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  vi.useRealTimers();
});

describe('QuickIncomingCapture', () => {
  it('saves exact text alone and keeps pasted source time unknown', async () => {
    const wrapper = await mountCapture();
    const exactText = '  Клиент просил\nперезвонить после обеда  ';

    await wrapper.get('[data-testid="incoming-request-text"]').setValue(exactText);
    expect(wrapper.get('[data-testid="incoming-time-unknown"]').text()).toContain('неизвестно');
    await wrapper.get('form').trigger('submit');
    await flushPromises();

    expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({
      request_text: exactText,
      source_occurred_at: null,
      source_timezone: 'Europe/Minsk',
      name: null,
      phone: null,
    }), 'key-1');
  });

  it('retries an unchanged failed command with the same key and timestamp', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-06T12:34:56.000Z'));
    mocks.create.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(incoming());
    const wrapper = await mountCapture();
    await wrapper.get('[data-testid="incoming-request-text"]').setValue('Звонок клиента');
    await wrapper.get('[data-testid="incoming-recorded-now"]').setValue(true);

    await wrapper.get('form').trigger('submit');
    await flushPromises();
    await wrapper.get('form').trigger('submit');
    await flushPromises();

    expect(mocks.create).toHaveBeenCalledTimes(2);
    expect(mocks.create.mock.calls[0]?.[1]).toBe('key-1');
    expect(mocks.create.mock.calls[1]?.[1]).toBe('key-1');
    expect(mocks.create.mock.calls[0]?.[0].source_occurred_at).toBe('2026-10-06T12:34:56.000Z');
    expect(mocks.create.mock.calls[1]?.[0].source_occurred_at).toBe('2026-10-06T12:34:56.000Z');
  });

  it('uses a new key after editing a failed payload', async () => {
    mocks.create.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(incoming());
    const wrapper = await mountCapture();
    await wrapper.get('[data-testid="incoming-request-text"]').setValue('Запрос');
    await wrapper.get('form').trigger('submit');
    await flushPromises();

    await wrapper.get('details').trigger('click');
    await wrapper.get('[data-testid="incoming-name"]').setValue('Анна');
    await wrapper.get('form').trigger('submit');
    await flushPromises();

    expect(mocks.create.mock.calls.map(call => call[1])).toEqual(['key-1', 'key-2']);
  });

  it('keeps a conflicting correction draft until explicitly loading the current version', async () => {
    mocks.get
      .mockResolvedValueOnce(incoming({ version: 3, requested_time_text: 'завтра', requested_at: '2026-10-07T00:00:00Z', date_precision: 'date' }))
      .mockResolvedValueOnce(incoming({ version: 4, request_text: 'Текст другого менеджера', requested_time_text: 'в пятницу' }));
    mocks.update.mockRejectedValueOnce({ status: 409, body: { detail: { message: 'Входящее уже изменилось' } } });
    const wrapper = await mountCapture(55);
    expect(wrapper.get('[data-testid="incoming-intake-state"]').text()).toContain('Нужен контакт');
    expect(wrapper.get('[data-testid="incoming-intake-state"]').text()).toContain('Не указано: Телефон');
    expect(wrapper.get('[data-testid="incoming-requested-at"]').text()).not.toMatch(/00:00/);
    await wrapper.get('[data-testid="incoming-request-text"]').setValue('Моя корректировка');

    await wrapper.get('form').trigger('submit');
    await flushPromises();

    expect((wrapper.get('[data-testid="incoming-request-text"]').element as HTMLTextAreaElement).value).toBe('Моя корректировка');
    expect(wrapper.get('[role="alert"]').text()).toContain('Входящее уже изменилось');
    await wrapper.get('[role="alert"] button').trigger('click');
    await flushPromises();
    expect((wrapper.get('[data-testid="incoming-request-text"]').element as HTMLTextAreaElement).value).toBe('Текст другого менеджера');

    await wrapper.get('details').trigger('click');
    await wrapper.get('[data-testid="incoming-requested-time"]').setValue('в субботу после 15:00');
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    const payload = mocks.update.mock.calls.at(-1)?.[1];
    expect(payload.expected_version).toBe(4);
    expect(payload.requested_time_text).toBe('в субботу после 15:00');
    expect(Object.prototype.hasOwnProperty.call(payload, 'requested_at')).toBe(false);
    expect(mocks.update.mock.calls.at(-1)?.[2]).toBe('key-2');
  });
});


describe('incoming suggestions after durable save', () => {
  const suggested = { state: 'suggested' as const, region_text: 'Билево', workflow_type: 'maintenance', service_type: 'maintenance', evidence: { region_text: 'Билево', service_type: 'ТО квартиры' }, field_sources: { region_text: 'text', service_type: 'text' } };
  it('acknowledges capture before parsing and leaves manual details untouched', async () => {
    let resolvePreview!: (value: IncomingResponse) => void;
    mocks.preview.mockImplementation(() => new Promise(resolve => { resolvePreview = resolve; }));
    mocks.create.mockResolvedValue(incoming({ request_text: 'ТО квартиры, район Билево', phone: '+375291234567', address_text: 'Ручной адрес', region_text: 'Минск' }));
    const wrapper = await mountCapture();
    await wrapper.get('[data-testid="incoming-request-text"]').setValue('ТО квартиры, район Билево');
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(wrapper.emitted('captured')).toHaveLength(1);
    expect(wrapper.get('[data-testid="incoming-saved"]').text()).toContain('сохранено');
    await wrapper.get('[data-testid="incoming-region"]').setValue('Центр');
    resolvePreview(incoming({ request_text: 'ТО квартиры, район Билево', preview: suggested }));
    await flushPromises();
    expect((wrapper.get('[data-testid="incoming-region"]').element as HTMLInputElement).value).toBe('Центр');
    expect((wrapper.get('[data-testid="incoming-phone"]').element as HTMLInputElement).value).toBe('+375291234567');
    expect(wrapper.get('[data-testid="incoming-preview"]').text()).toContain('из текста «ТО квартиры»');
    await wrapper.get('[data-testid="incoming-use-scenario"]').trigger('click');
    await wrapper.get('[data-testid="incoming-scenario"]').setValue('repair:repair');
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(mocks.update).toHaveBeenCalledWith(55, expect.objectContaining({ expected_version: 3, region_text: 'Центр', service_type: 'repair', workflow_type: 'repair' }), 'key-2');
    expect(mocks.update.mock.calls[0]?.[1]).not.toHaveProperty('phone');
    expect(mocks.update.mock.calls[0]?.[1]).not.toHaveProperty('address_text');
    expect(wrapper.emitted('saved')).toHaveLength(1);
  });
  it('keeps the acknowledged source editable when suggestions fail', async () => {
    mocks.preview.mockRejectedValue(new Error('offline'));
    const wrapper = await mountCapture();
    await wrapper.get('[data-testid="incoming-request-text"]').setValue('Исходный текст');
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(wrapper.emitted('captured')).toHaveLength(1);
    expect(wrapper.get('[data-testid="incoming-preview"]').text()).toContain('Исходник сохранён');
    expect(mocks.create).toHaveBeenCalledTimes(1);
    await wrapper.get('[data-testid="incoming-region"]').setValue('Витебск');
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(mocks.update.mock.calls[0]?.[1].region_text).toBe('Витебск');
  });
  it.each(['version', 'text'])('rejects a preview with stale %s while parsing', async (stale) => {
    let resolvePreview!: (value: IncomingResponse) => void;
    mocks.preview.mockImplementation(() => new Promise(resolve => { resolvePreview = resolve; }));
    const wrapper = await mountCapture(55);
    if (stale === 'text') await wrapper.get('[data-testid="incoming-request-text"]').setValue('Уточнённый текст');
    resolvePreview(incoming({ version: stale === 'version' ? 4 : 3, preview: suggested }));
    await flushPromises();
    expect(wrapper.find('[data-testid="incoming-use-region"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="incoming-preview"]').text()).toContain('изменились');
    expect((wrapper.get('[data-testid="incoming-request-text"]').element as HTMLTextAreaElement).value).toBe(stale === 'text' ? 'Уточнённый текст' : 'Исходный текст');
  });
});
