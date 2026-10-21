import { computed, nextTick, onScopeDispose, ref, watch, type Ref } from 'vue';
import { api } from '../api';
import type {
  FxRateResponse,
  ManagerInstallerResponse,
  ManagerOrderDetailResponse,
  ManagerOrderUpdatePayload,
  PaymentCurrency,
  PaymentResponse,
} from '../client';
import { ManagerSettingsService } from '../client';
import { confirmDialog } from '../services/ui-feedback';
import { fromLocalDateTimeInput, toLocalDateTimeInput } from '../utils/datetime';
import { getApiErrorMessage } from '../utils/api-errors';
import { isB2cCustomer as isB2cCustomerParty } from '../utils/customer-party';
import type { OrderWorkflowType } from '../components/orders/order-workspace';
import { normalizeOrderWorkflowType, ORDER_WORKFLOW_OPTIONS } from '../components/orders/order-workspace';
import { EXECUTION_STATUS_OPTIONS, NEGOTIATION_STATUS_OPTIONS, STATUS_LABELS } from '../components/orders/order-utils';
import { emptyRepairMeta, normalizeRepairMeta, type RepairMeta } from '../components/orders/repair-meta';
import type { ProductLine, ServiceLine } from '../components/orders/order-editor-types';

type ToastHandler = (message: string, type?: 'success' | 'error') => void;
type LinePayload = Pick<ManagerOrderUpdatePayload, 'products' | 'services'>;

type UseOrderDrawerFormOptions = {
  total: Readonly<Ref<number>>;
  productLines: Ref<ProductLine[]>;
  serviceLines: Ref<ServiceLine[]>;
  serviceTariffOptions: Ref<unknown[]>;
  activeServiceSuggestionIndex: Ref<number | null>;
  applyTariffTemplateToLine: (line: ServiceLine, option: any) => void;
  buildLinesPayload: () => LinePayload;
  validateLines: () => string;
  setToast: ToastHandler;
  loadExecutorsOnHydrate?: boolean;
};

