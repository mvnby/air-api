import { OpenAPI } from '../client/core/OpenAPI';
import { request } from '../client/core/request';
import type { CallDriveStatus, CallDriveFileResponse, CallDriveFileListResponse, CallRecordingResponse, CallRecordingListResponse, CallAdoptPayload, CallAdoptionResponse, CallPollResponse } from '../client';

export type { CallDriveStatus, CallRecordingResponse, CallProposalResponse } from '../client';
export type CallTranscriptionProvider = NonNullable<CallDriveStatus['transcription_provider']>;
export type CallDriveFile = CallDriveFileResponse;
export type CallDriveFilesQuery = { date_from?: string; date_to?: string; query?: string; page_token?: string };
export type CallDriveFilesResponse = CallDriveFileListResponse;
export const callProviderLabel = (provider?: string | null) => provider === 'google_batch' ? 'Google Speech' : provider === 'groq' ? 'Groq' : provider === 'soniox' ? 'Soniox' : 'провайдер распознавания';
const base = '/api/manager/call-recordings';

export const driveId = (value: string): string => {
  const trimmed = value.trim();
  if (/^[A-Za-z0-9_-]{10,160}$/.test(trimmed)) return trimmed;
  try {
    const url = new URL(trimmed);
    if (url.hostname !== 'drive.google.com' || url.protocol !== 'https:') return '';
    return url.pathname.match(/\/(?:folders|d)\/([A-Za-z0-9_-]{10,160})(?:\/|$)/)?.[1] || url.searchParams.get('id') || '';
  } catch { return ''; }
};

export const callRecordingsApi = {
  status: () => request<CallDriveStatus>(OpenAPI, { method: 'GET', url: `${base}/connection` }),
  authorize: () => request<{ url: string }>(OpenAPI, { method: 'GET', url: `${base}/authorization-url` }),
  folder: (folderId: string, autoPollEnabled: boolean, transcriptionProvider?: CallTranscriptionProvider) => request<CallDriveStatus>(OpenAPI, { method: 'PUT', url: `${base}/connection/folder`, body: { folder_id: folderId, auto_poll_enabled: autoPollEnabled, ...(transcriptionProvider ? { transcription_provider: transcriptionProvider } : {}) }, mediaType: 'application/json' }),
  disconnect: () => request<CallDriveStatus>(OpenAPI, { method: 'DELETE', url: `${base}/connection` }),
  poll: (fileId: string | null) => request<CallPollResponse>(OpenAPI, { method: 'POST', url: `${base}/poll`, body: { file_id: fileId }, mediaType: 'application/json' }),
  driveFiles: (query: CallDriveFilesQuery = {}) => request<CallDriveFilesResponse>(OpenAPI, { method: 'GET', url: `${base}/drive/files`, query }),
  list: (offset = 0) => request<CallRecordingListResponse>(OpenAPI, { method: 'GET', url: base, query: { limit: 50, offset } }),
  get: (id: number) => request<CallRecordingResponse>(OpenAPI, { method: 'GET', url: `${base}/${id}` }),
  metadata: (id: number, version: number, time: string | null, phone: string | null) => request<CallRecordingResponse>(OpenAPI, { method: 'PATCH', url: `${base}/${id}/metadata`, body: { expected_version: version, call_occurred_at: time, phone }, mediaType: 'application/json' }),
  retry: (id: number, version: number) => request<CallRecordingResponse>(OpenAPI, { method: 'POST', url: `${base}/${id}/retry`, body: { expected_version: version }, mediaType: 'application/json' }),
  adopt: (id: number, proposalId: number, payload: CallAdoptPayload) => request<CallAdoptionResponse>(OpenAPI, { method: 'POST', url: `${base}/${id}/proposals/${proposalId}/adopt`, body: payload, mediaType: 'application/json' }),
};

