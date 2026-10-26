import { defineComponent, ref } from 'vue';
import { mount, flushPromises } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useOrderRequestContext } from '../src/composables/useOrderRequestContext';
import OrderRequestPanel from '../src/components/orders/OrderRequestPanel.vue';
import type { OrderRequestFile } from '../src/client';
import { OpenAPI } from '../src/client/core/OpenAPI';
import { serviceAttachmentsApi } from '../src/components/service-attachments/api';
const evidenceFile = (id: number | null): OrderRequestFile => ({
  id, filename: 'Оригинал с длинным названием.pdf', mime_type: 'application/pdf', file_kind: 'pdf',
  size_bytes: 706702, source: 'email_lead_intake', origin_label: 'Из письма заказчика',
  category: 'document', created_at: '2026-10-26T08:00:00Z', preview_available: false,
  processing_status: 'ready', processing_error: null, available: true, caption: null, transcript: null, captured_at: null,
});

const api = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('../src/client/core/request', () => ({ request: api.request }));
const empty = () => ({ sources: [], files: [], warnings: [] });
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.body.innerHTML = ''; });

describe('Order source metadata and original access', () => {
  it('never shows zero before loading and rejects old responses across order changes and close', async () => {
    const pending: ((value: unknown) => void)[] = [];
    api.request.mockImplementation(() => new Promise(resolve => pending.push(resolve)));
    const order = ref<number | undefined>(590), active = ref(true);
    let state!: ReturnType<typeof useOrderRequestContext>;
    const wrapper = mount(defineComponent({ setup() { state = useOrderRequestContext(order, active); return () => null; } }));
    expect(state.summary.value).toBe('Проверяем файлы…');
    order.value = 591;
    pending[0]!({ ...empty(), files: [evidenceFile(143)] }); await flushPromises();
    expect(state.context.value).toBeNull();
    pending[1]!({ ...empty(), files: [evidenceFile(591)] }); await flushPromises();
    expect(state.summary.value).toBe('Файлов: 1');
    expect(state.context.value?.files[0]?.id).toBe(591);
    active.value = false;
    expect(state.context.value).toBeNull();
    expect(state.summary.value).not.toContain('0');
    wrapper.unmount();
  });

  it('shows error and permits a fresh metadata retry without fetching file bytes', async () => {
    api.request.mockRejectedValueOnce(new Error('Недоступно')).mockResolvedValueOnce(empty());
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
    let state!: ReturnType<typeof useOrderRequestContext>;
    const wrapper = mount(defineComponent({ setup() { state = useOrderRequestContext(ref(590), ref(true)); return () => null; } }));
    await flushPromises(); expect(state.error.value).toBe('Недоступно'); expect(state.summary.value).not.toContain('0');
    await state.load(); expect(state.summary.value).toBe('Файлов: 0'); expect(fetcher).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('uses the current credentials and selected storefront for explicit mail-original access', async () => {
    api.request.mockResolvedValue(empty());
    const initial = { TOKEN: OpenAPI.TOKEN, HEADERS: OpenAPI.HEADERS };
    OpenAPI.TOKEN = async () => 'scoped-token';
    OpenAPI.HEADERS = async () => ({ 'X-Storefront-Id': '99' });
    const fetcher = vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(['%PDF-1.4']) });
    vi.stubGlobal('fetch', fetcher);
    const create = vi.fn().mockReturnValue('blob:original'), revoke = vi.fn();
    vi.stubGlobal('URL', class extends URL { static createObjectURL = create; static revokeObjectURL = revoke; });
    let state!: ReturnType<typeof useOrderRequestContext>;
    const wrapper = mount(defineComponent({ setup() { state = useOrderRequestContext(ref(590), ref(true)); return () => null; } }));
    try {
      await flushPromises(); expect(fetcher).not.toHaveBeenCalled();
      await state.resolveAccess({ ...evidenceFile(-144), mail_message_id: -187, mail_attachment_id: 144 } as any, false);
      expect(fetcher.mock.calls[0]?.[0]).toMatch(/\/api\/manager\/mail\/messages\/-187\/attachments\/144$/);
      const headers = fetcher.mock.calls[0]?.[1].headers as Headers;
      expect(headers.get('Authorization')).toBe('Bearer scoped-token'); expect(headers.get('X-Storefront-Id')).toBe('99');
      fetcher.mockResolvedValueOnce({ ok: true, text: async () => JSON.stringify({ url: 'https://private.test/original', variant: 'original', expires_at: '' }) });
      await serviceAttachmentsApi.getAccess(143, 'original', true);
      expect(fetcher.mock.calls[1]?.[0]).toMatch(/\/service-attachments\/143\/access\?variant=original&download=true$/);
      expect(fetcher.mock.calls[1]?.[1].headers).toMatchObject({ Authorization: 'Bearer scoped-token', 'X-Storefront-Id': '99' });
      wrapper.unmount(); expect(revoke).toHaveBeenCalledWith('blob:original');
    } finally { Object.assign(OpenAPI, initial); wrapper.unmount(); }
  });

  it('Escape closes only the viewer and restores focus before the panel can close', async () => {
    const resolveAccess = vi.fn().mockResolvedValue({ url: 'https://example.test/file.pdf', variant: 'original', expires_at: '' });
    const wrapper = mount(OrderRequestPanel, { attachTo: document.body, props: {
      context: { ...empty(), files: [evidenceFile(143)] }, description: 'Рабочая заявка', loading: false, error: '', resolveAccess,
    } });
    const open = wrapper.findAll('button').find(button => button.text() === 'Открыть')!;
    open.element.focus(); await open.trigger('click'); await flushPromises();
    expect(document.querySelector('[role="dialog"]')).not.toBeNull();
    expect(resolveAccess).toHaveBeenCalledTimes(1);
    document.querySelector('[aria-label="Закрыть просмотр"]')?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    // The viewer's focused close action is the target; it is outside the inline panel.
    if (document.querySelector('[role="dialog"]')) document.activeElement?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await flushPromises();
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(wrapper.emitted('close')).toBeUndefined();
    expect(document.activeElement).toBe(open.element);
    await open.trigger('keydown', { key: 'Escape' });
    expect(wrapper.emitted('close')).toHaveLength(1);
    wrapper.unmount();
  });

  it('keeps unavailable records visible and suppresses late downloads after panel unmount', async () => {
    let resolve!: (value: unknown) => void;
    const resolveAccess = vi.fn().mockImplementation(() => new Promise(done => { resolve = done; }));
    const wrapper = mount(OrderRequestPanel, { props: { context: { ...empty(), files: [evidenceFile(143), { ...evidenceFile(null), available: false, legacy_key: 'missing' }] }, description: '', loading: false, error: '', resolveAccess } });
    expect(wrapper.text()).toContain('Недоступен'); expect(wrapper.text()).toContain('· 2');
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    await wrapper.findAll('button').find(button => button.text() === 'Скачать')!.trigger('click');
    wrapper.unmount(); resolve({ url: 'https://example.test/private.pdf' }); await flushPromises();
    expect(click).not.toHaveBeenCalled();
  });
});
