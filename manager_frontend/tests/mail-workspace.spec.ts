import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import MailDraftEditor from '../src/components/mail/MailDraftEditor.vue';
import MailMessageContent from '../src/components/mail/MailMessageContent.vue';
import MailView from '../src/views/MailView.vue';
import { mailApi, type MailMessage } from '../src/services/mail-workspace-api';
import { canNavigateAway } from '../src/services/unsaved-navigation-guard';
import { ManagerMailService } from '../src/client';
import OrderEmailHistory from '../src/components/orders/OrderEmailHistory.vue';

const account = { id: 'system', email: 'office@example.com', name: 'Компания', signature: 'С уважением, Компания' };
const draft = (overrides: Partial<MailMessage> = {}): MailMessage => ({ id: 80, version: 1, status: 'draft', folder: 'drafts', account_id: 'system', sender_email: account.email, sender_name: account.name, to: [], cc: [], bcc: [], subject: '', body_text: '', attachments: [], order_id: null, customer_id: null, manager_url: '/manager/mail?emailId=80', error: null, created_at: '2026-10-13T10:00:00Z', updated_at: '2026-10-13T10:00:00Z', sent_at: null, confirmed_version: null, content_hash: 'sha256-approved', csrf_token: 'csrf-preview', ...overrides });
let wrapper: VueWrapper | undefined;
const button = (text: string) => wrapper!.findAll('button').find(item => item.text() === text)!;

beforeEach(() => {
  window.history.replaceState({}, '', '/manager/mail');
  vi.spyOn(mailApi, 'accounts').mockResolvedValue({ items: [account] });
  vi.spyOn(mailApi, 'list').mockResolvedValue({ items: [], total: 0, page: 1, limit: 30 });
  vi.spyOn(mailApi, 'update').mockImplementation(async (_id, version, fields) => draft({ ...fields, version: version + 1 }));
  vi.spyOn(mailApi, 'get').mockResolvedValue(draft());
  vi.spyOn(mailApi, 'create').mockResolvedValue(draft());
  vi.spyOn(mailApi, 'preview').mockResolvedValue(draft());
  vi.spyOn(mailApi, 'approve').mockResolvedValue(draft({ confirmed_version: 1 }));
  vi.spyOn(mailApi, 'send').mockResolvedValue(draft({ status: 'sent', folder: 'outbox' }));
});
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.restoreAllMocks(); vi.useRealTimers(); });

