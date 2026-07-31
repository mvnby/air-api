import { computed, ref, watch, type Ref } from 'vue';
import { useDebounceFn } from '@vueuse/core';
import { api } from '../api';
import type {
  ManagerOrderDetailResponse,
  ManagerQuickTariffResponse,
  ManagerServiceEstimateResponse,
  OrderProductLineResponse,
  OrderServiceLineResponse,
} from '../client';
import { confirmDialog } from '../services/ui-feedback';
import { getApiErrorMessage } from '../utils/api-errors';
import {
  useServiceDescriptionMode,
  type ServiceDescriptionMode,
} from '../components/orders/service-description-mode';
import type {
  LogisticsComponentKind,
  OrderLogisticsComponent,
  ProductLine,
  ProductLogisticsTemplateComponent,
  ProductOption,
  ServiceLine,
} from '../components/orders/order-editor-types';

type ToastHandler = (message: string, type?: 'success' | 'error') => void;

type UseOrderCommercialEditorOptions = {
  order: Readonly<Ref<ManagerOrderDetailResponse | null>>;
  setToast: ToastHandler;
  persistDraft: () => void;
};

const SUPPLY_STATUS_LABELS: Record<string, string> = {
  draft: 'черновик',
  awaiting_reply: 'ждем ответ',
  reserved: 'бронь',
  ordered: 'заказано',
  ready_for_pickup: 'готово к забору',
  picked_up: 'забрано',
  received: 'получено',
  canceled: 'отменено',
};

const LOGISTICS_COMPONENT_KINDS = new Set(['indoor', 'outdoor', 'accessory', 'other']);

const toIntegerMoney = (value: number | null | undefined): number | null => {
  if (value == null || Number.isNaN(Number(value))) return null;
  return Math.round(Number(value));
};

const normalizeLogisticsKind = (value: unknown): LogisticsComponentKind => {
  const raw = String(value || '').trim();
  return LOGISTICS_COMPONENT_KINDS.has(raw) ? (raw as LogisticsComponentKind) : 'other';
};

const getProductCountryFromSpecs = (specs?: Record<string, any> | null) => {
  if (!specs) return null;
  return String(
    specs.country
    || specs.country_of_origin
    || specs['Страна производства']
    || specs['Страна-производитель']
    || '',
  ).trim() || null;
};

const normalizePositiveInteger = (value: unknown, fallback = 1) => {
  const parsed = Math.trunc(Number(value));
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
};

const normalizePositiveNumber = (value: unknown, fallback = 0) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
};

const normalizeProductLogisticsTemplate = (raw: unknown): ProductLogisticsTemplateComponent[] => {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item): ProductLogisticsTemplateComponent | null => {
      const source = (item || {}) as Record<string, any>;
      const title = String(source.title || '').trim();
      if (!title) return null;
      return {
        title,
        country: String(source.country || '').trim() || null,
        unit: String(source.unit || '').trim() || 'шт.',
        quantity_per_parent: normalizePositiveInteger(source.quantity_per_parent, 1),
        price_weight: normalizePositiveNumber(source.price_weight, 1),
        kind: normalizeLogisticsKind(source.kind),
      };
    })
    .filter((item): item is ProductLogisticsTemplateComponent => Boolean(item));
};

const normalizeOrderLogisticsComponents = (
  components?: OrderLogisticsComponent[] | null,
): OrderLogisticsComponent[] | null => {
  if (!components?.length) return null;
  const normalized = components
    .map((component) => ({
      title: String(component.title || '').trim(),
      country: String(component.country || '').trim() || 'Китай',
      unit: String(component.unit || '').trim() || 'шт.',
      quantity_per_parent: normalizePositiveInteger(component.quantity_per_parent, 1),
      unit_price: normalizePositiveNumber(component.unit_price, 0),
      kind: normalizeLogisticsKind(component.kind),
    }))
    .filter((component) => Boolean(component.title));
  return normalized.length ? normalized : null;
};