export const callStateLabel = (state: string, provider?: string | null) => ({ observing: 'Проверяется завершение загрузки', queued: 'В очереди', processing: 'Обрабатывается', waiting_transcription: provider === 'soniox' ? 'Ожидает результат распознавания Soniox' : provider === 'google_batch' || !provider ? 'Ожидает результат распознавания Google (до 24 часов)' : 'Ожидает результат распознавания', ready_for_review: 'Готово к разбору', failed: 'Ошибка этапа', reconnect_required: 'Требуется подключение или настройка', manual_review: 'Нужен ручной разбор' })[state] || state;
export const callStageLabel = (stage: string) => ({ download: 'Получение и проверка аудио', transcribe: 'Распознавание речи', structure: 'Разбор договорённостей', proposals: 'Предлагаемые действия' })[stage] || stage;
export const callErrorLabel = (code: string) => ({
  google_drive_access_denied: 'Google отклонил доступ — переподключите аккаунт',
  call_drive_not_connected: 'Подключите Google Диск',
  credentials_unreadable: 'Сохранённое подключение временно недоступно',
  credential_encryption_unavailable: 'Хранилище подключений временно недоступно',
  call_connection_changed: 'Подключение или папка изменились',
  call_transcription_not_configured: 'Распознавание речи не настроено',
  call_google_not_configured: 'Google Speech не настроен на сервере',
  call_google_access_denied: 'Google Speech отклонил доступ — проверьте настройку сервера',
  call_google_provider_error: 'Google Speech не смог обработать запись',
  call_google_invalid_audio: 'Google Speech не смог прочитать аудио',
  call_google_operation_failed: 'Задание Google Speech завершилось ошибкой',
  call_google_wait_expired: 'Google Speech не завершил распознавание в пределах срока — разберите запись вручную',
  call_soniox_not_configured: 'Распознавание Soniox не настроено на сервере',
  call_soniox_access_denied: 'Soniox отклонил доступ — проверьте настройку сервера',
  call_soniox_provider_error: 'Soniox временно недоступен — результат можно проверить позже',
  call_soniox_invalid_audio: 'Soniox не смог распознать эту запись — разберите её вручную',
  call_soniox_operation_failed: 'Задание Soniox завершилось ошибкой — разберите запись вручную',
  call_soniox_submission_uncertain: 'Не удалось подтвердить отправку в Soniox. Требуется ручной разбор; повторная отправка может создать второе задание',
  call_soniox_wait_expired: 'Soniox не завершил распознавание в пределах срока — разберите запись вручную',
  call_soniox_cleanup_pending: 'Удаление временного материала Soniox ещё не завершено; повторите незавершённый этап',
  not_configured: 'AI для разбора не настроен',
  authentication_rejected: 'Провайдер отклонил доступ — проверьте настройку AI',
  call_source_changed: 'Исходный файл изменился — проверьте папку ещё раз',
  call_upload_changed: 'Файл ещё загружается или его содержимое изменилось',
  call_file_outside_folder: 'Файл отсутствует в выбранной папке',
  call_stage_exhausted: 'Лимит попыток исчерпан — нужен ручной разбор',
  call_job_exhausted: 'Лимит восстановления исчерпан — нужен ручной разбор',
  call_metadata_changed: 'Исходные данные уточнены — обновите предложения',
  BotVoiceAudioValidationError: 'Не удалось прочитать аудиозапись или превышен лимит длительности',
  BotVoiceAudioToolUnavailableError: 'Подготовка аудио временно недоступна на сервере',
  BotVoiceTranscriptionInvalidAudioError: 'Речь не распознана — разберите запись вручную',
  PermissionError: 'Права сотрудника отозваны',
})[code] || 'Провайдер временно недоступен или вернул некорректный результат';
export const minskDateTime = (value?: string | null) => value ? new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Minsk', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value)).replace(' ', 'T') : '';
export const minskIso = (value: string) => value ? `${value}:00+03:00` : null;
