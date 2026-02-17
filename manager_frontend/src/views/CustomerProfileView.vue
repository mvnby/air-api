<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { ArrowLeft, Building2, Mail, Phone, ReceiptText, UserRound } from 'lucide-vue-next';
import { api } from '../api';
import type { ManagerCatalogCustomerItemResponse } from '../client';

const customer = ref<ManagerCatalogCustomerItemResponse | null>(null);
const loading = ref(false);
const error = ref('');

const customerId = computed(() => {
  const raw = new URLSearchParams(window.location.search).get('customerId');
  if (!raw) return null;
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? value : null;
});

const formatDate = (iso?: string | null) => {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('ru-RU');
};

const loadCustomer = async () => {
  if (!customerId.value) {
    error.value = 'Не передан customerId';
    customer.value = null;
    return;
  }
  loading.value = true;
  error.value = '';
  try {
    customer.value = await api.getManagerCustomerDetail(customerId.value);
  } catch (e) {
    console.error(e);
    error.value = 'Не удалось загрузить карточку клиента';
    customer.value = null;
  } finally {
    loading.value = false;
  }
};

const navigateToCustomers = () => {
  window.history.pushState({}, '', '/manager/customers');
  window.dispatchEvent(new PopStateEvent('popstate'));
};

const openOrders = () => {
  if (!customer.value) return;
  const search = customer.value.inn || customer.value.phone || customer.value.email || customer.value.name || '';
  const path = search
    ? `/manager/orders/kanban?search=${encodeURIComponent(search)}`
    : '/manager/orders/kanban';
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

watch(customerId, () => {
  void loadCustomer();
});

onMounted(() => {
  void loadCustomer();
});
</script>

<template>
  <div class="min-h-screen bg-[var(--mv-bg)] text-slate-100">
    <div class="mx-auto max-w-[1200px] px-4 py-6 md:px-8">
      <div class="mb-4 flex items-center gap-2">
        <button class="btn-mini-outline" type="button" @click="navigateToCustomers">
          <ArrowLeft class="h-4 w-4" />
          К списку клиентов
        </button>
        <button v-if="customer" class="btn-mini" type="button" @click="openOrders">
          Сделки клиента
        </button>
      </div>

      <div v-if="loading" class="rounded-[2rem] border border-slate-700 bg-slate-900/70 p-8 text-sm text-slate-300">
        Загрузка карточки клиента...
      </div>
      <div v-else-if="error" class="rounded-[2rem] border border-red-500/40 bg-red-900/20 p-6 text-sm text-red-200">
        {{ error }}
      </div>
      <div v-else-if="customer" class="space-y-4">
        <header class="rounded-[2rem] border border-slate-700 bg-gradient-to-r from-slate-900 to-slate-800 p-6">
          <p class="text-xs uppercase tracking-[0.2em] text-slate-400">Customer profile</p>
          <h1 class="mt-2 text-2xl font-bold">{{ customer.full_legal_name || customer.name || `Клиент #${customer.id}` }}</h1>
          <p class="mt-1 text-sm text-slate-300">ID: #{{ customer.id }} · {{ customer.type === 'company' ? 'Юр. лицо' : 'Физ. лицо' }}</p>
        </header>

        <section class="grid gap-4 md:grid-cols-2">
          <article class="rounded-[1.5rem] border border-slate-700 bg-slate-900/70 p-5">
            <h2 class="mb-3 text-sm font-semibold uppercase tracking-[0.16em] text-slate-400">Контакты</h2>
            <div class="space-y-2 text-sm">
              <p class="detail"><UserRound class="h-4 w-4" /> <span>{{ customer.name || '—' }}</span></p>
              <p class="detail"><Phone class="h-4 w-4" /> <span>{{ customer.phone || '—' }}</span></p>
              <p class="detail"><Mail class="h-4 w-4" /> <span>{{ customer.email || '—' }}</span></p>
              <p class="detail"><Building2 class="h-4 w-4" /> <span>УНП: {{ customer.inn || '—' }}</span></p>
              <p class="detail"><Building2 class="h-4 w-4" /> <span>КПП: {{ customer.kpp || '—' }}</span></p>
              <p class="detail"><ReceiptText class="h-4 w-4" /> <span>Заказов: {{ customer.order_count }}</span></p>
              <p class="detail"><ReceiptText class="h-4 w-4" /> <span>Создан: {{ formatDate(customer.created_at) }}</span></p>
            </div>
          </article>

          <article class="rounded-[1.5rem] border border-slate-700 bg-slate-900/70 p-5">
            <h2 class="mb-3 text-sm font-semibold uppercase tracking-[0.16em] text-slate-400">Юр. реквизиты</h2>
            <div class="space-y-2 text-sm">
              <p class="detail-value"><span>Полное наименование</span><strong>{{ customer.full_legal_name || '—' }}</strong></p>
              <p class="detail-value"><span>Юр. адрес</span><strong>{{ customer.legal_address || '—' }}</strong></p>
              <p class="detail-value"><span>Факт. адрес</span><strong>{{ customer.actual_address || '—' }}</strong></p>
              <p class="detail-value"><span>Банк</span><strong>{{ customer.bank_name || '—' }}</strong></p>
              <p class="detail-value"><span>BIC</span><strong>{{ customer.bic || '—' }}</strong></p>
              <p class="detail-value"><span>IBAN</span><strong>{{ customer.iban || '—' }}</strong></p>
              <p class="detail-value"><span>Подписант</span><strong>{{ customer.signer_name || '—' }}</strong></p>
              <p class="detail-value"><span>Должность</span><strong>{{ customer.signer_position || '—' }}</strong></p>
              <p class="detail-value"><span>Основание</span><strong>{{ customer.acting_basis || '—' }}</strong></p>
              <p class="detail-value"><span>Последний адрес доставки</span><strong>{{ customer.last_delivery_address || '—' }}</strong></p>
            </div>
          </article>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: rgb(203 213 225);
}

.detail-value {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.detail-value span {
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgb(148 163 184);
}

.detail-value strong {
  color: rgb(241 245 249);
  font-weight: 600;
  word-break: break-word;
}
</style>
