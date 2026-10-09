import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { CallDriveStatus, CallRecordingResponse } from '../src/client';

const mocks = vi.hoisted(() => ({ status: vi.fn(), list: vi.fn(), get: vi.fn(), authorize: vi.fn(), folder: vi.fn(), disconnect: vi.fn(), poll: vi.fn(), retry: vi.fn(), metadata: vi.fn(), adopt: vi.fn() }));
vi.mock('../src/services/call-recordings-api', async (original) => ({ ...(await original<typeof import('../src/services/call-recordings-api')>()), callRecordingsApi: mocks }));
import CallRecordingsView from '../src/views/CallRecordingsView.vue';
import CallProposalCard from '../src/components/calls/CallProposalCard.vue';
import { driveId } from '../src/services/call-recordings-api';

const connection = (enabled = true): CallDriveStatus => ({ connected: true, pipeline_enabled: enabled, transcription_configured: true, transcription_model: 'whisper-large-v3-turbo', structure_model: 'deepseek', folder_id: 'chosen-folder-000001', auto_poll_enabled: false, max_bytes: 10485760, max_duration_seconds: 600, max_files_per_poll: 5, max_recordings_per_day: 20, max_stage_attempts: 3 });
const recording = (): CallRecordingResponse => ({ id: 4, version: 7, file_id: 'safe-file-00000001', source_version: 'revision', source_checksum: 'md5', source_size: 500, source_url: 'https://drive.google.com/file/d/safe-file-00000001/view', filename: 'Тестовая запись.m4a', mime_type: 'video/3gpp', origin: 'drive_selected_folder', call_occurred_at: null, time_source: 'unknown', phone: null, state: 'ready_for_review', stage: 'proposals', stage_attempts: { transcribe: 1 }, last_error_code: null, audio_duration_seconds: 30, transcript: 'Дослать фото свидетельства. Нужен обратный звонок.', proposals: [
  { id: 10, kind: 'task', evidence: 'Дослать фото свидетельства', needs_clarification: [], payload: { text: 'Дослать фото свидетельства', description: 'Дослать фото свидетельства', due_at: null } },
  { id: 11, kind: 'callback', evidence: 'Нужен обратный звонок', needs_clarification: ['Контакт не подтверждён'], payload: { text: 'Перезвонить', due_at: null } },
] });

beforeEach(() => {
  vi.clearAllMocks();
  mocks.status.mockResolvedValue(connection());
  mocks.list.mockResolvedValue({ items: [recording()], total: 1 });
  mocks.get.mockResolvedValue(recording());
  mocks.adopt.mockResolvedValue({ resource_type: 'personal_task', resource_id: 12, resource_url: '/manager/tasks?taskId=12' });
});

describe('call recording review', () => {
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
});

it('only accepts direct Drive ids and Google Drive links', () => {
  expect(driveId('https://drive.google.com/drive/folders/chosen-folder-000001')).toBe('chosen-folder-000001');
  expect(driveId('https://drive.google.com/file/d/safe-file-00000001/view')).toBe('safe-file-00000001');
  expect(driveId('https://example.test/drive/folders/chosen-folder-000001')).toBe('');
});
