import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';
import { getApiErrorMessage } from '../../../utils/api-errors';
import { managerSession } from '../../../services/manager-session';
import {
  googleDocumentEditorApi,
  type GoogleDocumentEditSession,
  type GoogleDocumentSyncResult,
  type GoogleDocumentEditTarget,
} from '../integrations/google-document-editor-api';

type GoogleDocumentEditorInput = {
  notify: (message: string, type?: 'success' | 'error') => void;
  onSynced?: (target: GoogleDocumentEditTarget, result: GoogleDocumentSyncResult) => void | Promise<void>;
};

const targetKey = (target: GoogleDocumentEditTarget) => target.kind === 'managed-document'
  ? `document:${target.documentId}`
  : `template:${target.templateId}:${target.versionId}`;

export const useGoogleDocumentEditor = (input: GoogleDocumentEditorInput) => {
  const connectionState = ref<'loading' | 'connected' | 'disconnected'>('loading');
  const accountLabel = ref<string | null>(null);
  const sessions = reactive<Record<string, GoogleDocumentEditSession | null | undefined>>({});
  const busyKeys = reactive(new Set<string>());
  const trackedTargets = new Map<string, GoogleDocumentEditTarget>();
  const connected = computed(() => connectionState.value === 'connected');
  const canConnect = computed(() => ['owner', 'admin'].includes(String(
    managerSession.auth.value?.role || managerSession.currentUserRole.value || '',
  )));
  let returnRefresh: Promise<void> | null = null;
  let returnRefreshTimer: ReturnType<typeof window.setTimeout> | null = null;

  const refreshConnection = async (silent = false) => {
    if (!silent) connectionState.value = 'loading';
    try {
      const status = await googleDocumentEditorApi.getConnectionStatus();
      accountLabel.value = status.account_label;
      connectionState.value = status.connected ? 'connected' : 'disconnected';
    } catch {
      connectionState.value = 'disconnected';
    }
  };

  const connect = async () => {
    if (!canConnect.value) return;
    const popup = window.open('about:blank', '_blank');
    if (popup) popup.opener = null;
    try {
      const response = await googleDocumentEditorApi.getAuthorizationUrl();
      if (popup) popup.location.replace(response.url);
      else window.location.assign(response.url);
    } catch (error) {
      popup?.close();
      input.notify(`Не удалось открыть подключение Google: ${getApiErrorMessage(error)}`, 'error');
    }
  };

  const getSession = (target: GoogleDocumentEditTarget) => sessions[targetKey(target)] || null;
  const isBusy = (target: GoogleDocumentEditTarget) => busyKeys.has(targetKey(target));

  const loadSession = async (target: GoogleDocumentEditTarget) => {
    trackedTargets.set(targetKey(target), target);
    if (!connected.value) return;
    const key = targetKey(target);
    try {
      sessions[key] = await googleDocumentEditorApi.getSession(target);
    } catch {
      // Session discovery is optional: the first edit click can create it.
      sessions[key] = null;
    }
  };

  const open = async (target: GoogleDocumentEditTarget) => {
    if (!connected.value) return;
    const key = targetKey(target);
    trackedTargets.set(key, target);
    const popup = window.open('about:blank', '_blank');
    if (popup) popup.opener = null;
    busyKeys.add(key);
    try {
      const existing = sessions[key];
      const session = existing?.edit_url
        ? existing
        : await googleDocumentEditorApi.createSession(target);
      sessions[key] = session;
      if (!session.edit_url) throw new Error('Google не вернул ссылку для редактирования');
      if (popup) popup.location.replace(session.edit_url);
      else window.location.assign(session.edit_url);
    } catch (error) {
      popup?.close();
      input.notify(`Не удалось открыть Google Docs: ${getApiErrorMessage(error)}`, 'error');
    } finally {
      busyKeys.delete(key);
    }
  };

  const sync = async (target: GoogleDocumentEditTarget) => {
    if (!connected.value) return false;
    const key = targetKey(target);
    if (busyKeys.has(key)) return false;
    trackedTargets.set(key, target);
    busyKeys.add(key);
    try {
      const result = await googleDocumentEditorApi.syncSession(target);
      sessions[key] = result.session;
      input.notify(target.kind === 'template-version'
        ? result.newTemplateVersionCreated
          ? 'Изменения сохранены как новая версия шаблона.'
          : 'Шаблон уже синхронизирован — новых изменений нет.'
        : 'Изменения из Google сохранены в истории документа.');
      await input.onSynced?.(target, result);
      return true;
    } catch (error) {
      input.notify(`Не удалось забрать изменения: ${getApiErrorMessage(error)}`, 'error');
      return false;
    } finally {
      busyKeys.delete(key);
    }
  };

  const refreshAfterReturn = () => {
    if (document.visibilityState === 'hidden' || returnRefresh) return;
    returnRefresh = (async () => {
      await refreshConnection(true);
      if (!connected.value) return;
      const targets = [...trackedTargets.values()];
      await Promise.all(targets.map((target) => loadSession(target)));
      const changedTargets = targets.filter((target) => {
        const session = sessions[targetKey(target)];
        return session?.status === 'changed' && session.can_edit;
      });
      await Promise.all(changedTargets.map((target) => sync(target)));
    })().finally(() => {
      returnRefresh = null;
    });
  };

  const onVisibilityChange = () => {
    if (document.visibilityState !== 'hidden') refreshAfterEditorReturn();
  };

  const refreshAfterEditorReturn = () => {
    refreshAfterReturn();
    if (returnRefreshTimer !== null) window.clearTimeout(returnRefreshTimer);
    // Google can finish autosaving a binary Office file shortly after its tab
    // loses focus. One delayed pass catches that revision without polling.
    returnRefreshTimer = window.setTimeout(refreshAfterReturn, 1500);
  };

  onMounted(() => {
    window.addEventListener('focus', refreshAfterEditorReturn);
    document.addEventListener('visibilitychange', onVisibilityChange);
  });
  onBeforeUnmount(() => {
    window.removeEventListener('focus', refreshAfterEditorReturn);
    document.removeEventListener('visibilitychange', onVisibilityChange);
    if (returnRefreshTimer !== null) window.clearTimeout(returnRefreshTimer);
  });

  void refreshConnection();

  return {
    accountLabel,
    canConnect,
    connect,
    connected,
    connectionState,
    getSession,
    isBusy,
    loadSession,
    open,
    refreshConnection,
    sync,
  };
};
