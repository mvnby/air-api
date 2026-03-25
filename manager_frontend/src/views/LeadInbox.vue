<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { api, type LeadsInboxItemResponse } from '../api';
import LeadInboxCard from '../components/leads/LeadInboxCard.vue';
import LeadQualifyModal from '../components/leads/LeadQualifyModal.vue';
import { useBelarusPhoneMask } from '../composables/useBelarusPhoneMask';
import { useB2BLookup } from '../composables/useB2BLookup';

type Scope = 'active' | 'archive';

const scope = ref<Scope>('active');
const items = ref<LeadsInboxItemResponse[]>([]);
const total = ref(0);
const loading = ref(false);
const toast = ref('');

// Qualify / Reject modals
const qualifyTarget = ref<LeadsInboxItemResponse | null>(null);
const rejectTarget = ref<LeadsInboxItemResponse | null>(null);

// Create Lead modal
const showCreateModal = ref(false);
const createSaving = ref(false);
const createForm = ref({
  source: 'manager',
  request_text: '',
  name: '',
  phone: '',
  service_type: '',
  isCompany: false,
  inn: '',
  fullLegalName: '',
});

const { lookupCompany, isEgrLoading } = useB2BLookup();

const createPhoneInputRef = ref<HTMLInputElement | null>(null);
const phoneModelRef = ref('');

const { unmaskedValue: createPhoneUnmasked } = useBelarusPhoneMask(createPhoneInputRef, phoneModelRef);

// Customer Search in Create Modal
const searchTimeout = ref<number | null>(null);
const foundCustomers = ref<any[]>([]);
const existingCustomerId = ref<number | null>(null);

const searchCustomer = async () => {
  if (existingCustomerId.value) return; 

  const query = phoneModelRef.value.replace(/\D/g, '').length >= 3 ? phoneModelRef.value : createForm.value.name;
  
  if (!query || query.length < 3) {
    foundCustomers.value = [];
    return;
  }

  try {
    const res = await api.getManagerCustomers(1, 4, query);
    foundCustomers.value = res.items || [];
  } catch (e) {
    console.error('Customer search failed', e);
    foundCustomers.value = [];
  }
};

const onSearchInput = () => {
  if (existingCustomerId.value) {
     existingCustomerId.value = null;
  }
  if (searchTimeout.value) clearTimeout(searchTimeout.value);
  searchTimeout.value = window.setTimeout(searchCustomer, 400);
};

const selectCustomer = (c: any) => {
  existingCustomerId.value = c.id;
  createForm.value.name = c.name || c.full_legal_name || '';
  phoneModelRef.value = c.phone || c.inn || '';
  foundCustomers.value = [];
};

const clearSelectedCustomer = () => {
  existingCustomerId.value = null;
  createForm.value.name = '';
  phoneModelRef.value = '';
  foundCustomers.value = [];
};

watch(phoneModelRef, (val) => {
  createForm.value.phone = val;
});

watch(() => createForm.value.phone, (val) => {
  if (phoneModelRef.value !== val) {
    phoneModelRef.value = val;
  }
});

const setToast = (msg: string) => {
  toast.value = msg;
  setTimeout(() => { if (toast.value === msg) toast.value = ''; }, 3000);
};

const load = async () => {
  loading.value = true;
  try {
    const res = await api.getLeadsInbox(scope.value);
    items.value = res.items;
    total.value = res.total;
  } catch (e) {
    console.error(e);
    setToast('Не удалось загрузить входящие');
  } finally {
    loading.value = false;
  }
};

onMounted(load);
watch(scope, load);

// ── Create Lead ───────────────────────────────────────────────────────────────
const openCreateModal = () => {
  Object.assign(createForm.value, { 
    source: 'manager', 
    request_text: '', 
    name: '', 
    phone: '', 
    service_type: '',
    isCompany: false,
    inn: '',
    fullLegalName: '',
  });
  phoneModelRef.value = '';
  existingCustomerId.value = null;
  foundCustomers.value = [];
  showCreateModal.value = true;
};