describe('server-backed mail drafts', () => {
  it('saves an unfinished draft without recipients or links before navigation and never sends it', async () => {
    wrapper = mount(MailDraftEditor, { props: { initial: draft(), accounts: [account] } });
    await wrapper.get('input[aria-label="Тема"]').setValue('Запрос A2E200-AI38-01');
    expect(await canNavigateAway()).toBe(true);
    expect(mailApi.update).toHaveBeenCalledWith(80, 1, expect.objectContaining({ to: [], subject: 'Запрос A2E200-AI38-01', order_id: null, customer_id: null }));
    expect(wrapper.get('[data-testid="mail-save-state"]').text()).toContain('Сохранено · версия 2');
    expect(mailApi.send).not.toHaveBeenCalled();
  });

  it('autosaves changes and keeps a second edit made during the first save', async () => {
    let finish!: (result: MailMessage) => void;
    vi.mocked(mailApi.update).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    wrapper = mount(MailDraftEditor, { props: { initial: draft(), accounts: [account] } });
    await wrapper.get('input[aria-label="Тема"]').setValue('Первая тема');
    const navigation = canNavigateAway();
    await flushPromises();
    await wrapper.get('textarea[aria-label="Текст"]').setValue('Последующий текст');
    finish(draft({ version: 2, subject: 'Первая тема' }));
    expect(await navigation).toBe(true);
    expect(mailApi.update).toHaveBeenNthCalledWith(2, 80, 2, expect.objectContaining({ body_text: 'Последующий текст' }));
    expect(wrapper.get('textarea').element.value).toBe('Последующий текст');
  });

  it('autosaves an unfinished draft without a manual save click', async () => {
    vi.useFakeTimers();
    wrapper = mount(MailDraftEditor, { props: { initial: draft(), accounts: [account] } });
    await wrapper.get('textarea').setValue('Ещё не законченное письмо');
    await vi.advanceTimersByTimeAsync(650);
    expect(mailApi.update).toHaveBeenCalledOnce();
    expect(mailApi.send).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('Сохранено · версия 2');
  });

  it('keeps local text after a version conflict and blocks navigation and send', async () => {
    vi.mocked(mailApi.update).mockRejectedValue({ status: 409 });
    wrapper = mount(MailDraftEditor, { props: { initial: draft(), accounts: [account] } });
    await wrapper.get('textarea').setValue('Моя правка');
    expect(await canNavigateAway()).toBe(false);
    expect(wrapper.text()).toContain('Черновик изменён в другом окне или ChatGPT');
    expect(wrapper.get('textarea').element.value).toBe('Моя правка');
    expect(button('Отправить письмо').attributes('disabled')).toBeDefined();
    expect(mailApi.approve).not.toHaveBeenCalled();
    expect(mailApi.send).not.toHaveBeenCalled();
  });

  it('requires reviewing every recipient, full body and attachments before explicit send', async () => {
    const ready = draft({ to: ['supplier@example.com'], cc: ['copy@example.com'], bcc: ['private@example.com'], subject: 'A2E200-AI38-01', body_text: 'Полный текст\nПоследняя строка', attachments: [{ id: 9, filename: 'specification.pdf', mime_type: 'application/pdf', size: 123, sha256: 'file-hash', available: true, download_url: '/api/manager/mail/drafts/80/attachments/9' }] });
    vi.mocked(mailApi.preview).mockResolvedValue(ready);
    wrapper = mount(MailDraftEditor, { props: { initial: ready, accounts: [account] } });
    expect(wrapper.get('input[aria-label="Копия"]').element.value).toBe('copy@example.com');
    expect(wrapper.get('input[aria-label="Скрытая копия"]').element.value).toBe('private@example.com');
    expect(wrapper.get('textarea').element.value).toContain('Последняя строка');
    expect(wrapper.text()).toContain('specification.pdf');
    await button('Отправить письмо').trigger('click');
    await flushPromises();
    expect(mailApi.approve).toHaveBeenCalledWith(80, 1, 'sha256-approved', 'csrf-preview');
    expect(mailApi.send).toHaveBeenCalledOnce();
    expect(mailApi.send).toHaveBeenCalledWith(80, 1, expect.any(String), 'csrf-preview');
    expect(wrapper.text()).toContain('Принято почтовым сервером');
  });

  it('rejects a changed preview and a stale approval without sending', async () => {
    vi.mocked(mailApi.preview).mockResolvedValue(draft({ version: 2 }));
    wrapper = mount(MailDraftEditor, { props: { initial: draft(), accounts: [account] } });
    await button('Отправить письмо').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('Конфликт изменений');
    expect(mailApi.approve).not.toHaveBeenCalled();
    expect(mailApi.send).not.toHaveBeenCalled();
  });

  it('stores exact-version Manager approval for MCP without sending', async () => {
    wrapper = mount(MailDraftEditor, { props: { initial: draft(), accounts: [account] } });
    await button('Проверить для ChatGPT').trigger('click');
    await flushPromises();
    await button('Подтвердить для ChatGPT').trigger('click');
    await flushPromises();
    expect(mailApi.approve).toHaveBeenCalledWith(80, 1, 'sha256-approved', 'csrf-preview');
    expect(mailApi.send).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('Версия 1 подтверждена и ещё не отправлена');
    await wrapper.get('textarea').setValue('Изменённое письмо');
    expect(wrapper.text()).not.toContain('Версия 1 подтверждена и ещё не отправлена');
  });

  it('does not send if the exact preview approval becomes stale', async () => {
    vi.mocked(mailApi.approve).mockRejectedValue({ status: 409 });
    wrapper = mount(MailDraftEditor, { props: { initial: draft(), accounts: [account] } });
    await button('Отправить письмо').trigger('click');
    await flushPromises();
    expect(mailApi.send).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('Конфликт изменений');
  });

  it('ignores a double click while confirmation is in progress', async () => {
    let finish!: (result: MailMessage) => void;
    vi.mocked(mailApi.approve).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    wrapper = mount(MailDraftEditor, { props: { initial: draft(), accounts: [account] } });
    const sendButton = button('Отправить письмо');
    await sendButton.trigger('click');
    await sendButton.trigger('click');
    await flushPromises();
    expect(mailApi.approve).toHaveBeenCalledOnce();
    finish(draft({ confirmed_version: 1 }));
    await flushPromises();
    expect(mailApi.send).toHaveBeenCalledOnce();
  });

  it('does not blindly resend when the send response is lost', async () => {
    vi.mocked(mailApi.send).mockRejectedValue(new TypeError('Connection lost'));
    vi.mocked(mailApi.get).mockRejectedValue(new TypeError('Connection lost'));
    wrapper = mount(MailDraftEditor, { props: { initial: draft(), accounts: [account] } });
    await button('Отправить письмо').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('Повторная отправка может создать дубликат');
    expect(button('Отправить письмо').attributes('disabled')).toBeDefined();
    await button('Проверить статус').trigger('click');
    await flushPromises();
    expect(mailApi.send).toHaveBeenCalledOnce();
  });

  it('shows status inspection when a send fence returns a conflict after an unknown attempt', async () => {
    vi.mocked(mailApi.send).mockRejectedValue({ status: 409 });
    vi.mocked(mailApi.get).mockResolvedValue(draft({ status: 'unknown', folder: 'outbox' }));
    wrapper = mount(MailDraftEditor, { props: { initial: draft(), accounts: [account] } });
    await button('Отправить письмо').trigger('click'); await flushPromises();
    expect(button('Проверить статус')).toBeDefined();
    expect(wrapper.text()).not.toContain('заменит текст в форме');
    expect(mailApi.send).toHaveBeenCalledOnce();
  });

  it('rejects a same-version preview with different visible content or sender', async () => {
    for (const changed of [{ body_text: 'Невидимая подмена' }, { sender_email: 'other@example.test' }, { attachments: [{ id: 90, filename: 'other.pdf', size: 4, sha256: 'new', available: true, mime_type: 'application/pdf', download_url: null }] }]) {
      vi.mocked(mailApi.preview).mockResolvedValue(draft(changed));
      wrapper = mount(MailDraftEditor, { props: { initial: draft(), accounts: [account] } });
      await button('Отправить письмо').trigger('click'); await flushPromises();
      expect(wrapper.text()).toContain('Конфликт изменений');
      expect(mailApi.approve).not.toHaveBeenCalled(); expect(mailApi.send).not.toHaveBeenCalled();
      wrapper.unmount(); wrapper = undefined;
    }
  });

  it('saves the final visible edit before exact-version approval and send', async () => {
    vi.mocked(mailApi.preview).mockResolvedValue(draft({ version: 2, subject: 'Последняя видимая тема' }));
    wrapper = mount(MailDraftEditor, { props: { initial: draft(), accounts: [account] } });
    await wrapper.get('input[aria-label="Тема"]').setValue('Последняя видимая тема');
    await button('Отправить письмо').trigger('click'); await flushPromises();
    expect(mailApi.update).toHaveBeenCalledOnce();
    expect(mailApi.approve).toHaveBeenCalledWith(80, 2, 'sha256-approved', 'csrf-preview');
    expect(mailApi.send).toHaveBeenCalledWith(80, 2, expect.any(String), 'csrf-preview');
  });

  it('applies background wording only before any manual text edit and on the same version', async () => {
    wrapper = mount(MailDraftEditor, { props: { initial: draft({ body_text: 'Исходный текст' }), accounts: [account] } });
    (wrapper.vm as any).applySuggestion({ version: 2, subject: 'Чужая версия', body_text: 'Не подставлять' });
    expect(wrapper.get('textarea').element.value).toBe('Исходный текст');
    await wrapper.get('textarea').setValue('Мой текст');
    await wrapper.get('textarea').setValue('Исходный текст');
    (wrapper.vm as any).applySuggestion({ version: 1, subject: 'Тема ИИ', body_text: 'Новый текст ИИ' });
    expect(wrapper.get('textarea').element.value).toBe('Исходный текст');
  });

  it('autosaves accepted background wording without blocking opening or sending', async () => {
    vi.useFakeTimers();
    wrapper = mount(MailDraftEditor, { props: { initial: draft({ body_text: 'Исходный текст' }), accounts: [account] } });
    expect(button('Отправить письмо').attributes('disabled')).toBeUndefined();
    (wrapper.vm as any).applySuggestion({ version: 1, subject: 'Тема', body_text: 'Живой вводный абзац' });
    await vi.advanceTimersByTimeAsync(650);
    expect(mailApi.update).toHaveBeenCalledWith(80, 1, expect.objectContaining({ body_text: 'Живой вводный абзац' }));
  });

  it('persists the current edit before uploading attachment bytes with the new version', async () => {
    vi.spyOn(mailApi, 'upload').mockResolvedValue(draft({ version: 3, attachments: [{ id: 9, filename: 'specification.pdf', mime_type: 'application/pdf', size: 12, sha256: 'hash', download_url: null, available: true }] }));
    wrapper = mount(MailDraftEditor, { props: { initial: draft(), accounts: [account] } });
    await wrapper.get('input[aria-label="Тема"]').setValue('Запрос');
    const file = new File(['%PDF-test'], 'specification.pdf', { type: 'application/pdf' });
    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true });
    await input.trigger('change');
    await flushPromises();
    expect(mailApi.upload).toHaveBeenCalledWith(80, 2, file);
    expect(wrapper.text()).toContain('specification.pdf');
    expect(mailApi.send).not.toHaveBeenCalled();
  });
});

