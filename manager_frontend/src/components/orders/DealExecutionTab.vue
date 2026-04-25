<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { ManagerOrdersService, ManagerDocsService, ManagerContractsService } from '../../client';
import type { ManagerCustomerContractItemResponse, ManagerOrderDetailResponse, ManagerOrderDocumentItem } from '../../client';
import { formatMoney } from './order-utils';
import DateTimeField from '../ui/DateTimeField.vue';
import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{
  order: ManagerOrderDetailResponse;
}>();

const emit = defineEmits<{
  refresh: [];
  close: [];
}>();

// Refs and UI state
const toast = ref('');
const toastType = ref<'success' | 'error'>('success');
const setToast = (msg: string, type: 'success' | 'error' = 'success') => {
  toast.value = msg;
  toastType.value = type;
  setTimeout(() => { toast.value = ''; }, 3000);
};

const showAddStage = ref(false);
const newStageName = ref('');
const newStageStart = ref('');
const newStageInstaller = ref<number | null>(null);

const addStage = async () => {
    if (!newStageName.value) return;
    try {
        await ManagerOrdersService.createManagerOrderStage(props.order.id, {
            name: newStageName.value,
            start_time: newStageStart.value ? newStageStart.value + ':00Z' : undefined,
            installer_id: newStageInstaller.value,
        });
        showAddStage.value = false;
        newStageName.value = '';
        newStageStart.value = '';
        newStageInstaller.value = null;
        emit('refresh');
        setToast('Этап добавлен');
    } catch (e: any) {
        setToast(`Ошибка: ${getApiErrorMessage(e)}`, 'error');
    }
};

const updateStageStatus = async (stageId: number, newStatus: string) => {
    try {
        await ManagerOrdersService.updateManagerOrderStage(props.order.id, stageId, {
            status: newStatus
        });
        emit('refresh');
        setToast('Статус обновлен');
    } catch (e: any) {
        setToast(`Ошибка: ${getApiErrorMessage(e)}`, 'error');
    }
};

const deleteStage = async (stageId: number, stageName: string) => {
    if (!window.confirm(`Удалить выезд «${stageName}»?`)) return;
    try {
        await ManagerOrdersService.deleteManagerOrderStage(props.order.id, stageId);
        emit('refresh');
        setToast('Выезд удален');
    } catch (e: any) {
        setToast(`Ошибка: ${getApiErrorMessage(e)}`, 'error');
    }
};

const updateEquipmentStatus = async (newStatus: string) => {
    try {
        await ManagerOrdersService.patchManagerOrder(props.order.id, {
            equipment_status: newStatus
        });
        emit('refresh');
    } catch (e: any) {
        setToast(`Ошибка: ${getApiErrorMessage(e)}`, 'error');
    }
};

const toggleKit = async (val: boolean) => {
    try {
        await ManagerOrdersService.patchManagerOrder(props.order.id, {
            standard_install_kit_issued: val
        });
        emit('refresh');
    } catch (e: any) {
        setToast(`Ошибка: ${getApiErrorMessage(e)}`, 'error');
    }
};

const closeDeal = async () => {
    try {
        await ManagerOrdersService.patchManagerOrder(props.order.id, {
            status: 'closed',
            closing_result: 'won'
        });
        setToast('Сделка успешна закрыта!');
        emit('refresh');
        emit('close');
    } catch (e: any) {
        setToast(`Ошибка: ${getApiErrorMessage(e)}`, 'error');
    }
};

const payments = computed(() => props.order.payments || []);
const newPaymentAmount = ref<number | null>(null);
const newPaymentType = ref<string>('postpayment');

const addPayment = async () => {
  if (!newPaymentAmount.value) return;
  try {
    await ManagerOrdersService.addManagerOrderPayment(props.order.id, {
        amount: newPaymentAmount.value,
        type: newPaymentType.value,
    });
    newPaymentAmount.value = null;
    emit('refresh');
    setToast('Платеж добавлен');
  } catch (error) {
    setToast(`Ошибка: ${getApiErrorMessage(error)}`, 'error');
  }
};

