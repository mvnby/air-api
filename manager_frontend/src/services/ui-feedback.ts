import { reactive, readonly } from 'vue';

export type DialogVariant = 'default' | 'warning' | 'danger';
export type DialogInputKind = 'text' | 'textarea';
export type NotificationVariant = 'success' | 'error' | 'info';

type AsyncDialogAction = (value?: string) => void | Promise<void>;

export type ConfirmDialogOptions = {
  title: string;
  description?: string;
  confirmText?: string;
  cancelText?: string;
  variant?: DialogVariant;
  onConfirm?: AsyncDialogAction;
  getErrorMessage?: (error: unknown) => string;
};

export type PromptDialogOptions = ConfirmDialogOptions & {
  inputLabel?: string;
  initialValue?: string;
  placeholder?: string;
  inputKind?: DialogInputKind;
  required?: boolean;
  validate?: (value: string) => string | null;
};

export type MessageDialogOptions = Omit<ConfirmDialogOptions, 'cancelText' | 'onConfirm'>;

type DialogRequest = {
  kind: 'confirm' | 'prompt' | 'message';
  options: ConfirmDialogOptions | PromptDialogOptions;
  resolve: (value: boolean | string | null) => void;
};

export type DialogState = {
  open: boolean;
  kind: DialogRequest['kind'];
  title: string;
  description: string;
  confirmText: string;
  cancelText: string;
  variant: DialogVariant;
  inputLabel: string;
  inputValue: string;
  placeholder: string;
  inputKind: DialogInputKind;
  required: boolean;
  loading: boolean;
  error: string;
};

export type NotificationState = {
  id: number;
  message: string;
  variant: NotificationVariant;
};

const state = reactive<DialogState>({
  open: false,
  kind: 'confirm',
  title: '',
  description: '',
  confirmText: 'Подтвердить',
  cancelText: 'Отмена',
  variant: 'default',
  inputLabel: '',
  inputValue: '',
  placeholder: '',
  inputKind: 'text',
  required: false,
  loading: false,
  error: '',
});

const notifications = reactive<NotificationState[]>([]);
const queue: DialogRequest[] = [];
let activeRequest: DialogRequest | null = null;
let notificationId = 0;

const presentNext = () => {
  if (activeRequest || !queue.length) return;
  activeRequest = queue.shift()!;
  const options = activeRequest.options as PromptDialogOptions;
  Object.assign(state, {
    open: true,
    kind: activeRequest.kind,
    title: options.title,
    description: options.description || '',
    confirmText: options.confirmText || (activeRequest.kind === 'message' ? 'Понятно' : 'Подтвердить'),
    cancelText: options.cancelText || 'Отмена',
    variant: options.variant || 'default',
    inputLabel: options.inputLabel || '',
    inputValue: options.initialValue || '',
    placeholder: options.placeholder || '',
    inputKind: options.inputKind || 'text',
    required: Boolean(options.required),
    loading: false,
    error: '',
  });
};

const requestDialog = <T extends boolean | string | null>(
  kind: DialogRequest['kind'],
  options: ConfirmDialogOptions | PromptDialogOptions,
) => new Promise<T>((resolve) => {
  queue.push({ kind, options, resolve: resolve as DialogRequest['resolve'] });
  presentNext();
});

export const confirmDialog = (options: ConfirmDialogOptions) => requestDialog<boolean>('confirm', options);

export const promptDialog = (options: PromptDialogOptions) => requestDialog<string | null>('prompt', options);

export const messageDialog = (options: MessageDialogOptions) => (
  requestDialog<boolean>('message', options).then(() => undefined)
);

export const notify = (message: string, variant: NotificationVariant = 'info', durationMs = 3500) => {
  const item = { id: ++notificationId, message, variant };
  notifications.push(item);
  globalThis.setTimeout(() => dismissNotification(item.id), durationMs);
};

export const dismissNotification = (id: number) => {
  const index = notifications.findIndex((item) => item.id === id);
  if (index >= 0) notifications.splice(index, 1);
};

const finish = (value: boolean | string | null) => {
  const request = activeRequest;
  if (!request) return;
  state.open = false;
  activeRequest = null;
  request.resolve(value);
  globalThis.setTimeout(presentNext, 0);
};

export const cancelActiveDialog = () => {
  if (!activeRequest || state.loading) return;
  finish(activeRequest.kind === 'prompt' ? null : false);
};

export const setDialogInput = (value: string) => {
  state.inputValue = value;
  state.error = '';
};

export const submitActiveDialog = async () => {
  if (!activeRequest || state.loading) return;
  const options = activeRequest.options as PromptDialogOptions;
  const value = state.inputValue.trim();
  if (activeRequest.kind === 'prompt') {
    const validationError = options.validate?.(value)
      || (options.required && !value ? 'Заполните поле, чтобы продолжить.' : null);
    if (validationError) {
      state.error = validationError;
      return;
    }
  }

  state.loading = true;
  state.error = '';
  try {
    await options.onConfirm?.(activeRequest.kind === 'prompt' ? value : undefined);
    finish(activeRequest.kind === 'prompt' ? value : true);
  } catch (error) {
    state.error = options.getErrorMessage?.(error) || 'Не удалось выполнить действие. Попробуйте ещё раз.';
    state.loading = false;
  }
};

export const uiDialogState = readonly(state);
export const uiNotifications = readonly(notifications);

export const resetUiFeedbackForTests = () => {
  queue.splice(0);
  activeRequest = null;
  Object.assign(state, { open: false, loading: false, error: '', inputValue: '' });
  notifications.splice(0);
};
