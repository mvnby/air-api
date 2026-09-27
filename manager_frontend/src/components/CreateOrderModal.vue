<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { api } from '../api';
import type { ManagerCustomerBranchItemResponse } from '../client';
import { getApiErrorMessage } from '../utils/api-errors';
import OrderScenarioSelector, { type OrderScenarioOption } from './orders/OrderScenarioSelector.vue';

const props = defineProps<{ customerId: number; customerName: string }>();
const emit = defineEmits<{ (e: 'close'): void; (e: 'created', orderId: number): void }>();

const scenarioOptions = ref<OrderScenarioOption[]>([]);
const scenario = ref<OrderScenarioOption | null>(null);
const branches = ref<ManagerCustomerBranchItemResponse[]>([]);
const branchId = ref<number | null>(null);
const address = ref('');
const requestText = ref('');
const targetDate = ref('');
const contactName = ref('');
const contactPhone = ref('');
const clientRequestId = crypto.randomUUID();
const loading = ref(false);
const loadingOptions = ref(true);
const error = ref('');
const profileUrl = computed(() => `/manager/customers/profile?customerId=${props.customerId}`);

onMounted(async () => {
  try {
    const [scenarios, customerBranches] = await Promise.all([
      api.getManagerOrderScenarios(),
      api.getManagerCustomerBranches(props.customerId),
    ]);
    scenarioOptions.value = scenarios.items;
    branches.value = customerBranches.items || [];
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    loadingOptions.value = false;
  }
});

const selectBranch = () => {
  const branch = branches.value.find((item) => item.id === branchId.value);
  address.value = branch?.delivery_address || '';
};

const handleCreate = async () => {
  if (!scenario.value || loading.value) return;
  loading.value = true;
  error.value = '';
  try {
    const result = await api.createManagerOrder({
      customer_id: props.customerId,
      source: 'manager',
      client_request_id: clientRequestId,
      workflow_type: scenario.value.workflow_type,
      service_type: scenario.value.service_type ?? null,
      customer_branch_id: branchId.value,
      address: address.value.trim() || null,
      request_text: requestText.value.trim(),
      target_date: targetDate.value ? `${targetDate.value}T00:00:00` : null,
      contact_name: contactName.value.trim() || null,
      contact_phone: contactPhone.value.trim() || null,
    });
    emit('created', result.id);
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    loading.value = false;
  }
};
const handleClose = () => { if (!loading.value) emit('close'); };
</script>

<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div class="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" @click.self="handleClose">
        <div class="flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-slate-700/60 bg-[#1e293b] shadow-2xl">
          <div class="flex items-start justify-between gap-3 border-b border-slate-700/50 px-6 py-4">
            <div>
              <h2 class="text-lg font-bold text-white">Новый заказ</h2>
              <p class="mt-1 text-sm text-slate-300">
                Клиент: <a :href="profileUrl" target="_blank" class="text-brand-300 underline">{{ customerName }}</a>
                <a href="/manager/customers" class="ml-2 text-xs text-slate-400 underline">Сменить</a>
              </p>
            </div>
            <button type="button" :disabled="loading" class="text-slate-400 hover:text-white" aria-label="Закрыть" @click="handleClose">
              <span class="material-icons-round">close</span>
            </button>
          </div>
          <div class="space-y-5 overflow-y-auto px-6 py-5">
            <section>
              <h3 class="mb-2 text-sm font-semibold text-white">Что нужно сделать?</h3>
              <p v-if="loadingOptions" class="text-sm text-slate-400">Загружаем сценарии...</p>
              <OrderScenarioSelector v-else v-model="scenario" :options="scenarioOptions" :disabled="loading" />
            </section>
            <section class="space-y-3 border-t border-slate-700/60 pt-4">
              <h3 class="text-sm font-semibold text-white">Объект и уточнения <span class="font-normal text-slate-400">— можно позже</span></h3>
              <label v-if="branches.length" class="block text-xs font-medium text-slate-300">
                Известный объект
                <select v-model="branchId" :disabled="loading" class="mt-1 w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-white" @change="selectBranch">
                  <option :value="null">Уточнить позже / новый адрес</option>
                  <option v-for="branch in branches" :key="branch.id" :value="branch.id">{{ branch.name || `Филиал #${branch.id}` }} — {{ branch.delivery_address }}</option>
                </select>
              </label>
              <label class="block text-xs font-medium text-slate-300">
                Адрес работ
                <input v-model="address" :disabled="loading" type="text" placeholder="Уточнить позже" class="mt-1 w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-white placeholder-slate-500" />
              </label>
              <label class="block text-xs font-medium text-slate-300">
                Краткое описание
                <textarea v-model="requestText" :disabled="loading" rows="2" placeholder="Уточнить позже" class="mt-1 w-full resize-none rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-white placeholder-slate-500" @keydown.meta.enter="handleCreate" @keydown.ctrl.enter="handleCreate" />
              </label>
              <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <label class="block text-xs font-medium text-slate-300">Контактное лицо
                  <input v-model="contactName" :disabled="loading" type="text" placeholder="Уточнить позже" class="mt-1 w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-white placeholder-slate-500" />
                </label>
                <label class="block text-xs font-medium text-slate-300">Телефон контакта
                  <input v-model="contactPhone" :disabled="loading" type="tel" placeholder="Уточнить позже" class="mt-1 w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-white placeholder-slate-500" />
                </label>
              </div>
              <label class="block text-xs font-medium text-slate-300">
                Пожелание по дате <span class="font-normal text-slate-500">— не назначает выезд</span>
                <input v-model="targetDate" :disabled="loading" type="date" class="mt-1 w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-white" />
              </label>
            </section>
            <p class="text-xs text-slate-400">Статус: Переговоры. Недостающие сведения можно уточнить в карточке заказа.</p>
            <p v-if="error" role="alert" class="rounded-lg border border-red-500/40 bg-red-900/20 px-3 py-2 text-sm text-red-300">{{ error }}</p>
          </div>
          <div class="flex justify-end gap-3 border-t border-slate-700/50 px-6 py-4">
            <button type="button" :disabled="loading" class="rounded-lg px-4 py-2 text-sm text-slate-300 hover:bg-slate-700" @click="handleClose">Отмена</button>
            <button type="button" :disabled="loading || !scenario" class="rounded-lg bg-brand-600 px-5 py-2 text-sm font-semibold text-white disabled:opacity-50" @click="handleCreate">
              {{ loading ? 'Создаём...' : 'Создать заказ' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-fade-enter-active, .modal-fade-leave-active { transition: opacity 0.2s ease; }
.modal-fade-enter-from, .modal-fade-leave-to { opacity: 0; }
</style>