const generateDocument = async (type: string, templateId?: string, documentDate?: string) => {
  try {
    const res = await ManagerOrdersService.generateManagerOrderDocument(props.order.id, type, templateId, documentDate);
    window.open(res.edit_url, '_blank');
    await loadDocuments();
    emit('refresh');
  } catch (error) {
    setToast(`Ошибка генерации: ${getApiErrorMessage(error)}`, 'error');
  }
};

// --- Documents panel ---
const documents = ref<ManagerOrderDocumentItem[]>([]);
const isGeneratingDoc = ref(false);
const processingDocId = ref<number | null>(null);
const docDropdownOpen = ref(false);
const isUploadingDoc = ref(false);
const fileInputRef = ref<HTMLInputElement | null>(null);

const contractTemplates = ref<{id: string; name: string}[]>([]);
const selectedContractTemplateId = ref<string>('');
const documentDate = ref(new Date().toISOString().slice(0, 10));
const customerContracts = ref<ManagerCustomerContractItemResponse[]>([]);
const selectedCustomerContractId = ref<number | null>(props.order.customer_contract_id || null);

const DOCUMENT_TYPES = [
  { type: 'contract', label: 'Договор' },
  { type: 'invoice', label: 'Счет' },
  { type: 'act', label: 'Акт' },
  { type: 'offer', label: 'КП' },
  { type: 'tn2', label: 'ТН-2' },
  { type: 'ttn1', label: 'ТТН-1' },
];

const isCompanyOrder = computed(() => props.order.customer?.type === 'company' || !!props.order.customer?.inn);
const hasOrderContract = computed(() => documents.value.some(d => d.doc_type === 'contract'));
const hasContract = computed(() => (isCompanyOrder.value ? !!selectedCustomerContractId.value : false) || hasOrderContract.value);
const datedDocumentTypes = new Set(['contract', 'act', 'tn2', 'ttn1']);
const getDocumentDateForType = (type: string) => (
  datedDocumentTypes.has(type) && documentDate.value ? `${documentDate.value}T00:00:00` : undefined
);

const loadCustomerContracts = async () => {
  if (!props.order.customer?.id) {
    customerContracts.value = [];
    selectedCustomerContractId.value = null;
    return;
  }
  try {
    const res = await ManagerContractsService.getManagerCustomerContracts(props.order.customer.id);
    customerContracts.value = res.items.filter((contract) => contract.status === 'active');
    selectedCustomerContractId.value = props.order.customer_contract_id || null;
  } catch (error) {
    console.error('Failed to load customer contracts', error);
  }
};

