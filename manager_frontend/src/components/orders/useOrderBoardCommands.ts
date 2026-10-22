import { onScopeDispose, watch } from 'vue';
import type { ManagerOrderListItemResponse, ManagerOrderUpdatePayload } from '../../client';
import { ManagerOrdersService } from '../../client';
import { api } from '../../api';
import type { OrderCommandOwnership, OrderCommandToken } from '../../composables/useOrderCommandOwnership';
import { confirmDialog, promptDialog } from '../../services/ui-feedback';
import { getApiErrorMessage } from '../../utils/api-errors';
import { buildBoardTransitionPayload, needsExecutionWithoutPaymentConfirmation } from './order-transition';
import { formatMoney } from './order-utils';

type Options = {
  ownership: OrderCommandOwnership;
  find: (id: number) => ManagerOrderListItemResponse | undefined;
  actionable: () => boolean;
  refresh: () => Promise<boolean>;
  notify: (message: string) => void;
};
export const useOrderBoardCommands = (options: Options) => {
  const { ownership } = options;
  let dialogs = new AbortController();
  watch(ownership.context, () => { dialogs.abort(); dialogs = new AbortController(); }, { flush: 'sync' });
  onScopeDispose(() => dialogs.abort());
  const start = (orderId: number) => {
    if (!options.actionable() || !options.find(orderId)) return null;
    const token = ownership.begin(orderId);
    if (!token) options.notify(`Заказ №${orderId} уже сохраняется`);
    return token;
  };
  const requireCurrent = (token: OrderCommandToken) => {
    if (!ownership.current(token) || !options.actionable() || !options.find(token.orderId)) {
      throw new Error('Контекст заказов изменился. Закройте диалог и повторите действие в текущей очереди.');
    }
  };
  // Persistence and revalidation have separate outcomes. Never roll back a saved command.
  const save = async (token: OrderCommandToken, persist: () => Promise<unknown>, success: string) => {
    requireCurrent(token);
    await persist();
    if (!ownership.current(token)) return;
    let refreshed = false;
    try { refreshed = await options.refresh(); } catch { /* Board exposes the read failure independently. */ }
    if (!ownership.current(token)) return;
    options.notify(refreshed ? success : `${success}. Не удалось обновить доску — повторите загрузку.`);
  };
  const rename = async (payload: { orderId: number; title: string | null }) => {
    const token = start(payload.orderId); if (!token) return;
    try { await save(token, () => api.patchManagerOrder(payload.orderId, { title: payload.title?.trim() || null }), 'Название заказа сохранено'); }
    catch (error) { if (ownership.current(token)) options.notify(`Не удалось сохранить название: ${getApiErrorMessage(error)}`); }
    finally { ownership.finish(token); }
  };
  const refuse = async (payload: { orderId: number }) => {
    const token = start(payload.orderId); if (!token) return;
    try {
      await promptDialog({ signal: dialogs.signal,
        title: 'Пометить заказ отказом', inputLabel: 'Причина отказа или неуспешного завершения',
        inputKind: 'textarea', placeholder: 'Кратко опишите причину', confirmText: 'Пометить отказом', variant: 'danger',
        onConfirm: async value => save(token, () => api.patchManagerOrder(payload.orderId, {
          status: 'closed', closing_result: 'lost', reject_reason: value?.trim() || 'Без пояснения',
        }), 'Заказ помечен отказом'),
        getErrorMessage: error => `Не удалось закрыть отказ: ${getApiErrorMessage(error)}`,
      });
    } finally { ownership.finish(token); }
  };
  const move = async (payload: { orderId: number; oldStatus: string; newStatus: string }) => {
    if (payload.newStatus === 'closed_lost') return refuse(payload);
    const token = start(payload.orderId); if (!token) return;
    const item = options.find(payload.orderId)!;
    const persist = (update: ManagerOrderUpdatePayload) => save(token, () => api.patchManagerOrder(payload.orderId, update), 'Статус обновлён');
    try {
      if (needsExecutionWithoutPaymentConfirmation(item, payload.newStatus)) {
        await promptDialog({ signal: dialogs.signal, title: 'Назначить работы без оплаты?',
          description: 'У заказа нет полной зарегистрированной оплаты. Укажите причину перевода в работы.',
          inputLabel: 'Причина', initialValue: 'Доверенный клиент', inputKind: 'textarea', required: true,
          confirmText: 'Назначить работы', variant: 'warning',
          onConfirm: async value => {
            requireCurrent(token);
            const update = buildBoardTransitionPayload(options.find(payload.orderId)!, payload.newStatus, value || 'Без предоплаты');
            if (!update) throw new Error('Недоступный статус заказа');
            await persist(update);
          }, getErrorMessage: error => `Не удалось назначить работы: ${getApiErrorMessage(error)}`,
        });
      } else {
        const update = buildBoardTransitionPayload(item, payload.newStatus);
        if (update) await persist(update);
      }
    } catch (error) { if (ownership.current(token)) options.notify(`Ошибка обновления статуса: ${getApiErrorMessage(error)}`); }
    finally { ownership.finish(token); }
  };
  const closeDebt = async (payload: { orderId: number }) => {
    const token = start(payload.orderId); if (!token) return;
    const amount = Number(options.find(payload.orderId)?.balance_due || 0);
    try {
      if (amount <= 0) { options.notify('Долг уже закрыт'); return; }
      await confirmDialog({ signal: dialogs.signal, title: `Закрыть долг по заказу #${payload.orderId}?`,
        description: `Будет добавлена оплата ${formatMoney(amount)}.`, confirmText: 'Добавить оплату', variant: 'warning',
        onConfirm: () => save(token, () => ManagerOrdersService.addManagerOrderPayment(payload.orderId, {
          amount, currency: 'BYN', type: 'postpayment', comment: 'Закрытие долга из канбан-карточки',
        }), 'Долг закрыт'), getErrorMessage: error => `Не удалось закрыть долг: ${getApiErrorMessage(error)}`,
      });
    } finally { ownership.finish(token); }
  };
  return { rename, refuse, move, closeDebt };
};