export const useOrderDrawerForm = ({
  total,
  productLines,
  serviceLines,
  serviceTariffOptions,
  activeServiceSuggestionIndex,
  applyTariffTemplateToLine,
  buildLinesPayload,
  validateLines,
  setToast,
  loadExecutorsOnHydrate = true,
}: UseOrderDrawerFormOptions) => {
  const status = ref('new_lead');
  const orderTitle = ref('');
  const workflowType = ref<OrderWorkflowType>('sales_installation');
  const repairMeta = ref<RepairMeta>(emptyRepairMeta());
  const managerLabels = ref<string[]>([]);
  const managerLabelDraft = ref('');
  const nextFollowupDate = ref('');
  const assessmentDate = ref('');
  const installationDate = ref('');
  const comment = ref('');
  const isPaid = ref(false);
  const installerId = ref<number | null>(null);
  const customerDeliveryAddress = ref('');
  const customerBranchId = ref<number | null>(null);
  const newBranchAddress = ref('');
  const targetCurrency = ref<PaymentCurrency | null>(null);
  const targetCurrencyAmount = ref<number | null>(null);
  const enableCurrency = ref(false);
  const currentFxRate = ref<FxRateResponse | null>(null);
  const measurementRequired = ref(false);
  const measurerId = ref<number | null>(null);
  const measurementResult = ref('');
  const additionalConditions = ref('');
  const negotiationStatus = ref('awaiting_offer');
  const executionStatus = ref('needs_schedule');
  const executionWithoutPayment = ref(false);
  const executionWithoutPaymentReason = ref('');
  const autoExecutionOnPayment = ref(false);
  const autoCloseOnPayment = ref(false);
  const installersList = ref<ManagerInstallerResponse[]>([]);
  const executorsLoading = ref(false);
  const executorsError = ref('');
  let executorsLoaded = false;
  let executorsRequest = 0;
  let executorsTask: Promise<void> | null = null;
  onScopeDispose(() => { executorsRequest++; });
  const loadExecutors = (retry = false): Promise<void> => {
    if (executorsTask) return executorsTask;
    if (executorsLoaded && !retry) return Promise.resolve();
    const request = ++executorsRequest;
    executorsLoading.value = true;
    executorsError.value = '';
    executorsTask = api.getManagerInstallers(1, 100).then(response => {
      if (request !== executorsRequest) return;
      installersList.value = response.items;
      executorsLoaded = true;
    }).catch(() => {
      if (request === executorsRequest) executorsError.value = 'Не удалось загрузить список исполнителей';
    }).finally(() => {
      if (request === executorsRequest) { executorsLoading.value = false; executorsTask = null; }
    });
    return executorsTask;
  };
  const payments = ref<PaymentResponse[]>([]);
  const localServerErrors = ref<Record<string, string>>({});
  const localFormError = ref('');

  const isRepairWorkflow = computed(() => workflowType.value === 'repair');
  const showProductLinesSection = computed(() => workflowType.value === 'sales_installation');
  const isB2cCustomer = (order: Readonly<Ref<ManagerOrderDetailResponse | null>>) => computed(() => (
    isB2cCustomerParty(order.value?.customer)
  ));
  const executorOptions = computed(() => {
    const selectedIds = new Set<number>();
    if (installerId.value !== null) selectedIds.add(installerId.value);
    if (measurerId.value !== null) selectedIds.add(measurerId.value);
    return installersList.value.filter((installer) => installer.is_active || selectedIds.has(installer.id));
  });

  let currencyHydrationEpoch = 0;
  let currencyHydrationInProgress = false;
  let fxRateRequestEpoch = 0;

  const beginCurrencyHydration = () => {
    currencyHydrationInProgress = true;
    return ++currencyHydrationEpoch;
  };

  const releaseCurrencyWatcherAfterHydration = (epoch: number) => {
    void nextTick(() => {
      if (epoch === currencyHydrationEpoch) currencyHydrationInProgress = false;
    });
  };
  const getActiveFxRate = (currency: PaymentCurrency | null): number | null => {
    if (!currentFxRate.value || !currency) return null;
    if (currency === 'USD') return currentFxRate.value.usd_byn ?? null;
    if (currency === 'EUR') return currentFxRate.value.eur_byn ?? null;
    return null;
  };
  const syncTargetCurrencyAmountFromRate = () => {
    const rate = getActiveFxRate(targetCurrency.value);
    if (!enableCurrency.value || !rate || total.value <= 0) return;
    targetCurrencyAmount.value = Number((total.value / rate).toFixed(2));
  };

  watch(enableCurrency, async (enabled) => {
    if (currencyHydrationInProgress) return;
    const fxRequestEpoch = ++fxRateRequestEpoch;
    if (!enabled) {
      targetCurrency.value = null;
      targetCurrencyAmount.value = null;
    } else if (!targetCurrency.value) {
      targetCurrency.value = 'USD';
      try {
        const rate = await ManagerSettingsService.getFxRate();
        if (fxRequestEpoch !== fxRateRequestEpoch) return;
        currentFxRate.value = rate;
        syncTargetCurrencyAmountFromRate();
      } catch (error) {
        if (fxRequestEpoch !== fxRateRequestEpoch) return;
        console.warn('Failed to fetch FX rate', error);
        enableCurrency.value = false;
        setToast('Не удалось загрузить курс валют', 'error');
      }
    }
  });

  watch(targetCurrency, () => {
    if (currencyHydrationInProgress) return;
    syncTargetCurrencyAmountFromRate();
  });

  const totalPayments = computed(() => {
    const bynPaid = payments.value
      .filter((payment) => payment.currency === 'BYN')
      .reduce((sum, payment) => sum + payment.amount, 0);
    if (!enableCurrency.value || !currentFxRate.value || !targetCurrency.value) return bynPaid;
    const foreignPaid = payments.value
      .filter((payment) => payment.currency === targetCurrency.value)
      .reduce((sum, payment) => sum + payment.amount, 0);
    const rate = getActiveFxRate(targetCurrency.value);
    return rate ? bynPaid + foreignPaid * rate : bynPaid;
  });
  const calculatedTargetCurrencyPayments = computed(() => payments.value.reduce((sum, payment) => {
    if (payment.currency === targetCurrency.value) return sum + payment.amount;
    if (payment.currency === 'BYN' && targetCurrency.value) {
      const rate = getActiveFxRate(targetCurrency.value);
      if (rate) return sum + payment.amount / rate;
    }
    return sum;
  }, 0));
  const targetCurrencyBalanceDue = computed(() => (
    Math.max(0, (targetCurrencyAmount.value || 0) - calculatedTargetCurrencyPayments.value)
  ));
  const balanceDue = computed(() => {
    if (enableCurrency.value && currentFxRate.value && targetCurrency.value) {
      const rate = getActiveFxRate(targetCurrency.value);
      if (rate) return targetCurrencyBalanceDue.value * rate;
    }
    return Math.max(0, total.value - totalPayments.value);
  });

  const buildRepairMetaPayload = () => normalizeRepairMeta(
    repairMeta.value,
    { defaultRepairStatus: isRepairWorkflow.value },
  );

  const hydrateOrder = (order: ManagerOrderDetailResponse) => {
    localServerErrors.value = {};
    localFormError.value = '';
    status.value = order.status;
    orderTitle.value = order.title ?? '';
    workflowType.value = normalizeOrderWorkflowType((order as any).workflow_type);
    repairMeta.value = normalizeRepairMeta(((order as any).repair_meta || {}) as Partial<RepairMeta>, {
      defaultRepairStatus: workflowType.value === 'repair',
    });
    managerLabels.value = [...(order.manager_labels ?? [])];
    managerLabelDraft.value = '';
    nextFollowupDate.value = toLocalDateTimeInput(order.next_followup_date);
    assessmentDate.value = toLocalDateTimeInput(order.measurement_date);
    installationDate.value = toLocalDateTimeInput(order.installation_date);
    comment.value = order.comment ?? '';
    isPaid.value = order.is_paid;
    installerId.value = order.installer_id ?? null;
    customerDeliveryAddress.value = order.delivery_address || '';
    customerBranchId.value = order.customer_branch?.id ?? null;
    measurementRequired.value = order.measurement_required ?? false;
    measurerId.value = order.measurer_id ?? null;
    measurementResult.value = order.measurement_result ?? '';
    additionalConditions.value = order.additional_conditions ?? '';
    negotiationStatus.value = order.negotiation_status || 'awaiting_offer';
    executionStatus.value = order.execution_status || 'needs_schedule';
    executionWithoutPayment.value = Boolean(order.execution_without_payment);
    executionWithoutPaymentReason.value = order.execution_without_payment_reason || '';
    autoExecutionOnPayment.value = Boolean(order.auto_execution_on_payment);
    autoCloseOnPayment.value = Boolean(order.auto_close_on_payment);
    const hydrationEpoch = beginCurrencyHydration();
    const fxRequestEpoch = ++fxRateRequestEpoch;
    targetCurrency.value = order.target_currency || null;
    targetCurrencyAmount.value = order.target_currency_amount ?? null;
    enableCurrency.value = Boolean(order.target_currency);
    releaseCurrencyWatcherAfterHydration(hydrationEpoch);
    payments.value = [...(order.payments || [])];

    if (enableCurrency.value && !currentFxRate.value) {
      void ManagerSettingsService.getFxRate().then((rate) => {
        if (fxRequestEpoch !== fxRateRequestEpoch) return;
        currentFxRate.value = rate;
      }).catch((error) => console.warn('Failed to load fx rate on init', error));
    }
    if (loadExecutorsOnHydrate) void loadExecutors();
  };

  const currentFormSnapshot = (_proposalStatus?: string) => JSON.stringify({
    status: status.value,
    title: orderTitle.value.trim(),
    workflowType: workflowType.value,
    repairMeta: buildRepairMetaPayload(),
    managerLabels: [...managerLabels.value],
    nextFollowupDate: nextFollowupDate.value,
    assessmentDate: assessmentDate.value,
    installationDate: installationDate.value,
    comment: comment.value,
    installerId: installerId.value,
    customerDeliveryAddress: customerDeliveryAddress.value.trim(),
    customerBranchId: customerBranchId.value,
    measurementRequired: measurementRequired.value,
    measurerId: measurerId.value,
    measurementResult: measurementResult.value,
    additionalConditions: additionalConditions.value,
    negotiationStatus: negotiationStatus.value,
    executionStatus: executionStatus.value,
    executionWithoutPayment: executionWithoutPayment.value,
    executionWithoutPaymentReason: executionWithoutPaymentReason.value,
    autoExecutionOnPayment: autoExecutionOnPayment.value,
    autoCloseOnPayment: autoCloseOnPayment.value,
    enableCurrency: enableCurrency.value,
    targetCurrency: targetCurrency.value,
    targetCurrencyAmount: targetCurrencyAmount.value,
  });

  // Browser drafts contain only editable values; never hydrate server-owned fields or run workflow commands.
  const restoreFormDraft = (draft: unknown) => {
    if (!draft || typeof draft !== 'object' || Array.isArray(draft)) return;
    const stored = draft as Record<string, unknown>;
    const hydrationEpoch = beginCurrencyHydration();
    const fxRequestEpoch = ++fxRateRequestEpoch;
    ++workflowChangeRequestId;
    const textFields: Record<string, Ref<string>> = {
      title: orderTitle, comment, customerDeliveryAddress, measurementResult, additionalConditions,
      executionWithoutPaymentReason,
    };
    for (const [key, field] of Object.entries(textFields)) {
      if (typeof stored[key] === 'string') field.value = stored[key];
    }
    const dates = { nextFollowupDate, assessmentDate, installationDate };
    for (const [key, field] of Object.entries(dates)) {
      const value = stored[key];
      if (typeof value === 'string' && (!value || /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/.test(value))) field.value = value;
    }
    const flags = { measurementRequired, executionWithoutPayment, autoExecutionOnPayment, autoCloseOnPayment, enableCurrency };
    for (const [key, field] of Object.entries(flags)) {
      if (typeof stored[key] === 'boolean') field.value = stored[key];
    }
    for (const [key, field] of Object.entries({ installerId, customerBranchId, measurerId })) {
      const value = stored[key];
      if (value === null || (typeof value === 'number' && Number.isSafeInteger(value) && value > 0)) field.value = value;
    }
    if (typeof stored.status === 'string' && Object.prototype.hasOwnProperty.call(STATUS_LABELS, stored.status)) status.value = stored.status;
    if (ORDER_WORKFLOW_OPTIONS.some(option => option.value === stored.workflowType)) workflowType.value = stored.workflowType as OrderWorkflowType;
    if (NEGOTIATION_STATUS_OPTIONS.some(option => option.value === stored.negotiationStatus)) negotiationStatus.value = stored.negotiationStatus as string;
    if (EXECUTION_STATUS_OPTIONS.some(option => option.value === stored.executionStatus)) executionStatus.value = stored.executionStatus as string;
    if (Array.isArray(stored.managerLabels)) managerLabels.value = stored.managerLabels.filter((value): value is string => typeof value === 'string');
    if (stored.targetCurrency === null || stored.targetCurrency === 'USD' || stored.targetCurrency === 'EUR' || stored.targetCurrency === 'BYN') targetCurrency.value = stored.targetCurrency;
    if (stored.targetCurrencyAmount === null || (typeof stored.targetCurrencyAmount === 'number' && Number.isFinite(stored.targetCurrencyAmount) && stored.targetCurrencyAmount >= 0)) targetCurrencyAmount.value = stored.targetCurrencyAmount;
    if (stored.repairMeta && typeof stored.repairMeta === 'object' && !Array.isArray(stored.repairMeta)) {
      const raw = stored.repairMeta as Record<string, unknown>;
      const safe: Record<string, unknown> = {};
      for (const [key, fallback] of Object.entries(emptyRepairMeta())) {
        const value = raw[key];
        if (typeof fallback === 'string' && typeof value === 'string') safe[key] = value;
        else if (typeof fallback === 'boolean' && typeof value === 'boolean') safe[key] = value;
        else if (Array.isArray(fallback) && Array.isArray(value)) safe[key] = value.filter(item => typeof item === 'string');
        else if (fallback && typeof fallback === 'object' && !Array.isArray(fallback) && value && typeof value === 'object' && !Array.isArray(value)) {
          try {
            safe[key] = key === 'defect_act_blocks'
              ? Object.fromEntries(Object.entries(value).filter(([, text]) => typeof text === 'string'))
              : JSON.parse(JSON.stringify(value));
          } catch { /* An invalid optional repair object does not discard the rest of the draft. */ }
        }
      }
      repairMeta.value = normalizeRepairMeta(safe, { defaultRepairStatus: workflowType.value === 'repair' });
    }
    releaseCurrencyWatcherAfterHydration(hydrationEpoch);
    if (enableCurrency.value && !currentFxRate.value) {
      void ManagerSettingsService.getFxRate().then(rate => {
        if (fxRequestEpoch === fxRateRequestEpoch) currentFxRate.value = rate;
      }).catch(() => { /* Keep the fixed draft amount when the rate cannot be read. */ });
    }
  };

  const normalizeManagerLabel = (value: string) => value.trim().replace(/\s+/g, ' ');
  const addManagerLabel = () => {
    const label = normalizeManagerLabel(managerLabelDraft.value);
    if (!label) return;
    const exists = managerLabels.value.some((item) => (
      item.toLocaleLowerCase('ru-RU') === label.toLocaleLowerCase('ru-RU')
    ));
    if (!exists) managerLabels.value.push(label);
    managerLabelDraft.value = '';
  };
  const removeManagerLabel = (label: string) => {
    managerLabels.value = managerLabels.value.filter((item) => item !== label);
  };

  const hasDiagnosticServiceLine = () => serviceLines.value.some((line) => /диагност/i.test(line.title || ''));
  let workflowChangeRequestId = 0;
  const addDefaultRepairDiagnostic = async (requestId: number) => {
    if (hasDiagnosticServiceLine()) return;
    const fallback: ServiceLine = {
      service_id: null,
      title: 'Диагностика кондиционера на объекте',
      quantity: 1,
      price: 0,
      cost: 0,
    };
    try {
      const response = await api.listManagerQuickTariffs('диагностика', 'repair' as any, 5);
      if (requestId !== workflowChangeRequestId || workflowType.value !== 'repair') return;
      const line = { ...fallback };
      const option = (response.items || [])[0];
      if (option) applyTariffTemplateToLine(line, option);
      serviceLines.value = [line, ...serviceLines.value];
      setToast('Добавили базовую диагностику для ремонта');
    } catch (error) {
      if (requestId !== workflowChangeRequestId || workflowType.value !== 'repair') return;
      serviceLines.value = [fallback, ...serviceLines.value];
      setToast(`Не нашли тариф диагностики: ${getApiErrorMessage(error)}`, 'error');
    }
  };

  const setWorkflowType = async (next: OrderWorkflowType) => {
    if (workflowType.value === next) return;
    const hasScenarioData = productLines.value.length > 0
      || serviceLines.value.length > 0
      || Boolean(comment.value.trim())
      || Boolean(installationDate.value)
      || Boolean(measurementResult.value.trim());
    if (hasScenarioData && !await confirmDialog({
      title: 'Сменить сценарий заказа?',
      description: 'В заказе уже есть данные. Скрытые разделы сохранятся и останутся доступны после возврата к сценарию.',
      confirmText: 'Сменить сценарий',
      variant: 'warning',
    })) return;
    const requestId = ++workflowChangeRequestId;
    workflowType.value = next;
    serviceTariffOptions.value = [];
    activeServiceSuggestionIndex.value = null;
    if (next === 'repair') {
      repairMeta.value = normalizeRepairMeta(repairMeta.value, { defaultRepairStatus: true });
      await addDefaultRepairDiagnostic(requestId);
    }
  };

  const buildSavePayload = (
    activeProposalLocked: boolean,
    validate = true,
    validateCurrency = validate,
  ): ManagerOrderUpdatePayload | null => {
    if (validate) {
      localServerErrors.value = {};
      localFormError.value = '';
      const errors: Record<string, string> = {};
      if (!status.value) errors.status = 'Укажите статус';
      if (assessmentDate.value && installationDate.value && installationDate.value < assessmentDate.value) {
        errors.installation_date = 'Дата монтажа не может быть раньше даты замера';
      }
      const lineError = validateLines();
      if (lineError) {
        if (lineError.includes('товар')) errors.products = lineError;
        else errors.services = lineError;
      }
      if (Object.keys(errors).length) {
        localServerErrors.value = errors;
        localFormError.value = 'Исправьте ошибки в форме';
        return null;
      }
      if (status.value === 'execution' && total.value <= 0) {
        localFormError.value = 'Нельзя перевести в монтаж с пустой сметой';
        return null;
      }
      if (status.value === 'execution' && measurementRequired.value && !measurementResult.value.trim()) {
        localFormError.value = 'Требуется замер: заполните результат замера';
        return null;
      }
    }
    if (validateCurrency && enableCurrency.value) {
      if (!targetCurrency.value) {
        localFormError.value = 'Выберите валюту сделки';
        return null;
      }
      if (!getActiveFxRate(targetCurrency.value)) {
        localFormError.value = 'Для выбранной валюты сейчас нет доступного курса';
        return null;
      }
      if (!targetCurrencyAmount.value || targetCurrencyAmount.value <= 0) {
        localFormError.value = 'Укажите зафиксированную сумму в валюте';
        return null;
      }
    } else if (validateCurrency && payments.value.some((payment) => payment.currency !== 'BYN')) {
      localFormError.value = 'Нельзя отключить валютный режим, пока в заказе есть валютные платежи';
      return null;
    }
    const lines = buildLinesPayload();
    return {
      status: status.value,
      title: orderTitle.value,
      workflow_type: workflowType.value as any,
      repair_meta: buildRepairMetaPayload() as any,
      manager_labels: managerLabels.value,
      next_followup_date: fromLocalDateTimeInput(nextFollowupDate.value),
      measurement_date: fromLocalDateTimeInput(assessmentDate.value),
      installation_date: fromLocalDateTimeInput(installationDate.value),
      comment: comment.value,
      is_paid: isPaid.value,
      installer_id: installerId.value,
      customer_branch_id: customerBranchId.value,
      customer_delivery_address: customerDeliveryAddress.value,
      products: activeProposalLocked ? undefined : lines.products,
      services: activeProposalLocked ? undefined : lines.services,
      measurement_required: measurementRequired.value,
      measurer_id: measurerId.value,
      measurement_result: measurementResult.value,
      additional_conditions: additionalConditions.value,
      negotiation_status: status.value === 'negotiation' ? negotiationStatus.value : undefined,
      execution_status: status.value === 'execution' ? executionStatus.value : undefined,
      execution_without_payment: status.value === 'execution' ? executionWithoutPayment.value : false,
      execution_without_payment_reason: status.value === 'execution' && executionWithoutPayment.value
        ? executionWithoutPaymentReason.value
        : null,
      auto_execution_on_payment: autoExecutionOnPayment.value,
      auto_close_on_payment: status.value === 'execution' ? autoCloseOnPayment.value : false,
      target_currency: enableCurrency.value ? targetCurrency.value : null,
      target_currency_amount: enableCurrency.value && targetCurrencyAmount.value
        ? Number(String(targetCurrencyAmount.value).replace(',', '.'))
        : null,
    };
  };

  return {
    addManagerLabel,
    additionalConditions,
    assessmentDate,
    autoCloseOnPayment,
    autoExecutionOnPayment,
    balanceDue,
    buildRepairMetaPayload,
    buildSavePayload,
    calculatedTargetCurrencyPayments,
    comment,
    currentFormSnapshot,
    currentFxRate,
    customerBranchId,
    customerDeliveryAddress,
    enableCurrency,
    executionStatus,
    executionWithoutPayment,
    executionWithoutPaymentReason,
    executorOptions,
    executorsError,
    executorsLoading,
    loadExecutors,
    hydrateOrder,
    restoreFormDraft,
    installationDate,
    installerId,
    isB2cCustomer,
    isPaid,
    isRepairWorkflow,
    localFormError,
    localServerErrors,
    managerLabelDraft,
    managerLabels,
    measurementRequired,
    measurementResult,
    measurerId,
    negotiationStatus,
    newBranchAddress,
    nextFollowupDate,
    orderTitle,
    payments,
    removeManagerLabel,
    repairMeta,
    setWorkflowType,
    showProductLinesSection,
    status,
    targetCurrency,
    targetCurrencyAmount,
    targetCurrencyBalanceDue,
    totalPayments,
    workflowType,
  };
};