const openCustomerProfileForContract = () => {
  const customerId = props.order.customer?.id;
  if (!customerId) return;
  const currentPath = `${window.location.pathname}${window.location.search}`;
  const target = `/manager/customers/profile?customerId=${customerId}&openContract=1&returnTo=${encodeURIComponent(currentPath)}`;
  window.history.pushState({}, '', target);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

const updateCustomerContract = async () => {
  try {
    await ManagerOrdersService.patchManagerOrder(props.order.id, {
      customer_contract_id: selectedCustomerContractId.value,
    });
    emit('refresh');
  } catch (error) {
    setToast(`Ошибка выбора договора: ${getApiErrorMessage(error)}`, 'error');
  }
};

const loadDocuments = async () => {
  try {
    const res = await ManagerDocsService.getManagerOrderDocuments(props.order.id);
    documents.value = res.items;
  } catch (error) {
    console.error('Failed to load documents', error);
  }
};

const loadContractTemplates = async () => {
  try {
    const res = await ManagerDocsService.getDocTemplates('contract');
    contractTemplates.value = res.items;
    if (res.items.length > 0 && res.items[0]) {
      selectedContractTemplateId.value = res.items[0].id;
    }
  } catch (e) {
    console.warn('Failed to load contract templates', e);
  }
};

const handleDocGenerate = async (type: string) => {
  isGeneratingDoc.value = true;
  docDropdownOpen.value = false;
  try {
    const templateId = (type === 'contract' && selectedContractTemplateId.value)
      ? selectedContractTemplateId.value
      : undefined;
    await generateDocument(type, templateId, getDocumentDateForType(type));
    setToast('Документ создан', 'success');
  } finally {
    isGeneratingDoc.value = false;
  }
};

const downloadDocument = async (doc: ManagerOrderDocumentItem) => {
  processingDocId.value = doc.id;
  try {
    const response = await ManagerDocsService.getManagerDocDownload(doc.id);
    const url = window.URL.createObjectURL(new Blob([response]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `${doc.number}.pdf`);
    document.body.appendChild(link);
    link.click();
    link.remove();
  } catch (error) {
    setToast('Ошибка скачивания', 'error');
  } finally {
    processingDocId.value = null;
  }
};

const deleteDocument = async (docId: number) => {
  if (!confirm('Удалить документ?')) return;
  processingDocId.value = docId;
  try {
    await ManagerDocsService.deleteManagerDoc(docId);
    await loadDocuments();
    setToast('Документ удален', 'success');
  } catch (error) {
    setToast('Ошибка удаления', 'error');
  } finally {
    processingDocId.value = null;
  }
};

const triggerFileUpload = () => {
  fileInputRef.value?.click();
};

const handleFileUpload = async (event: Event) => {
  const target = event.target as HTMLInputElement;
  if (!target.files || !target.files.length) return;
  const file = target.files[0] as File;
  if (!file) return;

  isUploadingDoc.value = true;
  try {
    await ManagerDocsService.uploadManagerOrderDocument(props.order.id, { file });
    await loadDocuments();
    setToast('Документ загружен', 'success');
  } catch (error) {
    setToast(`Ошибка загрузки: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    isUploadingDoc.value = false;
    if (fileInputRef.value) fileInputRef.value.value = '';
  }
};

// Load documents and templates on mount
watch(() => props.order.id, () => {
  loadDocuments();
  loadContractTemplates();
  loadCustomerContracts();
  selectedCustomerContractId.value = props.order.customer_contract_id || null;
}, { immediate: true });
</script>

<template>
<div class="space-y-6">
  <Transition name="fade">
    <div v-if="toast" class="fixed top-6 right-6 z-[100] text-white px-6 py-3 rounded-xl shadow-2xl font-medium" :class="toastType === 'success' ? 'bg-teal-600' : 'bg-red-500'">
      {{ toast }}
    </div>
  </Transition>

  <div v-if="order.is_on_hold" class="rounded-xl border border-amber-300 bg-amber-50 p-4 mb-4 flex items-center justify-between">
    <div>
        <h4 class="text-amber-800 font-bold mb-1">Сделка на паузе</h4>
        <p class="text-sm text-amber-700">{{ order.on_hold_reason || 'Ожидает действий клиента или менеджера' }}</p>
    </div>
  </div>

  <!-- ZONE 1: Timeline -->
  <section class="rounded-2xl bg-white border border-slate-200 p-5 shadow-sm">
    <div class="flex items-center justify-between mb-4 border-b border-slate-100 pb-3">
        <h3 class="text-lg font-bold text-slate-800 font-['Space_Grotesk']">Хронология выездов</h3>
        <button v-if="!showAddStage" class="btn-mini" @click="showAddStage = true">+ Добавить выезд</button>
    </div>

    <!-- Timeline List -->
    <div class="space-y-4 relative before:absolute before:inset-0 before:ml-5 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-slate-300 before:to-transparent">
        <div v-for="stage in order.work_stages" :key="stage.id" class="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
            <div class="flex items-center justify-center w-10 h-10 rounded-full border border-white shrink-0 shadow z-10" :class="stage.status === 'canceled' ? 'bg-slate-400' : 'bg-teal-500'" >
                <span class="material-icons-round text-[20px] text-white">{{ stage.status === 'completed' ? 'check' : (stage.status === 'canceled' ? 'close' : (stage.status === 'in_progress' ? 'build' : 'schedule')) }}</span>
            </div>
            
            <div class="w-[calc(100%-4rem)] md:w-[calc(50%-2.5rem)] p-4 rounded-xl border border-slate-200 bg-slate-50 shadow text-sm" :class="{ 'opacity-50': stage.status === 'canceled' }">
                <div class="flex items-center justify-between mb-2">
                    <span class="font-bold text-slate-800">{{ stage.name }}</span>
                    <div class="flex items-center gap-1">
                        <select :value="stage.status" @change="updateStageStatus(stage.id, ($event.target as HTMLSelectElement).value)" class="text-xs bg-white border border-slate-300 rounded px-1 py-0.5 text-slate-700">
                            <option value="planned">Планируется</option>
                            <option value="in_progress">В работе</option>
                            <option value="completed">Выполнено</option>
                            <option value="canceled">Отменено</option>
                        </select>
                        <button @click="deleteStage(stage.id, stage.name)" class="text-slate-400 hover:text-red-500 transition-colors p-0.5" title="Удалить выезд">
                            <span class="material-icons-round text-[16px]">delete_outline</span>
                        </button>
                    </div>
                </div>
                <div class="text-slate-500 text-xs mt-1">
                    {{ stage.start_time ? new Date(stage.start_time).toLocaleString() : 'План: не задан' }}
                </div>
            </div>
        </div>
        
        <div v-if="!order.work_stages?.length && !showAddStage" class="text-center py-6 text-slate-500 italic">
            Нет запланированных выездов. Начните планирование.
        </div>
    </div>

    <!-- Add Form -->
    <div v-if="showAddStage" class="mt-4 p-4 border border-teal-200 bg-teal-50/30 rounded-xl">
        <h4 class="font-bold text-teal-800 mb-3 text-sm">Новый выезд</h4>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
            <label class="field-label !mb-0 text-xs">Название (Этап)
                <select v-model="newStageName" class="field-input mt-1">
                    <option value="" disabled>Выберите из пресетов...</option>
                    <option value="Монтаж 'под ключ'">Монтаж 'под ключ'</option>
                    <option value="Закладка трассы (Черновой)">Закладка трассы (Черновой)</option>
                    <option value="Навеска блоков (Чистовой)">Навеска блоков (Чистовой)</option>
                    <option value="Доп. выезд">Доп. выезд</option>
                </select>
            </label>
            <DateTimeField v-model="newStageStart" label="Дата и время" />
        </div>
        <div class="flex items-center gap-2 justify-end">
            <button class="btn-mini-outline" @click="showAddStage = false">Отмена</button>
            <button class="btn-mini" :disabled="!newStageName" @click="addStage">Сохранить</button>
        </div>
    </div>
  </section>

  <!-- ZONE 2: Picking List -->
  <section class="rounded-2xl bg-white border border-slate-200 p-5 shadow-sm">
      <div class="flex flex-col md:flex-row items-start md:items-center justify-between mb-4 border-b border-slate-100 pb-3">
          <h3 class="text-lg font-bold text-slate-800 font-['Space_Grotesk']">Склад и комплектация</h3>
          
          <div class="flex flex-wrap items-center gap-2 border border-slate-300 bg-slate-50 rounded-lg p-1 mt-3 md:mt-0 w-full md:w-auto">
              <button class="px-3 py-1 flex-1 md:flex-none justify-center rounded text-xs font-medium transition-colors" :class="order.equipment_status === 'pending' ? 'bg-red-500 text-white shadow' : 'text-slate-600 hover:bg-slate-200'" @click="updateEquipmentStatus('pending')">🔴 Не собрано</button>
              <button class="px-3 py-1 flex-1 md:flex-none justify-center rounded text-xs font-medium transition-colors" :class="order.equipment_status === 'reserved' ? 'bg-amber-500 text-white shadow' : 'text-slate-600 hover:bg-slate-200'" @click="updateEquipmentStatus('reserved')">🟡 Забронировано</button>
              <button class="px-3 py-1 flex-1 md:flex-none justify-center rounded text-xs font-medium transition-colors" :class="order.equipment_status === 'issued' ? 'bg-teal-500 text-white shadow' : 'text-slate-600 hover:bg-slate-200'" @click="updateEquipmentStatus('issued')">🟢 Выдано бригаде</button>
          </div>
      </div>

      <div class="bg-slate-50 rounded-xl p-4 border border-slate-200 mb-4">
          <ul class="space-y-2 text-sm text-slate-700">
              <li v-for="link in order.product_lines" :key="link.id" class="flex justify-between items-center bg-white p-2 rounded shadow-sm border border-slate-100">
                  <span class="font-medium flex-1">{{ link.product_title }}</span>
                  <span class="bg-slate-100 px-2 py-0.5 rounded font-bold text-slate-600">{{ link.quantity }} шт.</span>
              </li>
              <li v-if="!order.product_lines?.length" class="text-slate-400 italic py-2">Нет оборудования в смете</li>
          </ul>
      </div>

      <label class="flex items-center gap-2 cursor-pointer bg-slate-50 p-3 rounded-lg border border-slate-200 hover:bg-slate-100 transition-colors">
          <input type="checkbox" :checked="order.standard_install_kit_issued" @change="toggleKit(($event.target as HTMLInputElement).checked)" class="w-5 h-5 rounded border-slate-300 text-teal-600 focus:ring-teal-600" />
          <span class="font-medium text-slate-800 text-sm">Выдать стандартный монтажный комплект (Кронштейны, труба и т.д.)</span>
      </label>
  </section>

  <!-- ZONE 3: Finance -->
  <section class="rounded-2xl bg-white border border-slate-200 shadow-sm overflow-hidden flex flex-col md:flex-row">
      <div class="flex-1 p-5 border-b md:border-b-0 md:border-r border-slate-200 bg-slate-50">
          <h3 class="text-lg font-bold text-slate-800 font-['Space_Grotesk'] mb-4">Финансы</h3>
          <div class="mb-4 text-center border border-slate-200 rounded-xl py-6 bg-white shadow-inner">
              <p class="text-sm font-medium text-slate-500 uppercase tracking-wide">Остаток к оплате</p>
              <p class="text-4xl font-black mt-2 tracking-tight" :class="(order.balance_due || 0) > 0 ? 'text-red-500' : 'text-teal-600'">
                  {{ formatMoney(order.balance_due || 0) }}
              </p>
          </div>
          
          <div class="flex items-end gap-2 bg-white p-3 rounded-xl border border-slate-200 shadow-sm">
              <label class="flex-1 field-label !mb-0 text-xs">Внести сумму
                  <input v-model.number="newPaymentAmount" type="number" min="0" class="field-input mt-1 shadow-sm" placeholder="0.00" />
              </label>
              <button class="btn-mini h-[38px] w-[100px]" :disabled="!newPaymentAmount" @click="addPayment">Внести</button>
          </div>

          <div class="mt-4 space-y-2 max-h-32 overflow-y-auto pr-1">
              <div v-for="p in payments" :key="p.id" class="flex justify-between items-center text-xs py-2 px-3 rounded-lg bg-white border border-slate-100 shadow-sm">
                  <span class="text-slate-500">{{ new Date(p.date).toLocaleDateString() }}</span>
                  <span class="font-bold text-slate-800">{{ formatMoney(p.amount) }}</span>
                  <span class="text-slate-400 w-16 text-right">{{ p.type === 'prepayment' ? 'Аванс' : 'Доплата' }}</span>
              </div>
          </div>
      </div>

      <div class="flex-1 p-5 flex flex-col bg-white space-y-4">
          <!-- Full Documents Panel -->
          <div class="mb-2 flex items-center justify-between">
            <h4 class="text-md font-semibold text-slate-800">Documents (B2B / Contracts)</h4>
            <div class="relative flex items-center gap-2">
              <button
                class="flex items-center gap-1 rounded-xl bg-[#007f80] px-3 py-1.5 text-sm font-medium text-white shadow hover:bg-teal-600 focus:outline-none focus:ring-2 focus:ring-teal-500/50 disabled:opacity-50"
                :disabled="isGeneratingDoc || !!processingDocId || isUploadingDoc"
                @click="docDropdownOpen = !docDropdownOpen"
              >
                <span class="material-icons-round text-[18px]">add_circle</span> Create
              </button>

              <input type="file" ref="fileInputRef" class="hidden" accept=".pdf" @change="handleFileUpload" />
              <button
                class="flex items-center gap-1 rounded-xl bg-slate-700 px-3 py-1.5 text-sm font-medium text-white shadow hover:bg-slate-600 focus:outline-none focus:ring-2 focus:ring-slate-500/50 disabled:opacity-50"
                title="Upload PDF"
                :disabled="isUploadingDoc || !!processingDocId || isGeneratingDoc"
                @click="triggerFileUpload"
              >
                <span v-if="isUploadingDoc" class="material-icons-round animate-spin text-[18px]">loop</span>
                <span v-else class="material-icons-round text-[18px]">upload_file</span>
                Upload
              </button>

              <div
                v-if="docDropdownOpen"
                class="absolute right-[100px] top-full z-10 mt-2 w-56 rounded-xl border border-slate-200 bg-white p-1 text-slate-800 shadow-xl dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
              >
                <!-- Contract template selector -->
                <div v-if="contractTemplates.length > 1" class="border-b border-slate-200 px-3 py-2 dark:border-slate-700">
                  <label class="mb-1 block text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Шаблон договора</label>
                  <select
                    v-model="selectedContractTemplateId"
                    class="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200"
                    style="border-radius: 12px"
                  >
                    <option v-for="t in contractTemplates" :key="t.id" :value="t.id">{{ t.name }}</option>
                  </select>
                </div>
                <div class="border-b border-slate-200 px-3 py-2 dark:border-slate-700">
                  <label class="mb-1 block text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Дата документа</label>
                  <input
                    v-model="documentDate"
                    type="date"
                    class="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200"
                    style="border-radius: 12px"
                  />
                </div>

                <button
                  v-for="dtype in DOCUMENT_TYPES"
                  :key="dtype.type"
                  class="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-100 disabled:text-slate-400 disabled:opacity-70 disabled:hover:bg-transparent dark:text-slate-200 dark:hover:bg-slate-700 dark:disabled:text-slate-500"
                  :disabled="(dtype.type === 'act' || dtype.type === 'ttn1' || dtype.type === 'tn2') && !hasContract"
                  :title="(dtype.type === 'act' || dtype.type === 'ttn1' || dtype.type === 'tn2') && !hasContract ? 'Сначала создайте договор' : ''"
                  @click="handleDocGenerate(dtype.type)"
                >
                  {{ dtype.label }}
                  <span v-if="(dtype.type === 'act' || dtype.type === 'ttn1' || dtype.type === 'tn2') && !hasContract" class="material-icons-round text-[16px] text-amber-500">lock</span>
                </button>
              </div>
            </div>
          </div>

          <div v-if="isCompanyOrder" class="mb-3 rounded-xl border border-slate-200 bg-white/80 p-3 shadow-sm dark:border-slate-700/50 dark:bg-slate-900/40 dark:shadow-none">
            <label class="mb-1 block text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Открытый договор клиента</label>
            <select
              v-model="selectedCustomerContractId"
              class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
              @change="updateCustomerContract"
            >
              <option :value="null">Выберите договор</option>
              <option v-for="contract in customerContracts" :key="contract.id" :value="contract.id">
                {{ contract.number }} · до {{ new Date(contract.valid_until).toLocaleDateString('ru-RU') }}
              </option>
            </select>
            <div
              v-if="customerContracts.length === 0"
              class="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed border-slate-300 bg-slate-50 p-3 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-800/50 dark:text-slate-300"
            >
              <span>У клиента нет открытых договоров.</span>
              <button
                type="button"
                class="rounded-lg bg-teal-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-teal-700 focus:outline-none focus:ring-2 focus:ring-teal-500/50"
                @click="openCustomerProfileForContract"
              >
                Создать открытый договор
              </button>
            </div>
            <p v-else-if="!selectedCustomerContractId && !hasOrderContract" class="mt-2 text-xs text-amber-600 dark:text-amber-400">Для актов и накладных нужен открытый договор или разовый договор заказа.</p>
          </div>

          <div v-if="documents.length" class="space-y-3">
            <div v-for="doc in documents" :key="doc.id" class="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-3 text-slate-700 shadow-sm dark:border-slate-700/50 dark:bg-[#1e293b] dark:text-slate-300 dark:shadow-none">
              <div class="flex items-center gap-3">
                <div class="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-teal-600 dark:bg-slate-800 dark:text-teal-400">
                  <span class="material-icons-round text-xl">description</span>
                </div>
                <div>
                  <p class="text-sm font-medium text-slate-900 dark:text-white">{{ doc.number || doc.doc_type }}</p>
                  <p class="text-xs text-slate-500 dark:text-slate-400">{{ new Date(doc.date).toLocaleDateString() }} · <span class="uppercase">{{ doc.doc_type }}</span></p>
                </div>
              </div>
              <div class="flex items-center gap-2">
                <a :href="doc.edit_url" target="_blank" class="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-white" title="Редактировать">
                  <span class="material-icons-round text-[18px]">edit</span>
                </a>
                <button class="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-900 disabled:opacity-50 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-white" :disabled="processingDocId === doc.id" @click="downloadDocument(doc)" title="Скачать PDF">
                  <span class="material-icons-round text-[18px]">download</span>
                </button>
                <button class="flex h-8 w-8 items-center justify-center rounded-lg text-red-400 hover:bg-red-500/10 hover:text-red-300 disabled:opacity-50" :disabled="processingDocId === doc.id" @click="deleteDocument(doc.id)" title="Удалить">
                  <span class="material-icons-round text-[18px]">delete</span>
                </button>
              </div>
            </div>
          </div>
          <div v-else class="rounded-xl border border-dashed border-slate-300 py-3 text-center text-sm italic text-slate-500 dark:border-slate-700">
            Нет сформированных документов
          </div>
          
          <hr class="w-full border-slate-100 my-2" />
          
          <button 
                class="w-full py-4 rounded-xl text-lg font-bold shadow-lg flex items-center justify-center gap-2 transition-transform active:scale-95" 
                :class="(order.balance_due || 0) > 0 ? 'bg-slate-300 text-slate-500 cursor-not-allowed' : 'bg-teal-500 text-white hover:bg-teal-600'"
                :disabled="(order.balance_due || 0) > 0"
                @click="closeDeal"
                :title="(order.balance_due || 0) > 0 ? 'Нельзя закрыть при наличии долга' : 'Завершить сделку'"
            >
              <span class="material-icons-round text-[24px]">task_alt</span> Завершить сделку
          </button>
          <p v-if="(order.balance_due || 0) > 0" class="text-xs text-red-400 font-medium text-center">Оплатите остаток для закрытия сделки</p>
      </div>
  </section>
</div>
</template>