const submitCreateLead = async () => {
    if (!createForm.value.request_text?.trim()) {
        setToast('Заполните поле «Запрос»');
        return;
    }
    createSaving.value = true;
    try {
        await api.createManagerOrder({
            customer_id: existingCustomerId.value || undefined,
            source: createForm.value.source,
            request_text: createForm.value.request_text,
            name: createForm.value.name || undefined,
            phone: createPhoneUnmasked.value || undefined,
            service_type: createForm.value.service_type || undefined,
            customer_type: createForm.value.isCompany ? 'company' : 'individual',
            customer_inn: createForm.value.isCompany ? (createForm.value.inn || undefined) : undefined,
            customer_full_legal_name: createForm.value.isCompany ? (createForm.value.fullLegalName || createForm.value.name || undefined) : undefined,
        });
        showCreateModal.value = false;
        setToast('Лид создан');
        await load();
    } catch (e: any) {
        console.error(e);
        setToast(`Ошибка: ${e?.message ?? 'Не удалось создать лид'}`);
    } finally {
        createSaving.value = false;
    }
};

const onCreateInnBlur = async () => {
    if (!createForm.value.inn || createForm.value.inn.length !== 9) return;
    const data = await lookupCompany(createForm.value.inn);
    if (data) {
        if (!createForm.value.fullLegalName) createForm.value.fullLegalName = data.fullLegalName || '';
        if (!createForm.value.name) createForm.value.name = data.fullLegalName || '';
    }
};

// ── Qualify ───────────────────────────────────────────────────────────────────
const handleQualifySuccess = async (orderId: number) => {
  setToast(`Заявка #${orderId} переведена в Замер`);
  qualifyTarget.value = null;
  await load();
};

// ── No Answer (Недозвон) ──────────────────────────────────────────────────────
const markNoAnswer = async (item: LeadsInboxItemResponse) => {
  try {
    const noAnswerPayload = { 
      status: 'new_lead', 
      no_answer_at: new Date().toISOString() 
    };
    await api.patchManagerOrder(item.id, noAnswerPayload);
    setToast(`Заявка #${item.id} переведена в работу (Недозвон)`);
    await load();
  } catch (e) {
    console.error(e);
    setToast('Ошибка при обновлении статуса');
  }
};

// ── Rejection ─────────────────────────────────────────────────────────────────
const rejectReason = ref('');

const confirmReject = async () => {
  if (!rejectTarget.value) return;
  try {
    const newComment = rejectReason.value
      ? (rejectTarget.value.comment ? `${rejectTarget.value.comment}\n[Отказ: ${rejectReason.value}]` : `[Отказ: ${rejectReason.value}]`)
      : rejectTarget.value.comment;

    await api.patchManagerOrder(rejectTarget.value.id, {
      status: 'closed',
      closing_result: 'lost',
      reject_reason: rejectReason.value || undefined,
      comment: newComment || undefined,
    });
    setToast(`Заявка #${rejectTarget.value.id} перемещена в архив`);
    rejectTarget.value = null;
    rejectReason.value = '';
    await load();
  } catch (e) {
    console.error(e);
    setToast('Ошибка при отклонении');
  }
};

const openRejectModal = (item: LeadsInboxItemResponse) => {
  rejectTarget.value = item;
  rejectReason.value = '';
};

const scopeOptions: { value: Scope; label: string }[] = [
  { value: 'active', label: 'Активные' },
  { value: 'archive', label: 'Архив' },
];
</script>

