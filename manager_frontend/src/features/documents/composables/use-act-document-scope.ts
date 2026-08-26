import { computed, ref, type ComputedRef } from 'vue';
import {
  ManagerService,
  type ManagerCustomerBranchItemResponse,
  type ManagerOrderDetailResponse,
  type OrderServiceLineResponse,
} from '../../../client';
import { getApiErrorMessage } from '../../../utils/api-errors';

type ActScopeInput = {
  order: () => ManagerOrderDetailResponse;
  activeServiceLines: ComputedRef<OrderServiceLineResponse[]>;
  notify: (message: string, type?: 'success' | 'error') => void;
};

export const useActDocumentScope = (input: ActScopeInput) => {
  const customerBranches = ref<ManagerCustomerBranchItemResponse[]>([]);
  const selectedBranchId = ref<number | null>(input.order().customer_branch?.id ?? null);
  const title = ref(input.order().customer_branch?.name || '');
  const address = ref(input.order().delivery_address || input.order().customer_branch?.delivery_address || '');
  const selectedServiceLineIds = ref<number[]>([]);
  const selectedServiceLineQuantities = ref<Record<number, number>>({});
  const newBranchName = ref('');
  const newBranchAddress = ref('');
  const creatingBranch = ref(false);
  let requestId = 0;

  const selectedServiceLines = computed(() => {
    const selectedIds = new Set(selectedServiceLineIds.value);
    return input.activeServiceLines.value.filter((line) => selectedIds.has(line.id));
  });
  const maxQuantity = (line: OrderServiceLineResponse) => Math.max(0, Math.trunc(Number(line.quantity) || 0));
  const quantity = (lineId: number) => Math.max(0, Math.trunc(Number(selectedServiceLineQuantities.value[lineId]) || 0));
  const syncIds = () => {
    selectedServiceLineIds.value = input.activeServiceLines.value
      .filter((line) => quantity(line.id) > 0)
      .map((line) => line.id);
  };
  const selectAllServices = () => {
    const next: Record<number, number> = {};
    input.activeServiceLines.value.forEach((line) => {
      const value = maxQuantity(line);
      if (value > 0) next[line.id] = value;
    });
    selectedServiceLineQuantities.value = next;
    syncIds();
  };
  const reset = () => {
    const order = input.order();
    selectedBranchId.value = order.customer_branch?.id ?? null;
    title.value = order.customer_branch?.name || '';
    address.value = order.delivery_address || order.customer_branch?.delivery_address || '';
    selectAllServices();
  };
  const loadBranches = async () => {
    const currentRequest = ++requestId;
    const customerId = input.order().customer?.id;
    if (!customerId) {
      customerBranches.value = [];
      reset();
      return;
    }
    try {
      const response = await ManagerService.getManagerCustomerBranches(customerId);
      if (currentRequest !== requestId || input.order().customer?.id !== customerId) return;
      customerBranches.value = response.items || [];
      if (selectedBranchId.value && !customerBranches.value.some((item) => item.id === selectedBranchId.value)) {
        selectedBranchId.value = null;
      }
    } catch (error) {
      console.warn('Failed to load customer branches', error);
      customerBranches.value = [];
    }
  };
  const onBranchChange = () => {
    const branch = customerBranches.value.find((item) => item.id === selectedBranchId.value);
    if (!branch) return;
    title.value = branch.name || '';
    address.value = branch.delivery_address;
  };
  const setQuantity = (line: OrderServiceLineResponse, rawValue: number | string) => {
    const nextQuantity = Math.max(0, Math.min(maxQuantity(line), Math.trunc(Number(rawValue) || 0)));
    const next = { ...selectedServiceLineQuantities.value };
    if (nextQuantity > 0) next[line.id] = nextQuantity;
    else delete next[line.id];
    selectedServiceLineQuantities.value = next;
    syncIds();
  };
  const onCheckboxChange = (lineId: number, event: Event) => {
    const line = input.activeServiceLines.value.find((item) => item.id === lineId);
    if (line) setQuantity(line, (event.target as HTMLInputElement).checked ? maxQuantity(line) : 0);
  };
  const createBranch = async () => {
    const customerId = input.order().customer?.id;
    const deliveryAddress = newBranchAddress.value.trim();
    if (!customerId || !deliveryAddress) {
      input.notify(customerId ? 'Введите адрес объекта' : 'Сначала выберите клиента', 'error');
      return;
    }
    creatingBranch.value = true;
    try {
      const created = await ManagerService.createManagerCustomerBranch(customerId, {
        name: newBranchName.value.trim() || undefined,
        delivery_address: deliveryAddress,
        is_default: customerBranches.value.length === 0,
      });
      customerBranches.value = [created, ...customerBranches.value.filter((item) => item.id !== created.id)];
      selectedBranchId.value = created.id;
      title.value = created.name || '';
      address.value = created.delivery_address;
      newBranchName.value = '';
      newBranchAddress.value = '';
      input.notify('Объект создан');
    } catch (error) {
      input.notify(`Ошибка создания объекта: ${getApiErrorMessage(error)}`, 'error');
    } finally {
      creatingBranch.value = false;
    }
  };

  return {
    address,
    createBranch,
    creatingBranch,
    customerBranches,
    loadBranches,
    maxQuantity,
    newBranchAddress,
    newBranchName,
    onBranchChange,
    onCheckboxChange,
    quantity,
    reset,
    selectAllServices,
    selectedBranchId,
    selectedServiceLineIds,
    selectedServiceLines,
    setQuantity,
    title,
  };
};
