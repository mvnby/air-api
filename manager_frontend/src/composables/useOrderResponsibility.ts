import { computed, nextTick, onScopeDispose, ref, watch, type Ref } from 'vue';
import { ManagerOrdersService } from '../client';
import { orderResponsibilityApi, type OrderWithResponsibility } from '../services/order-responsibility';
import { managerSession } from '../services/manager-session';
import { managerStorefrontSelection } from '../services/manager-storefront-selection';
import { MANAGER_CAPABILITY, hasManagerCapability } from '../manager-capabilities';
import { getApiErrorMessage } from '../utils/api-errors';

type Options = {
  order: Readonly<Ref<OrderWithResponsibility | null>>; open: Readonly<Ref<boolean>>;
  otherBusy: Readonly<Ref<boolean>>; flush: () => Promise<boolean>;
  onUpdated: (order: OrderWithResponsibility) => void;
};
export const useOrderResponsibility = (options: Options) => {
  const busy = ref(false), paused = ref(false), error = ref('');
  const canAssign = computed(() => Boolean(managerSession.auth.value?.staff_user_id
    && hasManagerCapability(managerSession.auth.value, MANAGER_CAPABILITY.crmManage)
    && !managerSession.auth.value?.demo_read_only));
  const scope = computed(() => `${managerSession.auth.value?.staff_user_id}:${managerSession.auth.value?.tenant_id}:${managerStorefrontSelection.selectedSlug.value}:${options.order.value?.id}:${options.open.value}`);
  let generation = 0, disposed = false;
  watch(scope, () => { generation++; busy.value = false; paused.value = false; error.value = ''; }, { flush: 'sync' });
  onScopeDispose(() => { disposed = true; generation++; });
  const assign = async (staffUserId: number | null) => {
    if (!canAssign.value || busy.value || options.otherBusy.value || !options.open.value || !options.order.value) return false;
    const requestGeneration = generation, orderId = options.order.value.id;
    const expectedVersion = options.order.value.responsible_version ?? 0;
    const current = () => !disposed && generation === requestGeneration && options.open.value && options.order.value?.id === orderId;
    busy.value = true; error.value = '';
    try {
      // Drain queued writes while retaining the responsibility version the user actually saw.
      if (!await options.flush() || !current() || options.otherBusy.value || !canAssign.value) return false;
      paused.value = true;
      const result = await orderResponsibilityApi.assign(orderId, staffUserId, expectedVersion);
      if (!current()) return false;
      options.onUpdated(result); await nextTick();
      return true;
    } catch (cause) {
      if (!current()) return false;
      if ((cause as { status?: number })?.status === 409) {
        try {
          const fresh = await ManagerOrdersService.getManagerOrderDetail(orderId);
          if (!current()) return false;
          options.onUpdated(fresh); await nextTick();
          error.value = 'Ответственный уже изменён. Показаны текущие данные — выберите сотрудника заново.';
        } catch (refreshError) { if (current()) error.value = `Не удалось обновить ответственного: ${getApiErrorMessage(refreshError)}`; }
      } else error.value = getApiErrorMessage(cause);
      return false;
    } finally { if (current()) { paused.value = false; busy.value = false; } }
  };
  return { busy, paused, error, canAssign, assign };
};
