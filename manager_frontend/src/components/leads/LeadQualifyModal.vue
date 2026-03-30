<script setup lang="ts">
import { ref, watch } from 'vue';
import { api } from '../../api';
import type { LeadsInboxItemResponse } from '../../api';
import type { ManagerOrderUpdatePayload } from '../../client';
import { useBelarusPhoneMask } from '../../composables/useBelarusPhoneMask';
import { useB2BLookup } from '../../composables/useB2BLookup';

const props = defineProps<{
  lead: LeadsInboxItemResponse;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'success', orderId: number): void;
}>();

// Form State
const isLoading = ref(false);
const customerType = ref<'individual' | 'company'>(props.lead.customer_type as any || 'individual');
const customerName = ref(props.lead.customer_name || '');
// @ts-ignore (phone exists on the original response dynamically, we handle it if present)
const customerPhone = ref((props.lead as any).customer_phone || (props.lead as any).phone || '');
const phoneInputRef = ref<HTMLInputElement | null>(null);
const { unmaskedValue: unmaskedPhone } = useBelarusPhoneMask(phoneInputRef, customerPhone, { lazy: false });
const customerCity = ref('Витебск');
const customerAddress = ref('');
const companyName = ref(props.lead.customer_name || '');
const companyInn = ref(props.lead.customer_inn || '');
const companyFullLegalName = ref(props.lead.customer_full_legal_name || '');
const companyLegalAddress = ref('');
const companyIban = ref('');
const companyBic = ref('');
const companyBankName = ref('');

const objectType = ref('apartment');
const serviceType = ref('turnkey');
const equipmentClass = ref('');
const marketingSource = ref('');
const managerComment = ref(props.lead.comment || '');
const existingCustomerId = ref<number | null>(null);

const { lookupCompany, lookupBank, isEgrLoading, isBankLoading } = useB2BLookup();

// Customer Search
const searchTimeout = ref<number | null>(null);
const searchStatus = ref<'idle' | 'searching' | 'found' | 'not_found'>('idle');
const foundCustomerName = ref('');

const searchCustomer = async () => {
  const query = customerType.value === 'company' 
    ? companyInn.value 
    : (unmaskedPhone.value || customerPhone.value);
  if (!query || query.length < 5) {
    searchStatus.value = 'idle';
    existingCustomerId.value = null;
    return;
  }

  try {
    searchStatus.value = 'searching';
    const res = await api.getManagerCustomers(1, 1, query);
    if (res.items && res.items.length > 0) {
      const match = res.items[0];
      if (match) {
        existingCustomerId.value = match.id;
        foundCustomerName.value = match.name || match.full_legal_name || 'Неизвестно';
        searchStatus.value = 'found';
      } else {
        existingCustomerId.value = null;
        searchStatus.value = 'not_found';
      }
    } else {
      existingCustomerId.value = null;
      searchStatus.value = 'not_found';
    }
  } catch (e) {
    console.error('Customer search failed', e);
    searchStatus.value = 'idle';
  }
};

const onSearchInput = () => {
  if (searchTimeout.value) clearTimeout(searchTimeout.value);
  searchTimeout.value = window.setTimeout(searchCustomer, 500);
};

// Auto-search initially if phone exists
watch(() => props.lead, () => {
    if (customerPhone.value) {
        searchCustomer();
    }
}, { immediate: true });

const onInnBlur = async () => {
    if (!companyInn.value || companyInn.value.length !== 9) return;
    const data = await lookupCompany(companyInn.value);
    if (data) {
        if (!companyFullLegalName.value) companyFullLegalName.value = data.fullLegalName || '';
        if (!companyLegalAddress.value) companyLegalAddress.value = data.legalAddress || '';
        if (!companyName.value) companyName.value = data.fullLegalName || '';
    }
};

const onIbanBlur = async () => {
    if (!companyIban.value || companyIban.value.length < 15) return;
    const data = await lookupBank(companyIban.value);
    if (data) {
        if (!companyBankName.value) companyBankName.value = data.bankName || '';
        if (!companyBic.value) companyBic.value = data.bic || '';
    }
};


const submitQualify = async () => {
  isLoading.value = true;
  try {
    const payload: ManagerOrderUpdatePayload = {
      status: 'negotiation',
      customer_id: existingCustomerId.value || undefined,
      customer_type: customerType.value,
      customer_name: customerName.value || undefined,
      customer_phone: unmaskedPhone.value || customerPhone.value || undefined,
      customer_delivery_address: [customerCity.value, customerAddress.value].filter(Boolean).join(', ') || undefined,
      customer_inn: customerType.value === 'company' ? (companyInn.value || undefined) : undefined,
      customer_full_legal_name: customerType.value === 'company' ? (companyFullLegalName.value || companyName.value || undefined) : undefined,
      customer_legal_address: customerType.value === 'company' ? (companyLegalAddress.value || undefined) : undefined,
      customer_iban: customerType.value === 'company' ? (companyIban.value || undefined) : undefined,
      customer_bic: customerType.value === 'company' ? (companyBic.value || undefined) : undefined,
      customer_bank_name: customerType.value === 'company' ? (companyBankName.value || undefined) : undefined,
      comment: managerComment.value || undefined,
      object_type: objectType.value || undefined,
      service_type: serviceType.value || undefined,
      equipment_class: equipmentClass.value || undefined,
      marketing_source: marketingSource.value || undefined,
    };

    await api.patchManagerOrder(props.lead.id, payload);
    emit('success', props.lead.id);
  } catch (e) {
    console.error(e);
    alert('Ошибка при сохранении данных');
  } finally {
    isLoading.value = false;
  }
};
</script>

