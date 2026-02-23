<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { api, type LeadsInboxItemResponse } from '../api';
import type { LeadCreatePayload } from '../client';
import LeadInboxCard from '../components/leads/LeadInboxCard.vue';

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
const createForm = ref<LeadCreatePayload>({
  source: 'manager',
  request_text: '',
  name: '',
  phone: '',
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
  createForm.value = { source: 'manager', request_text: '', name: '', phone: '' };
  showCreateModal.value = true;
};

const submitCreateLead = async () => {
  if (!createForm.value.request_text?.trim()) {
    setToast('Заполните поле «Запрос»');
    return;
  }
  createSaving.value = true;
  try {
    await api.createManagerLead({
      ...createForm.value,
      name: createForm.value.name || undefined,
      phone: createForm.value.phone || undefined,
    });
    showCreateModal.value = false;
    setToast('Лид создан');
    // Reload inbox — the new lead appears as new_lead in the Orders system
    // (qualification via existing LeadsDashboard flow turns it into an Order)
    await load();
  } catch (e: any) {
    console.error(e);
    setToast(`Ошибка: ${e?.message ?? 'Не удалось создать лид'}`);
  } finally {
    createSaving.value = false;
  }
};

// ── Qualification ─────────────────────────────────────────────────────────────
const navigateToOrders = (orderId: number) => {
  const path = `/manager/orders/kanban?orderId=${orderId}`;
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

const confirmQualify = async () => {
  if (!qualifyTarget.value) return;
  // Move status new_lead → assessment via existing patch endpoint
  try {
    await api.patchManagerOrder(qualifyTarget.value.id, { status: 'assessment' });
    setToast(`Заявка #${qualifyTarget.value.id} переведена в работу`);
    qualifyTarget.value = null;
    await load();
  } catch (e) {
    console.error(e);
    setToast('Ошибка при квалификации');
  }
};

const openInKanban = () => {
  if (!qualifyTarget.value) return;
  navigateToOrders(qualifyTarget.value.id);
  qualifyTarget.value = null;
};

// ── Rejection ─────────────────────────────────────────────────────────────────
const confirmReject = async () => {
  if (!rejectTarget.value) return;
  try {
    await api.patchManagerOrder(rejectTarget.value.id, { status: 'canceled' });
    setToast(`Заявка #${rejectTarget.value.id} перемещена в архив`);
    rejectTarget.value = null;
    await load();
  } catch (e) {
    console.error(e);
    setToast('Ошибка при отклонении');
  }
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
    <div v-else class="flex flex-col gap-3 max-w-2xl mx-auto">
      <LeadInboxCard
        v-for="item in items"
        :key="item.id"
        :item="item"
        @qualify="qualifyTarget = $event"
        @reject="rejectTarget = $event"
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
    <div
      v-if="qualifyTarget"
      class="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      @click.self="qualifyTarget = null"
    >
      <div class="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-md w-full p-6 space-y-4">
        <h2 class="text-lg font-bold flex items-center gap-2">
          <span class="material-icons-round text-teal-500">check_circle</span>
          Квалифицировать заявку #{{ qualifyTarget.id }}
        </h2>
        <p class="text-sm text-slate-600 dark:text-slate-300">
          Статус изменится на <strong>«Замер»</strong>. Для детального оформления сделки откройте её в Канбане.
        </p>
        <div v-if="qualifyTarget.comment" class="bg-slate-50 dark:bg-slate-700/50 p-3 rounded-lg text-sm text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700">
          {{ qualifyTarget.comment }}
        </div>
        <div class="flex gap-3 pt-1">
          <button
            class="flex-1 py-2.5 rounded-xl bg-teal-600 text-white font-semibold hover:bg-teal-700 transition-colors text-sm"
            @click="confirmQualify"
          >✅ Квалифицировать</button>
          <button
            class="flex-1 py-2.5 rounded-xl bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 font-semibold hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors text-sm"
            @click="openInKanban"
          >📋 Открыть в Канбане</button>
        </div>
        <button class="w-full text-center text-xs text-slate-400 hover:text-slate-600 transition-colors" @click="qualifyTarget = null">Отмена</button>
      </div>
    </div>

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
        <div class="flex gap-3 pt-1">
          <button
            class="flex-1 py-2.5 rounded-xl bg-red-600 text-white font-semibold hover:bg-red-700 transition-colors text-sm"
            @click="confirmReject"
          >⛔ Подтвердить отказ</button>
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

        <div class="space-y-3">
          <div>
            <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wide">Имя / Компания</label>
            <input
              v-model="createForm.name"
              type="text"
              placeholder="Иванов Иван"
              class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500"
            />
          </div>
          <div>
            <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wide">Телефон</label>
            <input
              v-model="createForm.phone"
              type="tel"
              placeholder="+375 (29) 000-00-00"
              class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500"
            />
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
