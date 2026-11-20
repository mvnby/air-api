import { ref } from 'vue';
import { ManagerOrderSitesService, type OrderSiteItem } from '../../../client';
import { loadOrderSitePages } from '../../../components/orders/order-site-pages';
import { getApiErrorMessage } from '../../../utils/api-errors';

export function useOrderActSites(orderId: () => number) {
  const sites = ref<OrderSiteItem[]>([]);
  const selectedIds = ref<number[]>([]);
  const loading = ref(false);
  const error = ref('');
  let loadedOrderId: number | null = null;
  let generation = 0;

  function reset() {
    generation++;
    loadedOrderId = null;
    sites.value = [];
    selectedIds.value = [];
    loading.value = false;
    error.value = '';
  }

  async function load() {
    const id = orderId();
    if (loadedOrderId === id) return;
    const request = ++generation;
    loading.value = true;
    error.value = '';
    try {
      const result = await loadOrderSitePages((limit, offset) =>
        ManagerOrderSitesService.managerListOrderSites(id, limit, offset));
      if (request !== generation || id !== orderId()) return;
      sites.value = result;
      selectedIds.value = [];
      loadedOrderId = id;
    } catch (failure) {
      if (request === generation && id === orderId()) error.value = getApiErrorMessage(failure);
    } finally {
      if (request === generation) loading.value = false;
    }
  }

  return { sites, selectedIds, loading, error, reset, load };
}
