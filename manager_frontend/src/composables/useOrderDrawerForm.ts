import { computed, ref, watch, type Ref } from 'vue';
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
import type { OrderWorkflowType } from '../components/orders/order-workspace';
import { normalizeOrderWorkflowType } from '../components/orders/order-workspace';
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
  const payments = ref<PaymentResponse[]>([]);
  const localServerErrors = ref<Record<string, string>>({});
  const localFormError = ref('');

  const isRepairWorkflow = computed(() => workflowType.value === 'repair');
  const showProductLinesSection = computed(() => workflowType.value === 'sales_installation');
  const isB2cCustomer = (order: Readonly<Ref<ManagerOrderDetailResponse | null>>) => computed(() => (
    order.value?.customer ? order.value.customer.type !== 'company' : true
  ));
  const executorOptions = computed(() => {
    const selectedIds = new Set<number>();
    if (installerId.value !== null) selectedIds.add(installerId.value);
    if (measurerId.value !== null) selectedIds.add(measurerId.value);
    return installersList.value.filter((installer) => installer.is_active || selectedIds.has(installer.id));
  });

  const hasManualEurRate = computed(() => Boolean(currentFxRate.value?.eur_byn));
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
    if (!enabled) {
      targetCurrency.value = null;
      targetCurrencyAmount.value = null;
    } else if (!targetCurrency.value) {
      targetCurrency.value = 'USD';
      try {
        currentFxRate.value = await ManagerSettingsService.getFxRate();
        syncTargetCurrencyAmountFromRate();
      } catch (error) {
        console.warn('Failed to fetch FX rate', error);
        enableCurrency.value = false;
        setToast('Не удалось загрузить курс валют', 'error');
      }
    }
  });

  watch(targetCurrency, (currency) => {
    if (currency === 'EUR' && !hasManualEurRate.value) {
      targetCurrency.value = 'USD';
      return;
    }
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
    targetCurrency.value = order.target_currency || null;
    targetCurrencyAmount.value = order.target_currency_amount || null;
    enableCurrency.value = Boolean(order.target_currency);
    payments.value = [...(order.payments || [])];

    if (enableCurrency.value && !currentFxRate.value) {
      void ManagerSettingsService.getFxRate().then((rate) => {
        currentFxRate.value = rate;
        if (targetCurrency.value === 'EUR' && !rate.eur_byn) targetCurrency.value = 'USD';
      }).catch((error) => console.warn('Failed to load fx rate on init', error));
    }
    if (!installersList.value.length) {
      void api.getManagerInstallers(1, 100).then((response) => {
        installersList.value = response.items;
      }).catch((error) => console.error('Failed to load installers', error));
    }
  };

  const currentFormSnapshot = (proposalStatus: string) => JSON.stringify({
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
    proposalStatus,
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

  const buildSavePayload = (activeProposalLocked: boolean): ManagerOrderUpdatePayload | null => {
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
    if (enableCurrency.value) {
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
    } else if (payments.value.some((payment) => payment.currency !== 'BYN')) {
      localFormError.value = 'Нельзя отключить валютный режим, пока в заказе есть валютные платежи';
      return null;
    }
    repairMeta.value = buildRepairMetaPayload();
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
    hydrateOrder,
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