describe('standalone mailbox', () => {
  it('replies to Reply-To and keeps threading and the complete detail body', async () => {
    window.history.replaceState({}, '', '/manager/mail?emailId=-7');
    vi.mocked(mailApi.get).mockResolvedValue(draft({ id: -7, folder: 'inbox', status: 'received',
      sender_email: 'no-reply@example.test', reply_to: ['sales@example.test'], message_id: '<parent@example.test>',
      references: ['<root@example.test>'], body_text: 'Long full body\nFinal detail line' }));
    wrapper = mount(MailView);
    await flushPromises();
    await button('Ответить').trigger('click');
    await flushPromises();
    expect(mailApi.get).toHaveBeenCalledWith(-7);
    expect(mailApi.create).toHaveBeenCalledWith(expect.objectContaining({
      to: ['sales@example.test'], in_reply_to: '<parent@example.test>',
      references: ['<root@example.test>', '<parent@example.test>'],
      body_text: expect.stringContaining('> Final detail line'),
    }));
  });

  it('shows active and uncertain send results in order history without offering a blind retry', async () => {
    vi.spyOn(ManagerMailService, 'listManagerOrderOutgoingEmails').mockResolvedValue({ items: [
      { id: 80, status: 'sending', created_at: '2026-10-13T10:00:00Z', subject: 'Документы', recipient_email: 'client@example.com' },
      { id: 81, status: 'unknown', created_at: '2026-10-13T11:00:00Z', subject: 'Результат требует проверки', recipient_email: 'client@example.com' },
    ], total: 2, page: 1, limit: 8 });
    const retry = vi.spyOn(ManagerMailService, 'retryManagerOutgoingEmail');
    wrapper = mount(OrderEmailHistory, { props: { orderId: 42 } });
    await flushPromises();
    await wrapper.get('button[aria-expanded]').trigger('click');
    expect(wrapper.text()).toContain('Отправляется');
    expect(wrapper.text()).toContain('Результат требует проверки');
    expect(wrapper.text()).toContain('Письмо могло быть принято сервером');
    expect(wrapper.findAll('button').some(item => /Повторить|Retry/.test(item.text()))).toBe(false);
    await wrapper.findAll('article')[1]!.trigger('click');
    expect(window.location.pathname + window.location.search).toBe('/manager/mail/outbox?orderId=42&emailId=81');
    expect(retry).not.toHaveBeenCalled();
  });

  it('loads inbox mail from the existing mailbox only after an explicit refresh', async () => {
    vi.spyOn(mailApi, 'sync').mockResolvedValue({ processed: 1, captured: 1, skipped: 0 });
    wrapper = mount(MailView);
    await flushPromises();
    expect(mailApi.sync).not.toHaveBeenCalled();
    await button('Обновить почту').trigger('click');
    await flushPromises();
    expect(mailApi.sync).toHaveBeenCalledOnce();
    expect(wrapper.text()).toContain('Загружено новых писем: 1.');
    expect(mailApi.create).not.toHaveBeenCalled();
  });
  it('opens an MCP draft deep link and edits it through the same server draft', async () => {
    window.history.replaceState({}, '', '/manager/mail?emailId=80');
    wrapper = mount(MailView);
    await flushPromises();
    expect(mailApi.get).toHaveBeenCalledWith(80);
    await wrapper.get('input[aria-label="Тема"]').setValue('Правка из Manager');
    await button('Сохранить черновик').trigger('click');
    await flushPromises();
    expect(mailApi.update).toHaveBeenCalledWith(80, 1, expect.objectContaining({ subject: 'Правка из Manager' }));
  });

  it('creates a mail draft without requiring an order or customer', async () => {
    wrapper = mount(MailView);
    await flushPromises();
    await button('Новое письмо').trigger('click');
    await flushPromises();
    expect(mailApi.create).toHaveBeenCalledWith({ account_id: 'system' });
    expect(wrapper.find('input[aria-label="Кому"]').exists()).toBe(true);
    expect(mailApi.send).not.toHaveBeenCalled();
  });

  it('renders message content as data and makes unavailable historic files explicit', () => {
    wrapper = mount(MailMessageContent, { props: { message: draft({ status: 'received', folder: 'inbox', body_text: '<script>alert(1)</script><img src="https://tracker.test/pixel">', attachments: [{ id: null, filename: 'old.pdf', mime_type: 'application/pdf', size: 100, sha256: null, available: false, download_url: null }] }) } });
    expect(wrapper.find('script').exists()).toBe(false);
    expect(wrapper.find('img').exists()).toBe(false);
    expect(wrapper.find('iframe').exists()).toBe(false);
    expect(wrapper.text()).toContain('<script>alert(1)</script>');
    expect(wrapper.text()).toContain('Файл не сохранён; повторная отправка недоступна');
  });

  it('keeps the legacy outbox URL and searches the selected folder', async () => {
    window.history.replaceState({}, '', '/manager/mail/outbox?orderId=42');
    wrapper = mount(MailView);
    await flushPromises();
    expect(mailApi.list).toHaveBeenCalledWith(expect.objectContaining({ folder: 'outbox', order_id: 42 }));
    await wrapper.get('input[aria-label="Поиск писем"]').setValue('A2E200-AI38-01');
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(mailApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ folder: 'outbox', q: 'A2E200-AI38-01', page: 1, limit: 30 }));
  });

  it('does not carry an outgoing status into the inbox where it would hide all messages', async () => {
    window.history.replaceState({}, '', '/manager/mail/outbox?status=sent');
    wrapper = mount(MailView);
    await flushPromises();
    await button('Входящие').trigger('click');
    await flushPromises();
    expect(mailApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ folder: 'inbox', status: undefined }));
  });
});