<template>
  <div class="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-[100] p-4 font-sans text-slate-800 dark:text-slate-200">
    <div class="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] flex flex-col overflow-hidden">
      <!-- Header -->
      <div class="px-6 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between shrink-0 bg-slate-50/50 dark:bg-slate-900/50">
        <div>
          <h2 class="text-lg font-bold flex items-center gap-2">
            <span class="material-icons-round text-teal-600 dark:text-teal-500">check_circle</span>
            Квалификация: Заявка #{{ lead.id }}
          </h2>
          <p class="text-xs text-slate-500 mt-1" v-if="(lead as any).source_display">Источник: {{ (lead as any).source_display }}</p>
        </div>
        <button @click="emit('close')" class="w-8 h-8 flex items-center justify-center rounded-full hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-500 transition-colors">
          <span class="material-icons-round text-[18px]">close</span>
        </button>
      </div>

      <!-- Body -->
      <div class="p-6 overflow-y-auto flex-1 space-y-8">
        
        <!-- 1. Client Type Switcher -->
        <div class="flex gap-2 p-1 bg-slate-100 dark:bg-slate-800 rounded-xl w-fit mx-auto">
          <button 
            class="px-5 py-2 rounded-lg text-sm font-semibold transition-all"
            :class="customerType === 'individual' ? 'bg-white dark:bg-slate-700 shadow-sm text-teal-700 dark:text-teal-400' : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'"
            @click="customerType = 'individual'; searchCustomer()"
          >
            👤 Физ. лицо
          </button>
          <button 
            class="px-5 py-2 rounded-lg text-sm font-semibold transition-all"
            :class="customerType === 'company' ? 'bg-white dark:bg-slate-700 shadow-sm text-teal-700 dark:text-teal-400' : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'"
            @click="customerType = 'company'; searchCustomer()"
          >
            🏢 Юр. лицо
          </button>
        </div>

        <!-- Auto-detect Banner -->
        <div v-if="searchStatus === 'found'" class="bg-teal-50 dark:bg-teal-900/30 border border-teal-200 dark:border-teal-800 text-teal-800 dark:text-teal-300 px-4 py-3 rounded-xl flex items-start gap-3 text-sm">
          <span class="material-icons-round text-teal-500 mt-0.5">info</span>
          <div>
            <strong>Найден карточка клиента: {{ foundCustomerName }}</strong><br/>
            Заказ будет автоматически привязан к этому профилю.
            <a :href="'/manager/customers/profile?customerId=' + existingCustomerId" target="_blank" class="ml-2 underline hover:text-teal-600 dark:hover:text-teal-200 font-semibold" title="Открыть в новой вкладке">
              Посмотреть профиль
            </a>
          </div>
        </div>

        <!-- 2. Who and Where -->
        <section>
          <h3 class="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-4 flex items-center gap-2">
            <span class="material-icons-round text-[14px]">person_pin_circle</span>
            Кто и Где
          </h3>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <!-- Company fields -->
            <template v-if="customerType === 'company'">
              <div class="md:col-span-2">
                <label class="block text-xs font-semibold text-slate-500 mb-1">УНП</label>
                <div class="relative">
                  <input v-model="companyInn" type="text" @input="onSearchInput" @blur="onInnBlur" class="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 transition-shadow" placeholder="9 цифр">
                  <div v-if="isEgrLoading" class="absolute right-3 top-2.5">
                    <span class="material-icons-round animate-spin text-teal-500 text-sm">refresh</span>
                  </div>
                </div>
              </div>
              <div class="md:col-span-2">
                <label class="block text-xs font-semibold text-slate-500 mb-1">Короткое название (для списка)</label>
                <input v-model="companyName" type="text" class="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 transition-shadow" placeholder="ООО Мастер Воздуха">
              </div>
              <div class="md:col-span-2">
                <label class="block text-xs font-semibold text-slate-500 mb-1">Полное юридическое название</label>
                <input v-model="companyFullLegalName" type="text" class="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 transition-shadow">
              </div>
              <div class="md:col-span-2">
                <label class="block text-xs font-semibold text-slate-500 mb-1">Юридический адрес</label>
                <input v-model="companyLegalAddress" type="text" class="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 transition-shadow">
              </div>
              <div class="md:col-span-2 grid grid-cols-1 md:grid-cols-3 gap-4">
                <div class="md:col-span-2">
                  <label class="block text-xs font-semibold text-slate-500 mb-1">IBAN (Расчетный счет)</label>
                  <div class="relative">
                    <input v-model="companyIban" type="text" @blur="onIbanBlur" class="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 transition-shadow">
                    <div v-if="isBankLoading" class="absolute right-3 top-2.5">
                      <span class="material-icons-round animate-spin text-teal-500 text-sm">refresh</span>
                    </div>
                  </div>
                </div>
                <div>
                  <label class="block text-xs font-semibold text-slate-500 mb-1">BIC</label>
                  <input v-model="companyBic" type="text" class="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 transition-shadow">
                </div>
              </div>
              <div class="md:col-span-2">
                <label class="block text-xs font-semibold text-slate-500 mb-1">Название банка</label>
                <input v-model="companyBankName" type="text" class="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 transition-shadow">
              </div>
            </template>

            <!-- Base fields -->
            <div>
              <label class="block text-xs font-semibold text-slate-500 mb-1">Имя (Контакт)</label>
              <input v-model="customerName" type="text" class="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 transition-shadow">
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-500 mb-1">Телефон</label>
              <input ref="phoneInputRef" v-model="customerPhone" type="text" @input="onSearchInput" class="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-4 py-2.5 text-sm font-medium focus:ring-2 focus:ring-teal-500 transition-shadow">
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-500 mb-1">Город</label>
              <input v-model="customerCity" type="text" class="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 transition-shadow">
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-500 mb-1">Адрес объекта</label>
              <input v-model="customerAddress" type="text" class="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 transition-shadow" placeholder="ул. Ленина 5, кв 10">
            </div>
          </div>
        </section>

        <!-- 3. What -->
        <section>
          <h3 class="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-4 flex items-center gap-2">
            <span class="material-icons-round text-[14px]">build</span>
            Что делаем
          </h3>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label class="block text-xs font-semibold text-slate-500 mb-2">Тип объекта</label>
              <select v-model="objectType" class="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 appearance-none cursor-pointer">
                <option value="apartment">🏢 Квартира (Стандарт)</option>
                <option value="house">🏡 Частный дом (Леса/Фасад)</option>
                <option value="office">🏬 Офис/Магазин</option>
                <option value="industrial">🏭 Пром/Серверная</option>
              </select>
            </div>
            
            <div>
              <label class="block text-xs font-semibold text-slate-500 mb-2">Суть задачи</label>
              <select v-model="serviceType" class="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 appearance-none cursor-pointer">
                <option value="turnkey">📦 Покупка + Монтаж</option>
                <option value="install_only">🔧 Только монтаж</option>
                <option value="pre_install">🧱 Закладка трассы (Ремонт)</option>
                <option value="maintenance">❄️ Сервис/ТО</option>
                <option value="repair">🛠 Ремонт</option>
              </select>
            </div>
          </div>
        </section>

        <!-- 4. Details -->
        <section>
          <h3 class="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-4 flex items-center gap-2">
            <span class="material-icons-round text-[14px]">info</span>
            Детали
          </h3>
          
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label class="block text-xs font-semibold text-slate-500 mb-2">Источник</label>
              <select v-model="marketingSource" class="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 appearance-none cursor-pointer">
                <option value="">Не указано</option>
                <option value="site">Сайт</option>
                <option value="instagram">Instagram / TikTok</option>
                <option value="referral">Рекомендация (Сарафан)</option>
                <option value="onliner">Onliner</option>
                <option value="kufar">Kufar / 103</option>
              </select>
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-500 mb-2">Предпочтения (Класс)</label>
              <select v-model="equipmentClass" class="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 appearance-none cursor-pointer">
                <option value="">Не определился</option>
                <option value="economy">Эконом (Лишь бы холодило)</option>
                <option value="standard">Цена/Качество (Стандарт)</option>
                <option value="premium">Премиум (Дизайн, тишина, Wi-Fi)</option>
              </select>
            </div>
          </div>

          <div>
            <label class="block text-xs font-semibold text-slate-500 mb-2 flex justify-between">
              Комментарий менеджера
              <span class="text-[10px] text-slate-400 font-normal">для замерщика</span>
            </label>
            <textarea 
              v-model="managerComment" 
              rows="3" 
              class="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-4 py-3 text-sm focus:ring-2 focus:ring-teal-500 transition-shadow resize-y"
              placeholder="Нужна автовышка, потолки 4 метра..."
            ></textarea>
          </div>
        </section>
      </div>

      <!-- Footer Actions -->
      <div class="px-6 py-4 bg-slate-50 dark:bg-slate-900 border-t border-slate-100 dark:border-slate-800 flex gap-3 shrink-0">
        <button 
          @click="submitQualify" 
          :disabled="isLoading"
          class="flex-1 py-3 bg-teal-600 hover:bg-teal-700 disabled:opacity-50 text-white rounded-xl font-bold flex items-center justify-center gap-2 transition-colors"
        >
          <span v-if="isLoading" class="material-icons-round animate-spin">refresh</span>
          <span v-else class="material-icons-round">thumb_up</span>
          Записать на Замер
        </button>
      </div>

    </div>
  </div>
</template>
