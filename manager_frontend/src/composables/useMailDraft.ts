import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue';
import { mailApi, mailCommandKey, type MailDraftFields, type MailMessage } from '../services/mail-workspace-api';
import { getApiErrorMessage } from '../utils/api-errors';
import { registerUnsavedNavigationGuard } from '../services/unsaved-navigation-guard';

const addresses = (value: string) => value.split(/[;,\n]/).map(item => item.trim()).filter(Boolean);
const conflict = (error: unknown) => (error as { status?: number })?.status === 409;

export function useMailDraft(initial: MailMessage, onSaved: (draft: MailMessage) => void) {
  const draft = ref(initial);
  const model = reactive({ account_id: initial.account_id || 'system', to: initial.to.join(', '), cc: initial.cc.join(', '), bcc: initial.bcc.join(', '), subject: initial.subject, body_text: initial.body_text, order_id: initial.order_id ? String(initial.order_id) : '', customer_id: initial.customer_id ? String(initial.customer_id) : '' });
  const fields = (): MailDraftFields => ({ account_id: model.account_id, to: addresses(model.to), cc: addresses(model.cc), bcc: addresses(model.bcc), subject: model.subject, body_text: model.body_text, order_id: model.order_id ? Number(model.order_id) : null, customer_id: model.customer_id ? Number(model.customer_id) : null });
  const savedContents = ref(JSON.stringify(fields()));
  const dirty = computed(() => JSON.stringify(fields()) !== savedContents.value);
  const saving = ref(false);
  const busy = ref(false);
  const error = ref('');
  const hasConflict = ref(false);
  const preview = ref<MailMessage | null>(null);
  const sendUncertain = ref(false);
  const editable = computed(() => draft.value.status === 'draft' && !preview.value && !busy.value && !sendUncertain.value);
  const saveLabel = computed(() => hasConflict.value ? 'Конфликт изменений' : error.value ? 'Не сохранено' : saving.value ? 'Сохраняем…' : dirty.value ? 'Есть изменения' : `Сохранено · версия ${draft.value.version}`);
  let timer: ReturnType<typeof setTimeout> | undefined;
  let activeSave: Promise<boolean> | null = null;
  let disposed = false;

  const stopTimer = () => { if (timer) clearTimeout(timer); timer = undefined; };
  const updateResult = (result: MailMessage) => { draft.value = result; onSaved(result); };
  const fail = (cause: unknown) => {
    hasConflict.value = conflict(cause);
    error.value = hasConflict.value
      ? 'Черновик изменён в другом окне или ChatGPT. Ваш текст остаётся здесь. Откройте актуальную версию перед дальнейшим редактированием и отправкой.'
      : getApiErrorMessage(cause);
  };

  const save = async (): Promise<boolean> => {
    stopTimer();
    if (activeSave) return activeSave;
    if (hasConflict.value) return false;
    if (!dirty.value) return true;
    if (draft.value.status !== 'draft' || sendUncertain.value) return false;
    saving.value = true;
    error.value = '';
    activeSave = (async () => {
      try {
        while (dirty.value) {
          const snapshot = fields();
          const saved = await mailApi.update(draft.value.id, draft.value.version, snapshot);
          updateResult(saved);
          savedContents.value = JSON.stringify(snapshot);
        }
        return true;
      } catch (cause) {
        fail(cause);
        return false;
      } finally {
        saving.value = false;
        activeSave = null;
      }
    })();
    return activeSave;
  };

  watch(model, () => {
    stopTimer();
    if (disposed || !editable.value || hasConflict.value || !dirty.value) return;
    timer = setTimeout(() => { void save(); }, 650);
  });

  const reload = async () => {
    if (saving.value || busy.value) return;
    busy.value = true;
    stopTimer();
    try {
      const result = await mailApi.get(draft.value.id);
      updateResult(result);
      Object.assign(model, { account_id: result.account_id || 'system', to: result.to.join(', '), cc: result.cc.join(', '), bcc: result.bcc.join(', '), subject: result.subject, body_text: result.body_text, order_id: result.order_id ? String(result.order_id) : '', customer_id: result.customer_id ? String(result.customer_id) : '' });
      savedContents.value = JSON.stringify(fields());
      error.value = '';
      hasConflict.value = false;
      preview.value = null;
      // A lost send response must be checked server-side; reopening a draft alone is not permission to resend.
      if (result.status !== 'draft') sendUncertain.value = false;
    } catch (cause) { fail(cause); }
    finally { busy.value = false; }
  };

  const showPreview = async () => {
    if (busy.value || !await save()) return;
    busy.value = true;
    try {
      const result = await mailApi.preview(draft.value.id);
      if (result.version !== draft.value.version) {
        fail({ status: 409 });
        return;
      }
      preview.value = result;
      error.value = '';
    } catch (cause) { fail(cause); }
    finally { busy.value = false; }
  };

  const confirmAndSend = async () => {
    const approved = preview.value;
    if (!approved || !approved.content_hash || !approved.csrf_token || busy.value || sendUncertain.value) return;
    busy.value = true;
    error.value = '';
    let sendStarted = false;
    try {
      await mailApi.approve(approved.id, approved.version, approved.content_hash, approved.csrf_token);
      sendStarted = true;
      updateResult(await mailApi.send(approved.id, approved.version, mailCommandKey(), approved.csrf_token));
      preview.value = null;
    } catch (cause) {
      fail(cause);
      preview.value = null;
      if (sendStarted) {
        sendUncertain.value = true;
        try {
          const result = await mailApi.get(approved.id);
          updateResult(result);
          if (['sent', 'failed', 'unknown', 'sending', 'pending'].includes(result.status)) sendUncertain.value = false;
        } catch { /* Keep the saved draft and the uncertain result visible. */ }
        error.value = 'Ответ на отправку не получен. Проверьте статус письма и папку отправленных у почтового провайдера. Повторная отправка может создать дубликат.';
      }
    } finally { busy.value = false; }
  };

  const confirmOnly = async () => {
    const approved = preview.value;
    if (!approved?.content_hash || !approved.csrf_token || busy.value || sendUncertain.value) return;
    busy.value = true;
    error.value = '';
    try {
      updateResult(await mailApi.approve(approved.id, approved.version, approved.content_hash, approved.csrf_token));
      preview.value = null;
    } catch (cause) { fail(cause); preview.value = null; }
    finally { busy.value = false; }
  };

  const changeAttachment = async (operation: (id: number, version: number) => Promise<MailMessage>) => {
    if (busy.value || !await save()) return;
    busy.value = true;
    try { updateResult(await operation(draft.value.id, draft.value.version)); error.value = ''; preview.value = null; }
    catch (cause) { fail(cause); }
    finally { busy.value = false; }
  };

  const beforeUnload = (event: BeforeUnloadEvent) => {
    if (dirty.value || saving.value || busy.value) { event.preventDefault(); event.returnValue = ''; }
  };
  window.addEventListener('beforeunload', beforeUnload);
  const unregister = registerUnsavedNavigationGuard(async () => !busy.value && await save());
  onBeforeUnmount(() => { disposed = true; stopTimer(); unregister(); window.removeEventListener('beforeunload', beforeUnload); });

  return { draft, model, dirty, saving, busy, error, hasConflict, preview, sendUncertain, editable, saveLabel, save, reload, showPreview, confirmAndSend, confirmOnly, changeAttachment };
}