<template>
  <div class="p-6 bg-slate-50 dark:bg-[#0f172a] min-h-full text-slate-900 dark:text-white transition-colors duration-200">

    <!-- Header -->
    <div class="flex items-center justify-between mb-6 gap-4 flex-wrap">
      <h1 class="text-2xl font-bold flex items-center gap-3">
        <span class="material-icons-round text-teal-600 dark:text-teal-400">move_to_inbox</span>
        Входящие
        <span
          v-if="total > 0 && scope === 'active'"
          class="inline-flex items-center justify-center rounded-full px-2.5 py-0.5 text-sm font-bold bg-red-500 text-white ml-1"
        >{{ total }}</span>
      </h1>

      <div class="flex items-center gap-2">
        <!-- Create Lead button -->
        <button
          class="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold bg-teal-600 text-white hover:bg-teal-700 active:scale-95 transition-all shadow-sm"
          @click="openCreateModal"
        >
          <span class="material-icons-round text-[18px]">add</span>
          Создать лид
        </button>

        <!-- Scope filter -->
        <div class="flex rounded-lg overflow-hidden border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm font-medium shadow-sm">
          <button
            v-for="opt in scopeOptions"
            :key="opt.value"
            class="px-4 py-2 transition-colors"
            :class="scope === opt.value
              ? 'bg-teal-600 text-white'
              : 'text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700'"
            @click="scope = opt.value"
          >
            {{ opt.label }}
          </button>
        </div>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center gap-3 text-slate-500 dark:text-slate-400 py-12 justify-center">
      <span class="material-icons-round animate-spin text-teal-500">refresh</span>
      Загрузка...
    </div>

    <!-- Empty state -->
    <div
      v-else-if="items.length === 0"
      class="text-center py-16 text-slate-400 dark:text-slate-500"
    >
      <span class="material-icons-round text-5xl mb-3 block opacity-30">inbox</span>
      <p class="text-lg font-medium">
        {{ scope === 'active' ? 'Входящих нет — всё обработано!' : 'Архив пуст' }}
      </p>
    </div>

    <!-- Feed -->
    <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      <LeadInboxCard
        v-for="item in items"
        :key="item.id"
        :item="item"
        :is-archive="scope === 'archive'"
        @qualify="qualifyTarget = $event"
        @reject="openRejectModal($event)"
        @no-answer="markNoAnswer($event)"
      />
    </div>

    <!-- Toast -->
    <transition name="slide-up">
      <div
        v-if="toast"
        class="fixed bottom-6 left-1/2 -translate-x-1/2 bg-slate-900 text-white px-5 py-3 rounded-xl shadow-2xl text-sm font-medium z-50"
      >
        {{ toast }}
      </div>
    </transition>

    <!-- ── Qualify Modal ──────────────────────────────── -->
    <LeadQualifyModal
      v-if="qualifyTarget"
      :lead="qualifyTarget"
      @close="qualifyTarget = null"
      @success="handleQualifySuccess"
    />

    <!-- ── Reject Modal ───────────────────────────────── -->
    <div
      v-if="rejectTarget"
      class="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      @click.self="rejectTarget = null"
    >
      <div class="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-sm w-full p-6 space-y-4">
        <h2 class="text-lg font-bold flex items-center gap-2">
          <span class="material-icons-round text-red-500">cancel</span>
          Отказать по заявке #{{ rejectTarget.id }}
        </h2>
        <p class="text-sm text-slate-600 dark:text-slate-300">
          Заявка будет перемещена в архив со статусом <strong>«Отменена»</strong>.
        </p>

        <div>
          <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wide">Причина отказа (опционально)</label>
          <input
            v-model="rejectReason"
            type="text"
            placeholder="Например: Дорого, Нецелевой, Спам"
            class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-red-500"
          />
        </div>

        <div class="flex gap-3 pt-1">
          <button
            class="flex-1 py-2.5 rounded-xl bg-red-600 text-white font-semibold hover:bg-red-700 transition-colors text-sm"
            @click="confirmReject"
          >⛔ Подтвердить</button>
          <button
            class="flex-1 py-2.5 rounded-xl bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 font-semibold hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors text-sm"
            @click="rejectTarget = null"
          >Отмена</button>
        </div>
      </div>
    </div>

    <!-- ── Create Lead Modal ───────────────────────────── -->
    <div
      v-if="showCreateModal"
      class="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      @click.self="showCreateModal = false"
    >
      <div class="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-md w-full p-6 space-y-4">
        <h2 class="text-lg font-bold flex items-center gap-2">
          <span class="material-icons-round text-teal-500">person_add</span>
          Новый лид
        </h2>

        <div class="space-y-3 relative">
          <!-- Selected Customer Banner -->
          <div v-if="existingCustomerId" class="bg-teal-50 dark:bg-teal-900/30 border border-teal-200 dark:border-teal-800 text-teal-800 dark:text-teal-300 px-3 py-2 rounded-xl flex items-center justify-between text-sm col-span-full">
            <div class="flex items-center gap-2">
              <span class="material-icons-round text-teal-500 text-lg">check_circle</span>
              <span>Привязан клиент: <strong>{{ createForm.name || phoneModelRef || 'Без имени' }}</strong></span>
            </div>
            <button @click="clearSelectedCustomer" class="text-teal-600 hover:text-teal-800 dark:text-teal-400 dark:hover:text-teal-200 p-1 rounded-md hover:bg-teal-100 dark:hover:bg-teal-800 transition-colors" title="Отвязать клиента">
              <span class="material-icons-round text-[16px]">close</span>
            </button>
          </div>

          <!-- Client Type Selection -->
          <div class="flex gap-2 p-1 bg-slate-100 dark:bg-slate-800 rounded-xl w-fit mx-auto col-span-full">
            <button 
              class="px-5 py-1.5 rounded-lg text-xs font-semibold transition-all"
              :class="!createForm.isCompany ? 'bg-white dark:bg-slate-700 shadow-sm text-teal-700 dark:text-teal-400' : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'"
              @click="createForm.isCompany = false"
            >
              👤 Физ. лицо
            </button>
            <button 
              class="px-5 py-1.5 rounded-lg text-xs font-semibold transition-all"
              :class="createForm.isCompany ? 'bg-white dark:bg-slate-700 shadow-sm text-teal-700 dark:text-teal-400' : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'"
              @click="createForm.isCompany = true"
            >
              🏢 Юр. лицо
            </button>
          </div>

          <div v-if="createForm.isCompany" class="col-span-full grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="relative">
              <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wide">УНП</label>
              <input
                v-model="createForm.inn"
                @blur="onCreateInnBlur"
                type="text"
                placeholder="9 цифр"
                class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500"
              />
              <div v-if="isEgrLoading" class="absolute right-3 top-7">
                <span class="material-icons-round animate-spin text-teal-500 text-sm">refresh</span>
              </div>
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wide">Юр. Название</label>
              <input
                v-model="createForm.fullLegalName"
                type="text"
                placeholder="Полное название"
                class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500"
              />
            </div>
          </div>

          <div>
            <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wide">Имя / Компания</label>
            <input
              v-model="createForm.name"
              @input="onSearchInput"
              type="text"
              placeholder="Иванов Иван / МастерВоздуха"
              class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500"
            />
          </div>
          <div class="relative">
            <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wide">Телефон</label>
            <input
              ref="createPhoneInputRef"
              v-model="phoneModelRef"
              @input="onSearchInput"
              type="text"
              placeholder="+375 (29) 000-00-00"
              class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500"
            />

            <!-- Autocomplete Dropdown -->
            <div v-if="foundCustomers.length > 0 && !existingCustomerId" class="absolute z-10 w-full left-0 top-[100%] bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-xl shadow-lg mt-1 max-h-48 overflow-y-auto">
              <button
                v-for="c in foundCustomers"
                :key="c.id"
                @click="selectCustomer(c)"
                class="w-full text-left px-4 py-2 hover:bg-slate-50 dark:hover:bg-slate-700 border-b border-slate-100 dark:border-slate-700 last:border-0"
              >
                <div class="text-sm font-semibold text-slate-800 dark:text-white">{{ c.name || c.full_legal_name || 'Без имени' }}</div>
                <div class="text-xs text-slate-500 dark:text-slate-400">{{ c.phone || c.inn || 'Нет данных' }} <span class="text-[10px] ml-1 opacity-50">{{ c.type === 'company' ? 'Юр. лицо' : 'Физ. лицо' }}</span></div>
              </button>
            </div>
          </div>
          <div>
            <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wide">Источник</label>
            <select
              v-model="createForm.source"
              class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-teal-500"
            >
              <option value="manager">Менеджер (звонок/офис)</option>
              <option value="phone">Входящий звонок</option>
              <option value="site">Сайт</option>
              <option value="other">Другое</option>
            </select>
          </div>
          <div>
            <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wide">Суть задачи</label>
            <select
              v-model="createForm.service_type"
              class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-teal-500"
            >
              <option value="">— Не указано —</option>
              <option value="turnkey">📦 Покупка + Монтаж</option>
              <option value="install_only">🔧 Только монтаж</option>
              <option value="pre_install">🧱 Закладка трассы (Ремонт)</option>
              <option value="maintenance">❄️ Сервис / ТО</option>
              <option value="repair">🛠 Ремонт</option>
            </select>
          </div>
          <div>
            <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wide">Запрос <span class="text-red-400">*</span></label>
            <textarea
              v-model="createForm.request_text"
              rows="3"
              placeholder="Нужен монтаж кондиционера в квартиру, Минск..."
              class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500 resize-none"
            />
          </div>
        </div>

        <div class="flex gap-3 pt-1">
          <button
            class="flex-1 py-2.5 rounded-xl font-semibold text-sm transition-all"
            :class="createSaving ? 'bg-teal-400 text-white cursor-not-allowed' : 'bg-teal-600 text-white hover:bg-teal-700'"
            :disabled="createSaving"
            @click="submitCreateLead"
          >
            {{ createSaving ? 'Сохранение...' : '✅ Создать лид' }}
          </button>
          <button
            class="flex-1 py-2.5 rounded-xl bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 font-semibold text-sm hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
            @click="showCreateModal = false"
          >Отмена</button>
        </div>
      </div>
    </div>

  </div>
</template>

<style scoped>
.slide-up-enter-active,
.slide-up-leave-active { transition: all 0.3s ease; }
.slide-up-enter-from,
.slide-up-leave-to { opacity: 0; transform: translate(-50%, 12px); }
</style>