const mapProductLineFromResponse = (line: OrderProductLineResponse): ProductLine => ({
  link_id: line.id,
  product_id: line.product_id || 0,
  product_query: line.product_title || '',
  quantity: line.quantity,
  price: line.price,
  cost: line.cost,
  product_country: (line as any).product_country || null,
  product_logistics_components: Array.isArray((line as any).product_logistics_components)
    ? ((line as any).product_logistics_components as ProductLogisticsTemplateComponent[])
    : [],
  logistics_components: Array.isArray((line as any).logistics_components) && (line as any).logistics_components.length
    ? ((line as any).logistics_components as OrderLogisticsComponent[])
    : null,
});

const mapServiceLineFromResponse = (line: OrderServiceLineResponse): ServiceLine => ({
  service_id: line.service_id,
  title: line.service_title,
  quantity: Math.max(1, Number(line.quantity || 1)),
  price: Number(line.price || 0),
  cost: Number(line.cost || 0),
});

export const useOrderCommercialEditor = ({ order, setToast, persistDraft }: UseOrderCommercialEditorOptions) => {
  const productOptions = ref<ProductOption[]>([]);
  const productLookupById = ref<Record<number, ProductOption>>({});
  const activeSuggestionIndex = ref<number | null>(null);
  const productLookupLoading = ref(false);
  const searchInStock = ref(false);
  let productSearchRequestId = 0;

  const productLines = ref<ProductLine[]>([]);
  const supplyRequests = ref<any[]>([]);
  const supplyActionLoadingLineId = ref<number | null>(null);
  const serviceLines = ref<ServiceLine[]>([]);
  const editingServiceLineIndex = ref<number | null>(null);
  const activeServiceSuggestionIndex = ref<number | null>(null);
  const serviceTariffOptions = ref<ManagerQuickTariffResponse[]>([]);
  const serviceTariffLookupLoading = ref(false);
  let serviceTariffSearchRequestId = 0;
  const estimateOptions = ref<ManagerServiceEstimateResponse[]>([]);
  const estimateOptionsLoading = ref(false);
  const estimateImportMode = ref<'detailed' | 'collapsed'>('detailed');
  const selectedEstimateId = ref<number | null>(null);
  const estimateSearchQuery = ref('');
  const importingEstimate = ref(false);
  const showEstimateImport = ref(false);

  const {
    preferredMode: serviceDescriptionMode,
    rememberMode: setDefaultServiceDescriptionMode,
    applyTariffTemplate: applyTariffTemplateToLine,
    replaceLineDescription,
  } = useServiceDescriptionMode();

  const total = computed(() => {
    const products = productLines.value.reduce((sum, line) => sum + line.price * line.quantity, 0);
    const services = serviceLines.value.reduce((sum, line) => sum + line.price * line.quantity, 0);
    return products + services;
  });

  const margin = computed(() => {
    const productCost = productLines.value.reduce((sum, line) => sum + line.cost * line.quantity, 0);
    const serviceCost = serviceLines.value.reduce((sum, line) => sum + line.cost * line.quantity, 0);
    return Math.round(total.value - productCost - serviceCost);
  });

  const rememberProductOption = (option: ProductOption) => {
    productLookupById.value = { ...productLookupById.value, [option.id]: option };
  };

  const rememberProductOptions = (options: ProductOption[]) => {
    if (!options.length) return;
    const merged = { ...productLookupById.value };
    for (const option of options) merged[option.id] = option;
    productLookupById.value = merged;
  };

  const mapSmartSearchItemToOption = (item: any): ProductOption => ({
    id: Number(item.id),
    title: String(item.title ?? ''),
    price: Number(item.price ?? 0),
    cost: Number(item.min_cost_byn ?? 0),
    is_inverter: Boolean(item.is_inverter),
    power_cooling: item.power_cooling == null ? null : Number(item.power_cooling),
    availability_status: String(item.availability_status ?? 'out_of_stock'),
    vitebsk_qty: Number(item.vitebsk_qty ?? 0),
    minsk_qty: Number(item.minsk_qty ?? 0),
    specs: ((item.specs || {}) as Record<string, any>),
  });

  const syncProductLookupFromLines = () => {
    for (const line of productLines.value) {
      if (!line.product_id || productLookupById.value[line.product_id]) continue;
      rememberProductOption({
        id: line.product_id,
        title: line.product_query,
        price: line.price,
        cost: line.cost,
        is_inverter: false,
        power_cooling: null,
        availability_status: 'out_of_stock',
        vitebsk_qty: 0,
        minsk_qty: 0,
      });
    }
  };

  const loadOrderSupplyRequests = async (orderId: number) => {
    try {
      const response = await api.listSupplyRequests({ orderId, limit: 100 });
      supplyRequests.value = response.items || [];
    } catch (error) {
      console.warn('Failed to load supply requests for order', error);
      supplyRequests.value = [];
    }
  };

  const supplyBadgeForLine = (line: ProductLine) => {
    if (!line.link_id) return null;
    for (const request of supplyRequests.value) {
      const requestLine = (request.lines || []).find((item: any) => Number(item.order_product_link_id) === Number(line.link_id));
      if (requestLine) {
        return {
          label: SUPPLY_STATUS_LABELS[requestLine.status] || requestLine.status,
          requestId: request.id,
          status: requestLine.status,
        };
      }
    }
    return null;
  };

  const createSupplyFromProductLine = async (line: ProductLine, intent: 'order' | 'reserve') => {
    if (!order.value?.id) return;
    if (!line.link_id) {
      setToast('Сначала сохраните заказ, чтобы создать поставку по строке.', 'error');
      return;
    }
    supplyActionLoadingLineId.value = line.link_id;
    try {
      await api.createSupplyRequestFromOrderLines({
        order_product_link_ids: [line.link_id],
        intent,
      });
      setToast(intent === 'reserve' ? 'Строка отправлена в бронирование.' : 'Строка добавлена в поставки.');
      await loadOrderSupplyRequests(order.value.id);
    } catch (error) {
      setToast(`Не удалось создать поставку: ${getApiErrorMessage(error)}`, 'error');
    } finally {
      supplyActionLoadingLineId.value = null;
    }
  };

  const debouncedLoadProductOptions = useDebounceFn(async (index: number, query: string, requestId: number) => {
    try {
      productLookupLoading.value = true;
      const response = await api.smartSearchProducts(query, 20);
      if (requestId !== productSearchRequestId || activeSuggestionIndex.value !== index) return;
      let options = Array.isArray(response) ? response.map(mapSmartSearchItemToOption) : [];
      if (searchInStock.value) {
        options = options.filter((option) => (
          option.vitebsk_qty > 0
          || option.minsk_qty > 0
          || option.availability_status === 'check_availability'
        ));
      }
      productOptions.value = options;
      rememberProductOptions(options);
    } catch (error) {
      setToast(`Ошибка поиска товаров: ${getApiErrorMessage(error)}`, 'error');
      if (requestId === productSearchRequestId) productOptions.value = [];
    } finally {
      if (requestId === productSearchRequestId) productLookupLoading.value = false;
    }
  }, 400);

  const onProductChanged = (index: number, applyCatalogPrice = false) => {
    const row = productLines.value[index];
    if (!row) return;
    const selected = productLookupById.value[row.product_id];
    if (!selected) return;
    row.product_query = selected.title;
    if (applyCatalogPrice) row.price = selected.price;
  };

  const onProductQueryInput = (index: number) => {
    const row = productLines.value[index];
    if (!row) return;
    activeSuggestionIndex.value = index;
    const query = row.product_query.trim();
    row.product_id = 0;
    productSearchRequestId += 1;
    if (query.length < 2) {
      productOptions.value = [];
      productLookupLoading.value = false;
      return;
    }
    debouncedLoadProductOptions(index, query, productSearchRequestId);
  };

  watch(searchInStock, () => {
    if (activeSuggestionIndex.value !== null) onProductQueryInput(activeSuggestionIndex.value);
  });

  const onProductInputBlur = (index: number) => {
    window.setTimeout(() => {
      if (activeSuggestionIndex.value === index) activeSuggestionIndex.value = null;
    }, 120);
  };

  const onProductInputFocus = (index: number) => {
    activeSuggestionIndex.value = index;
  };

  const selectProductForLine = (index: number, option: ProductOption) => {
    const row = productLines.value[index];
    if (!row) return;
    row.product_id = option.id;
    row.product_query = option.title;
    row.price = option.price;
    row.product_country = getProductCountryFromSpecs(option.specs);
    row.product_logistics_components = normalizeProductLogisticsTemplate(option.specs?.logistics_components);
    row.logistics_components = null;
    if (option.cost && option.cost > 0) row.cost = option.cost;
    rememberProductOption(option);
    activeSuggestionIndex.value = null;
    productOptions.value = [];
    onProductChanged(index, false);
  };

  const openSelectedProduct = (index: number) => {
    const row = productLines.value[index];
    if (!row?.product_id) return;
    persistDraft();
    const returnTo = `${window.location.pathname}${window.location.search}`;
    const query = new URLSearchParams({
      editProductId: String(row.product_id),
      editProductQuery: row.product_query || '',
      returnTo,
    });
    window.history.pushState({}, '', `/manager/products?${query.toString()}`);
    window.dispatchEvent(new PopStateEvent('popstate'));
  };

  const addProductLine = () => {
    productLines.value.push({
      link_id: null,
      product_id: 0,
      product_query: '',
      quantity: 1,
      price: 0,
      cost: 0,
      product_country: null,
      product_logistics_components: [],
      logistics_components: null,
    });
  };

  const addServiceLine = () => {
    serviceLines.value.push({ title: '', quantity: 1, price: 0, cost: 0, service_id: null });
    editingServiceLineIndex.value = serviceLines.value.length - 1;
  };

  const debouncedLoadServiceTariffOptions = useDebounceFn(async (index: number, query: string, requestId: number) => {
    try {
      serviceTariffLookupLoading.value = true;
      const response = await api.listManagerQuickTariffs(query, null, 10);
      if (requestId !== serviceTariffSearchRequestId || activeServiceSuggestionIndex.value !== index) return;
      serviceTariffOptions.value = response.items || [];
    } catch (error) {
      setToast(`Ошибка поиска тарифов: ${getApiErrorMessage(error)}`, 'error');
      if (requestId === serviceTariffSearchRequestId) serviceTariffOptions.value = [];
    } finally {
      if (requestId === serviceTariffSearchRequestId) serviceTariffLookupLoading.value = false;
    }
  }, 300);

  const onServiceTitleInput = (index: number) => {
    const row = serviceLines.value[index];
    if (!row) return;
    activeServiceSuggestionIndex.value = index;
    row.service_id = null;
    const query = row.title.trim();
    serviceTariffSearchRequestId += 1;
    if (query.length < 2) {
      serviceTariffOptions.value = [];
      serviceTariffLookupLoading.value = false;
      return;
    }
    debouncedLoadServiceTariffOptions(index, query, serviceTariffSearchRequestId);
  };

  const onServiceTitleFocus = (index: number) => {
    activeServiceSuggestionIndex.value = index;
    const row = serviceLines.value[index];
    if (row?.title.trim() && row.title.trim().length >= 2) onServiceTitleInput(index);
  };

  const onServiceTitleBlur = (index: number) => {
    window.setTimeout(() => {
      if (activeServiceSuggestionIndex.value === index) activeServiceSuggestionIndex.value = null;
    }, 120);
  };

  const selectServiceTariffForLine = (index: number, option: ManagerQuickTariffResponse) => {
    const row = serviceLines.value[index];
    if (!row) return;
    applyTariffTemplateToLine(row, option);
    activeServiceSuggestionIndex.value = null;
    serviceTariffOptions.value = [];
  };

  const setServiceLineDescriptionMode = async (index: number, mode: ServiceDescriptionMode) => {
    const row = serviceLines.value[index];
    if (!row) return;
    await replaceLineDescription(row, mode, () => confirmDialog({
      title: 'Заменить изменённое название?',
      description: 'Текст был отредактирован вручную. При замене эти изменения будут потеряны.',
      confirmText: mode === 'full' ? 'Заменить на подробное' : 'Заменить на краткое',
      variant: 'warning',
    }));
  };

  const loadEstimateOptions = async () => {
    estimateOptionsLoading.value = true;
    try {
      const response = await api.listManagerServiceEstimates(1, 10);
      estimateOptions.value = response.items;
      if (!response.items.length) {
        selectedEstimateId.value = null;
        return;
      }
      if (!selectedEstimateId.value || !response.items.some((item) => item.id === selectedEstimateId.value)) {
        selectedEstimateId.value = response.items[0]!.id;
      }
    } catch (error) {
      console.warn('Failed to load service estimates', error);
      estimateOptions.value = [];
      selectedEstimateId.value = null;
    } finally {
      estimateOptionsLoading.value = false;
    }
  };

  const toggleEstimateImport = async () => {
    showEstimateImport.value = !showEstimateImport.value;
    if (showEstimateImport.value && !estimateOptions.value.length && !estimateOptionsLoading.value) {
      await loadEstimateOptions();
    }
  };

  const applyEstimateToServices = async () => {
    const estimateId = Number(selectedEstimateId.value);
    if (!Number.isFinite(estimateId) || estimateId <= 0) {
      setToast('Выберите смету для добавления', 'error');
      return;
    }
    importingEstimate.value = true;
    try {
      const response = await api.getManagerServiceEstimateOrderLines(
        estimateId,
        estimateImportMode.value,
        serviceDescriptionMode.value,
      );
      if (!response.services.length) {
        setToast('В выбранной смете нет строк', 'error');
        return;
      }
      const mappedLines: ServiceLine[] = response.services.map((line) => ({
        service_id: line.service_id ?? null,
        title: line.title || 'Услуга',
        quantity: Math.max(1, Number(line.quantity || 1)),
        price: Number(line.price || 0),
        cost: Number(line.cost || 0),
      }));
      serviceLines.value = [...serviceLines.value, ...mappedLines];
      showEstimateImport.value = false;
      setToast(response.mode === 'collapsed'
        ? `Смета #${response.estimate_id} добавлена одной строкой`
        : `Смета #${response.estimate_id} добавлена: ${mappedLines.length} строк`);
    } catch (error) {
      setToast(`Ошибка импорта сметы: ${getApiErrorMessage(error)}`, 'error');
    } finally {
      importingEstimate.value = false;
    }
  };

  const removeProductLine = async (index: number) => {
    if (!await confirmDialog({ title: 'Удалить товар из заказа?', confirmText: 'Удалить', variant: 'danger' })) return;
    productLines.value.splice(index, 1);
    if (activeSuggestionIndex.value === index) {
      activeSuggestionIndex.value = null;
      productOptions.value = [];
    }
  };

  const removeServiceLine = async (index: number) => {
    if (!await confirmDialog({ title: 'Удалить услугу из заказа?', confirmText: 'Удалить', variant: 'danger' })) return;
    serviceLines.value.splice(index, 1);
    editingServiceLineIndex.value = null;
    if (activeServiceSuggestionIndex.value === index) {
      activeServiceSuggestionIndex.value = null;
      serviceTariffOptions.value = [];
    }
  };

  const buildLinesPayload = (proposalId: number | null) => ({
    products: productLines.value.map((line) => ({
      product_id: line.product_id || 0,
      quantity: Math.trunc(Number(line.quantity) || 0),
      price: Math.round(Number(line.price) || 0),
      cost: (!line.cost && line.cost !== 0) ? null : toIntegerMoney(line.cost),
      logistics_components: normalizeOrderLogisticsComponents(line.logistics_components),
      link_id: line.link_id ?? null,
      proposal_id: proposalId,
    })),
    services: serviceLines.value.map((line) => ({
      service_id: line.service_id ?? null,
      title: line.title,
      quantity: Math.trunc(Number(line.quantity) || 0),
      price: Math.round(Number(line.price) || 0),
      cost: (!line.cost && line.cost !== 0) ? null : toIntegerMoney(line.cost),
      link_id: null,
      proposal_id: proposalId,
    })),
  });

  const validateLines = () => {
    if (productLines.value.some((line) => line.quantity <= 0)) return 'Количество товара должно быть больше 0';
    if (productLines.value.some((line) => line.price < 0)) return 'Цена товара не может быть отрицательной';
    if (productLines.value.some((line) => !line.product_id)) return 'Выберите товар из выпадающего списка';
    if (serviceLines.value.some((line) => line.quantity <= 0)) return 'Количество услуги должно быть больше 0';
    if (serviceLines.value.some((line) => line.price < 0)) return 'Цена услуги не может быть отрицательной';
    if (serviceLines.value.some((line) => !line.title?.trim())) return 'Для услуги укажите название';
    return '';
  };

  const currentLinesSnapshot = (activeProposalId: number | null) => JSON.stringify({
    activeProposalId,
    products: productLines.value.map((line) => ({
      link_id: line.link_id ?? null,
      product_id: Number(line.product_id || 0),
      product_query: String(line.product_query || '').trim(),
      quantity: Number(line.quantity || 0),
      price: Number(line.price || 0),
      cost: Number(line.cost || 0),
      product_country: line.product_country || null,
      product_logistics_components: line.product_logistics_components || [],
      logistics_components: line.logistics_components || null,
    })),
    services: serviceLines.value.map((line) => ({
      service_id: line.service_id ?? null,
      title: String(line.title || '').trim(),
      quantity: Number(line.quantity || 0),
      price: Number(line.price || 0),
      cost: Number(line.cost || 0),
    })),
  });

  const loadLines = (products: OrderProductLineResponse[], services: OrderServiceLineResponse[]) => {
    editingServiceLineIndex.value = null;
    productLines.value = products.map(mapProductLineFromResponse);
    serviceLines.value = services.map(mapServiceLineFromResponse);
  };

  const resetLookupState = () => {
    productLookupById.value = {};
    syncProductLookupFromLines();
    productOptions.value = [];
    activeSuggestionIndex.value = null;
    productLookupLoading.value = false;
    serviceTariffOptions.value = [];
    activeServiceSuggestionIndex.value = null;
    serviceTariffLookupLoading.value = false;
  };

  return {
    activeServiceSuggestionIndex,
    activeSuggestionIndex,
    addProductLine,
    addServiceLine,
    applyEstimateToServices,
    applyTariffTemplateToLine,
    buildLinesPayload,
    createSupplyFromProductLine,
    currentLinesSnapshot,
    editingServiceLineIndex,
    estimateImportMode,
    estimateOptions,
    estimateOptionsLoading,
    estimateSearchQuery,
    importingEstimate,
    loadEstimateOptions,
    loadLines,
    loadOrderSupplyRequests,
    margin,
    onProductInputBlur,
    onProductInputFocus,
    onProductQueryInput,
    onServiceTitleBlur,
    onServiceTitleFocus,
    onServiceTitleInput,
    openSelectedProduct,
    productLines,
    productLookupById,
    productLookupLoading,
    productOptions,
    removeProductLine,
    removeServiceLine,
    resetLookupState,
    searchInStock,
    selectProductForLine,
    selectServiceTariffForLine,
    selectedEstimateId,
    serviceDescriptionMode,
    serviceLines,
    serviceTariffLookupLoading,
    serviceTariffOptions,
    setDefaultServiceDescriptionMode,
    setServiceLineDescriptionMode,
    showEstimateImport,
    supplyActionLoadingLineId,
    supplyBadgeForLine,
    syncProductLookupFromLines,
    toggleEstimateImport,
    total,
    validateLines,
  };
};
