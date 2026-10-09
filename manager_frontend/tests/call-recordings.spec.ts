import { DOMWrapper, flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { CallDriveStatus, CallRecordingResponse } from '../src/client';

const mocks = vi.hoisted(() => ({ status: vi.fn(), list: vi.fn(), get: vi.fn(), authorize: vi.fn(), folder: vi.fn(), disconnect: vi.fn(), poll: vi.fn(), retry: vi.fn(), metadata: vi.fn(), adopt: vi.fn(), driveFiles: vi.fn() }));
vi.mock('../src/services/call-recordings-api', async (original) => ({ ...(await original<typeof import('../src/services/call-recordings-api')>()), callRecordingsApi: mocks }));
import CallRecordingsView from '../src/views/CallRecordingsView.vue';
import CallRecordingPicker from '../src/components/calls/CallRecordingPicker.vue';
import CallProposalCard from '../src/components/calls/CallProposalCard.vue';
import { callErrorLabel, driveId } from '../src/services/call-recordings-api';

const connection = (enabled = true): CallDriveStatus => ({ connected: true, pipeline_enabled: enabled, transcription_configured: true, transcription_model: 'whisper-large-v3-turbo', transcription_provider: 'groq', google_batch_configured: false, groq_configured: true, structure_model: 'deepseek', folder_id: 'chosen-folder-000001', auto_poll_enabled: false, max_bytes: 10485760, max_duration_seconds: 600, max_files_per_poll: 5, max_recordings_per_day: 20, max_stage_attempts: 3 });
const recording = (): CallRecordingResponse => ({ id: 4, version: 7, file_id: 'safe-file-00000001', source_version: 'revision', source_checksum: 'md5', source_size: 500, source_url: 'https://drive.google.com/file/d/safe-file-00000001/view', filename: 'Тестовая запись.m4a', mime_type: 'video/3gpp', origin: 'drive_selected_folder', call_occurred_at: null, time_source: 'unknown', phone: null, transcription_provider: null, transcription_model: null, state: 'ready_for_review', stage: 'proposals', stage_attempts: { transcribe: 1 }, last_error_code: null, audio_duration_seconds: 30, transcript: 'Дослать фото свидетельства. Нужен обратный звонок.', proposals: [
  { id: 10, kind: 'task', evidence: 'Дослать фото свидетельства', needs_clarification: [], payload: { text: 'Дослать фото свидетельства', description: 'Дослать фото свидетельства', due_at: null } },
  { id: 11, kind: 'callback', evidence: 'Нужен обратный звонок', needs_clarification: ['Контакт не подтверждён'], payload: { text: 'Перезвонить', due_at: null } },
] });

beforeEach(() => {
  vi.clearAllMocks();
  mocks.status.mockResolvedValue(connection());
  mocks.list.mockResolvedValue({ items: [recording()], total: 1 });
  mocks.get.mockResolvedValue(recording());
  mocks.driveFiles.mockResolvedValue({ items: [{ file_id: 'picked-file-000001', filename: 'Вызов Дима_261008_170514.m4a', source_url: 'https://drive.google.com/file/d/picked-file-000001/view', call_occurred_at: '2026-10-08T14:05:14Z', contact: 'Дима', phone: null, size: 500 }], next_page_token: null });
  mocks.poll.mockResolvedValue({ observed: 1, queued: 0, has_more: false });
  mocks.adopt.mockResolvedValue({ resource_type: 'personal_task', resource_id: 12, resource_url: '/manager/tasks?taskId=12' });
});

describe('call recording review', () => {
  it('keeps an existing connection compact and waits for an explicit selection', async () => {
    const wrapper = mount(CallRecordingsView);
    await flushPromises();
    expect(wrapper.get('[data-testid="call-setup"] details').attributes('open')).toBeUndefined();
    expect(wrapper.get('[data-testid="call-selection-empty"]').text()).toContain('Выберите запись');
    expect(mocks.get).not.toHaveBeenCalled();
    const row = wrapper.findAll('button').find(button => button.text().includes('Тестовая запись'))!;
    expect(row.attributes('aria-pressed')).toBe('false');
    await row.trigger('click');
    await flushPromises();
    expect(row.attributes('aria-pressed')).toBe('true');
    expect(wrapper.find('[data-testid="call-selection-empty"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it('shows loading and an actionable empty list without processing files', async () => {
    let resolveList!: (value: { items: CallRecordingResponse[]; total: number }) => void;
    mocks.list.mockImplementationOnce(() => new Promise(resolve => { resolveList = resolve; }));
    const wrapper = mount(CallRecordingsView);
    await flushPromises();
    expect(wrapper.text()).toContain('Загружаем подключение и записи');
    resolveList({ items: [], total: 0 });
    await flushPromises();
    expect(wrapper.text()).toContain('Пока нет записей для разбора');
    expect(wrapper.text()).toContain('Проверьте файл вручную');
    expect(mocks.poll).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('toggles automatic checking directly while preserving the selected provider', async () => {
    mocks.folder.mockResolvedValue({ ...connection(), auto_poll_enabled: true });
    const wrapper = mount(CallRecordingsView);
    await flushPromises();
    await wrapper.get('[data-testid="call-setup"] input[type="checkbox"]').setValue(true);
    await flushPromises();
    expect(mocks.folder).toHaveBeenCalledWith('chosen-folder-000001', true, 'groq');
    expect(wrapper.text()).toContain('Автопроверка включена');
    expect(mocks.poll).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('does not offer resubmission when the Google wait deadline expired', async () => {
    mocks.get.mockResolvedValue({ ...recording(), state: 'manual_review', stage: 'transcribe', last_error_code: 'call_google_wait_expired' });
    const wrapper = mount(CallRecordingsView);
    await flushPromises();
    await wrapper.findAll('button').find(button => button.text().includes('Тестовая запись'))!.trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('разберите запись вручную');
    expect(wrapper.text()).not.toContain('Повторить незавершённый этап');
    expect(mocks.retry).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it.each([false, true])('saves Soniox without changing automatic checking: %s', async (auto) => {
    mocks.status.mockResolvedValue({ ...connection(), auto_poll_enabled: auto, soniox_configured: true });
    mocks.folder.mockResolvedValue({ ...connection(), auto_poll_enabled: auto, transcription_provider: 'soniox', soniox_configured: true });
    const wrapper = mount(CallRecordingsView);
    await flushPromises();
    await wrapper.get('[aria-label="Провайдер распознавания"]').setValue('soniox');
    expect(wrapper.text()).toContain('результат появляется после завершения обработки');
    await wrapper.get('[aria-label="Папка записей"]').setValue('https://drive.google.com/drive/folders/chosen-folder-000001');
    await wrapper.get('[aria-label="Папка записей"]').trigger('submit');
    await flushPromises();
    expect(mocks.folder).toHaveBeenCalledWith('chosen-folder-000001', auto, 'soniox');
    expect(mocks.poll).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('explains Soniox waiting without a Google deadline', async () => {
    const value = { ...recording(), state: 'waiting_transcription', stage: 'transcribe', transcription_provider: 'soniox', transcription_model: 'stt-async-v4' };
    mocks.list.mockResolvedValue({ items: [value], total: 1 }); mocks.get.mockResolvedValue(value);
    const wrapper = mount(CallRecordingsView);
    await flushPromises();
    await wrapper.findAll('button').find(button => button.text().includes('Тестовая запись'))!.trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('уже отправлена в Soniox');
    expect(wrapper.text()).not.toContain('24 часов');
    expect(mocks.retry).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it.each(['call_soniox_submission_uncertain', 'call_soniox_wait_expired', 'call_soniox_operation_failed', 'call_soniox_invalid_audio'])('blocks another Soniox submission for %s', async (code) => {
    mocks.get.mockResolvedValue({ ...recording(), state: 'manual_review', stage: 'transcribe', transcription_provider: 'soniox', last_error_code: code });
    const wrapper = mount(CallRecordingsView);
    await flushPromises();
    await wrapper.findAll('button').find(button => button.text().includes('Тестовая запись'))!.trigger('click');
    await flushPromises();
    expect(wrapper.text()).not.toContain('Повторить незавершённый этап');
    expect(wrapper.text()).toContain(callErrorLabel(code));
    wrapper.unmount();
  });

  it('reads the folder and selects one file before an explicit check', async () => {
    const wrapper = mount(CallRecordingsView);
    const dialog = new DOMWrapper(document.body);
    await flushPromises();
    expect(mocks.driveFiles).not.toHaveBeenCalled();
    await wrapper.get('[data-testid="choose-drive-recording"]').trigger('click');
    await flushPromises();
    expect(mocks.driveFiles).toHaveBeenCalledTimes(1);
    expect(mocks.poll).not.toHaveBeenCalled();
    await dialog.get('[data-testid="drive-file-option"]').trigger('click');
    await dialog.get('[data-testid="select-drive-recording"]').trigger('click');
    await flushPromises();
    expect(wrapper.get('[data-testid="picked-drive-recording"]').text()).toContain('Дима');
    expect(mocks.poll).not.toHaveBeenCalled();
    await wrapper.get('[data-testid="start-picked-recording"]').trigger('click');
    await flushPromises();
    expect(mocks.poll).toHaveBeenCalledWith('picked-file-000001');
    expect(mocks.poll).toHaveBeenCalledTimes(1);
    wrapper.unmount();
  });

  it('filters by inclusive Minsk dates and contact, resets a stale selection', async () => {
    const wrapper = mount(CallRecordingPicker, { props: { open: true, folderName: 'Звонки' } });
    const dialog = new DOMWrapper(document.body);
    await flushPromises();
    await dialog.get('[data-testid="drive-file-option"]').trigger('click');
    await dialog.get('[aria-label="Режим выбора даты"]').setValue('range');
    await dialog.get('[aria-label="Дата начала"]').setValue('2026-10-01');
    await dialog.get('[aria-label="Дата окончания"]').setValue('2026-10-08');
    await dialog.get('[aria-label="Имя контакта или номер"]').setValue(' +375 (29) 123-45-67 ');
    expect(dialog.get('[data-testid="select-drive-recording"]').attributes('disabled')).toBeDefined();
    expect(mocks.driveFiles).toHaveBeenCalledTimes(1);
    await dialog.get('form').trigger('submit');
    await flushPromises();
    expect(mocks.driveFiles).toHaveBeenLastCalledWith({ date_from: '2026-10-01', date_to: '2026-10-08', query: '+375 (29) 123-45-67' });
    expect(mocks.poll).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('continues an empty filtered page and preserves results after a load-more error', async () => {
    mocks.driveFiles.mockResolvedValueOnce({ items: [], next_page_token: 'page-two' }).mockRejectedValueOnce(new Error('Drive недоступен')).mockResolvedValueOnce({ items: [{ file_id: 'unknown-file-0001', filename: 'Без даты.m4a', call_occurred_at: null, contact: null, phone: null, source_url: '', size: null }], next_page_token: 'page-three' }).mockRejectedValueOnce(new Error('Временно недоступно'));
    const wrapper = mount(CallRecordingPicker, { props: { open: true, folderName: 'Звонки' } });
    const dialog = new DOMWrapper(document.body);
    await flushPromises();
    expect(dialog.text()).not.toContain('Записи не найдены');
    expect(dialog.get('[data-testid="more-drive-recordings"]').text()).toBe('Продолжить поиск');
    await dialog.get('[data-testid="more-drive-recordings"]').trigger('click'); await flushPromises();
    expect(dialog.get('[role="alert"]').text()).toContain('Drive недоступен');
    expect(mocks.driveFiles).toHaveBeenLastCalledWith(expect.objectContaining({ page_token: 'page-two' }));
    await dialog.get('[data-testid="more-drive-recordings"]').trigger('click'); await flushPromises();
    expect(dialog.text()).toContain('Дата звонка неизвестна');
    await dialog.get('[data-testid="more-drive-recordings"]').trigger('click'); await flushPromises();
    expect(dialog.text()).toContain('Без даты.m4a');
    expect(dialog.get('[role="alert"]').text()).toContain('Временно недоступно');
    expect(mocks.poll).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('searches all time without date parameters and makes a phone-only contact the primary label', async () => {
    mocks.driveFiles.mockResolvedValue({ items: [{ file_id: 'phone-file-00001', filename: 'Запись вызова +375291234567_261008_091013.m4a', contact: null, phone: '+375291234567', call_occurred_at: null, source_url: '', size: null }], next_page_token: null });
    const wrapper = mount(CallRecordingPicker, { props: { open: true, folderName: 'Звонки' } });
    const dialog = new DOMWrapper(document.body);
    await flushPromises();
    await dialog.get('[aria-label="Режим выбора даты"]').setValue('all');
    await dialog.get('[aria-label="Имя контакта или номер"]').setValue('+37529');
    expect(dialog.find('[aria-label="Дата начала"]').exists()).toBe(false);
    expect(dialog.find('[aria-label="Дата окончания"]').exists()).toBe(false);
    await dialog.get('form').trigger('submit');
    await flushPromises();
    expect(mocks.driveFiles).toHaveBeenLastCalledWith({ query: '+37529' });
    const row = dialog.get('[data-testid="drive-file-option"]');
    expect(row.findAll('span.block')[0]!.text()).toBe('+375291234567');
    expect(row.text()).toContain('Запись вызова +375291234567_261008_091013.m4a');
    expect(mocks.poll).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('sorts appended files by call time and deduplicates their Drive ids', async () => {
    const file = { filename: 'Звонок.m4a', contact: null, phone: null, source_url: '', size: null };
    mocks.driveFiles.mockResolvedValueOnce({ items: [{ ...file, file_id: 'unknown', call_occurred_at: null }, { ...file, file_id: 'older', call_occurred_at: '2026-10-01T07:00:00Z' }], next_page_token: 'next' }).mockResolvedValueOnce({ items: [{ ...file, file_id: 'newer', call_occurred_at: '2026-10-08T07:00:00Z' }, { ...file, file_id: 'older', call_occurred_at: '2026-10-01T07:00:00Z' }], next_page_token: null });
    const wrapper = mount(CallRecordingPicker, { props: { open: true, folderName: 'Звонки' } });
    const dialog = new DOMWrapper(document.body);
    await flushPromises();
    await dialog.get('[data-testid="more-drive-recordings"]').trigger('click');
    await flushPromises();
    const rows = dialog.findAll('[data-testid="drive-file-option"]');
    expect(rows).toHaveLength(3);
    expect(rows[0]!.text()).toContain('2026-10-08 10:00');
    expect(rows[1]!.text()).toContain('2026-10-01 10:00');
    expect(rows[2]!.text()).toContain('Дата звонка неизвестна');
    wrapper.unmount();
  });

  it('saves Google batch selection without enabling automatic polling', async () => {
    mocks.folder.mockResolvedValue({ ...connection(), transcription_provider: 'google_batch', transcription_configured: true, transcription_model: 'google-batch' });
    const wrapper = mount(CallRecordingsView);
    await flushPromises();
    await wrapper.get('[aria-label="Провайдер распознавания"]').setValue('google_batch');
    expect(wrapper.text()).toContain('Результат может появиться в течение 24 часов');
    await wrapper.get('[aria-label="Папка записей"]').setValue('https://drive.google.com/drive/folders/chosen-folder-000001');
    await wrapper.get('[aria-label="Папка записей"]').trigger('submit');
    await flushPromises();
    expect(mocks.folder).toHaveBeenCalledWith('chosen-folder-000001', false, 'google_batch');
    wrapper.unmount();
  });

  it('explains that submitted Google transcription is pending and shows frozen provider details', async () => {
    const value = recording();
    value.state = 'waiting_transcription'; value.stage = 'transcribe'; value.transcription_provider = 'google_batch'; value.transcription_model = 'batch-model';
    mocks.list.mockResolvedValue({ items: [value], total: 1 });
    mocks.get.mockResolvedValue(value);
    const wrapper = mount(CallRecordingsView);
    await flushPromises();
    await wrapper.findAll('button').find(button => button.text().includes('Тестовая запись'))!.trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('уже отправлена в Google');
    expect(wrapper.text()).toContain('Google Speech · batch-model');
    wrapper.unmount();
  });

  it('does not poll or accept on opening and adopts only the chosen edited proposal', async () => {
    const wrapper = mount(CallRecordingsView);
    await flushPromises();
    expect(mocks.poll).not.toHaveBeenCalled();
    expect(mocks.adopt).not.toHaveBeenCalled();
    const row = wrapper.findAll('button').find(button => button.text().includes('Тестовая запись'))!;
    await row.trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('Неизвестно — уточните вручную');
    const cards = wrapper.findAllComponents(CallProposalCard);
    expect(cards).toHaveLength(2);
    await cards[0]!.get('textarea').setValue('Дослать чёткое фото свидетельства');
    await cards[0]!.get('form').trigger('submit');
    await flushPromises();
    expect(mocks.adopt).toHaveBeenCalledTimes(1);
    expect(mocks.adopt).toHaveBeenCalledWith(4, 10, expect.objectContaining({ expected_version: 7, task: expect.objectContaining({ text: 'Дослать чёткое фото свидетельства', due_at: null }) }));
    wrapper.unmount();
  });

  it('keeps polling off when the server pipeline is disabled', async () => {
    mocks.status.mockResolvedValue(connection(false));
    const wrapper = mount(CallRecordingsView);
    await flushPromises();
    expect(wrapper.get('[data-testid="poll-call-recordings"]').attributes('disabled')).toBeDefined();
    expect(wrapper.text()).toContain('Обработка записей выключена на сервере');
    expect(mocks.poll).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('shows accepted resource links and blocks adoption during a failed stage', async () => {
    const value = recording();
    value.state = 'failed'; value.stage = 'structure'; value.last_error_code = 'timeout';
    value.proposals![0]!.accepted_url = '/manager/tasks?taskId=12';
    const wrapper = mount(CallProposalCard, { props: { proposal: value.proposals![0]!, version: 7, disabled: true } });
    expect(wrapper.get('a').attributes('href')).toBe('/manager/tasks?taskId=12');
    expect(wrapper.find('[data-testid="adopt-call-proposal"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it('discloses the incoming clarification task and leaves the desired time editable', async () => {
    const wrapper = mount(CallProposalCard, { props: { proposal: { id: 3, kind: 'incoming', evidence: 'Обслуживание в Уручье', needs_clarification: ['Адрес требует уточнения'], payload: { request_text: 'Обслуживание в Уручье', region_text: 'Уручье', clarification_requested: true } }, version: 7, disabled: false } });
    expect(wrapper.text()).toContain('Также сохранить поручение');
    expect(wrapper.text()).toContain('Сохранение не подтверждает выезд');
    expect((wrapper.get('input[type="checkbox"]').element as HTMLInputElement).checked).toBe(true);
    wrapper.unmount();
  });

  it.each([false, true])('shows a desired day without inventing an hour; manual time=%s', async (manual) => {
    const wrapper = mount(CallProposalCard, { props: { proposal: { id: 3, kind: 'incoming', evidence: 'Обслуживание завтра утром', needs_clarification: ['Время требует уточнения'], requested_date: '2026-10-09', date_precision: 'date', payload: { request_text: 'Обслуживание завтра утром', requested_time_text: 'завтра утром', requested_at: null } }, version: 7, disabled: false } });
    expect(wrapper.get('[data-testid="call-desired-day"]').text()).toContain('09.10.2026');
    expect(wrapper.text()).not.toContain('00:00');
    const input = wrapper.get('input[type="datetime-local"]');
    expect((input.element as HTMLInputElement).value).toBe('');
    if (manual) await input.setValue('2026-10-09T10:30');
    await wrapper.get('form').trigger('submit');
    const payload = wrapper.emitted('adopt')![0]![1] as { incoming: { requested_at: string | null; requested_time_text: string } };
    expect(payload.incoming.requested_at).toBe(manual ? '2026-10-09T10:30:00+03:00' : null);
    expect(payload.incoming.requested_time_text).toBe('завтра утром');
    wrapper.unmount();
  });
});

it('only accepts direct Drive ids and Google Drive links', () => {
  expect(driveId('https://drive.google.com/drive/folders/chosen-folder-000001')).toBe('chosen-folder-000001');
  expect(driveId('https://drive.google.com/file/d/safe-file-00000001/view')).toBe('safe-file-00000001');
  expect(driveId('https://example.test/drive/folders/chosen-folder-000001')).toBe('');
});

it.each(['call_google_not_configured', 'call_google_access_denied', 'call_google_provider_error', 'call_google_invalid_audio', 'call_google_operation_failed', 'call_google_wait_expired'])('shows a safe explanation for %s', (code) => {
  expect(callErrorLabel(code)).not.toBe('Провайдер временно недоступен или вернул некорректный результат');
  expect(callErrorLabel(code)).not.toContain(code);
});
