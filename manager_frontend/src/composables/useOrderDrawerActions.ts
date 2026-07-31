import type { Ref } from 'vue';
import { api } from '../api';
import type { ManagerOrderDetailResponse } from '../client';
import { ManagerOrdersService } from '../client';
import { confirmDialog } from '../services/ui-feedback';
import { getApiErrorMessage } from '../utils/api-errors';

type ToastHandler = (message: string, type?: 'success' | 'error') => void;

type UseOrderDrawerActionsOptions = {
  order: Readonly<Ref<ManagerOrderDetailResponse | null>>;
  displayOrderTitle: Readonly<Ref<string>>;
  hasUnsavedChanges: Readonly<Ref<boolean>>;
  localFormError: Ref<string>;
  persistDraft: () => void;
  clearDraft: () => void;
  setToast: ToastHandler;
  onBeforeClose: () => void;
  onModelValue: (open: boolean) => void;
  onUpdated: (order: ManagerOrderDetailResponse) => void;
  onDeleted: (orderId: number) => void;
};

export const useOrderDrawerActions = ({
  order,
  displayOrderTitle,
  hasUnsavedChanges,
  localFormError,
  persistDraft,
  clearDraft,
  setToast,
  onBeforeClose,
  onModelValue,
  onUpdated,
  onDeleted,
}: UseOrderDrawerActionsOptions) => {
  const copyText = async (value: string | null | undefined, label: string) => {
    const normalized = String(value || '').trim();
    if (!normalized) {
      setToast(`${label} отсутствует`, 'error');
      return;
    }
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(normalized);
      else {
        const textarea = document.createElement('textarea');
        textarea.value = normalized;
        textarea.setAttribute('readonly', 'true');
        textarea.style.position = 'absolute';
        textarea.style.left = '-9999px';
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
      }
      setToast(`${label} скопирован`, 'success');
    } catch {
      setToast(`Не удалось скопировать ${label.toLowerCase()}`, 'error');
    }
  };

  const toggleHold = async () => {
    if (!order.value) return;
    const hold = !order.value.is_on_hold;
    try {
      const updatedOrder = await api.patchManagerOrder(order.value.id, {
        is_on_hold: hold,
        on_hold_reason: hold ? 'Переговоры / Ручная пауза' : '',
      });
      onUpdated(updatedOrder);
      setToast(hold ? 'Сделка поставлена на паузу' : 'Сделка снята с паузы', 'success');
    } catch {
      setToast('Ошибка паузы', 'error');
    }
  };

  const closeDrawer = async (options?: { force?: boolean } | Event) => {
    const isDomEvent = typeof Event !== 'undefined' && options instanceof Event;
    const force = Boolean(options && !isDomEvent && (options as { force?: boolean }).force);
    if (!force && hasUnsavedChanges.value) {
      persistDraft();
      const discard = await confirmDialog({
        title: 'Закрыть без сохранения?',
        description: 'В карточке есть несохранённые изменения. Они будут потеряны.',
        confirmText: 'Закрыть без сохранения',
        variant: 'warning',
      });
      if (!discard) return;
    }
    onBeforeClose();
    clearDraft();
    onModelValue(false);
  };

  const deleteOrder = async () => {
    if (!order.value?.id) return;
    const currentOrder = order.value;
    const label = `Заказ №${currentOrder.id}${displayOrderTitle.value ? ` «${displayOrderTitle.value}»` : ''}`;
    const proceed = await confirmDialog({
      title: `Удалить ${label}?`,
      description: 'Заказ будет безвозвратно удалён вместе со связанными документами, выездами и платежами.',
      confirmText: 'Удалить заказ',
      variant: 'danger',
    });
    if (!proceed) return;
    try {
      await ManagerOrdersService.deleteManagerOrder(currentOrder.id);
      setToast('Заказ успешно удален', 'success');
      window.setTimeout(() => {
        onDeleted(currentOrder.id);
        void closeDrawer({ force: true });
      }, 1500);
    } catch (error) {
      localFormError.value = getApiErrorMessage(error) || 'Ошибка при удалении заказа';
    }
  };

  return { closeDrawer, copyText, deleteOrder, toggleHold };
};
