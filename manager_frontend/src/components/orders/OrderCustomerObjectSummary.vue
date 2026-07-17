<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { Building2, Copy, Mail, MapPin, Pencil, Phone, Route, UserRound } from 'lucide-vue-next';
import type { OrderCustomerBrief } from '../../client';
import AddressSuggestInput from '../ui/AddressSuggestInput.vue';
import { buildYandexMapUrl } from '../../utils/address';

const props = defineProps<{
  customer?: OrderCustomerBrief | null;
  branch?: { id: number; name?: string | null; delivery_address: string } | null;
  address: string;
  hasComment?: boolean;
  savingCustomer?: boolean;
}>();

const emit = defineEmits<{
  copy: [value: string, label: string];
  'save-customer': [payload: { name: string; phone: string; email: string }];
  'update:address': [value: string];
  'open-customer': [];
  'change-customer': [];
  'toggle-branch': [];
}>();

const editingCustomer = ref(false);
const editingObject = ref(false);
const customerName = ref('');
const customerPhone = ref('');
const customerEmail = ref('');
const objectAddress = ref('');

const displayName = computed(() => props.customer?.full_legal_name || props.customer?.name || 'Клиент не выбран');
const phone = computed(() => String(props.customer?.phone || '').trim());
const email = computed(() => String(props.customer?.email || '').trim());
const phoneDigits = computed(() => phone.value.replace(/\D/g, ''));
const validPhone = computed(() => phoneDigits.value.length >= 7);
const validEmail = computed(() => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value));
const mapUrl = computed(() => buildYandexMapUrl(props.address));

watch(() => props.address, (value) => {
  if (!editingObject.value) objectAddress.value = value;
}, { immediate: true });

const startCustomerEdit = () => {
  customerName.value = props.customer?.full_legal_name || props.customer?.name || '';
  customerPhone.value = phone.value;
  customerEmail.value = email.value;
  editingCustomer.value = true;
};

const saveCustomer = () => {
  emit('save-customer', {
    name: customerName.value.trim(),
    phone: customerPhone.value.trim(),
    email: customerEmail.value.trim(),
  });
  editingCustomer.value = false;
};

const startObjectEdit = () => {
  objectAddress.value = props.address;
  editingObject.value = true;
};

const saveObject = () => {
  emit('update:address', objectAddress.value.trim());
  editingObject.value = false;
};
</script>

<template>
  <section class="mt-3 overflow-hidden rounded-xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
    <div class="flex flex-col divide-y divide-slate-100 dark:divide-slate-800">
      <div class="grid min-w-0 grid-cols-[2rem_minmax(0,1fr)] items-start gap-x-3 px-3 py-2.5 sm:grid-cols-[2rem_minmax(0,1fr)_auto]">
        <span class="row-span-2 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          <Building2 v-if="customer?.type === 'company'" :size="17" />
          <UserRound v-else :size="17" />
        </span>
        <div class="min-w-0 flex-1">
          <p class="break-words text-sm font-semibold leading-5 text-slate-900 dark:text-white">{{ displayName }}</p>
          <div class="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
            <a v-if="validPhone" :href="'tel:' + phoneDigits" class="inline-flex items-center gap-1 hover:text-teal-700 dark:hover:text-teal-300">
              <Phone :size="13" /> {{ phone }}
            </a>
            <button v-else type="button" class="font-medium text-amber-700 dark:text-amber-300" @click="startCustomerEdit">Телефон не указан · добавить</button>
            <a v-if="validEmail" :href="'mailto:' + email" class="inline-flex min-w-0 items-center gap-1 hover:text-teal-700 dark:hover:text-teal-300">
              <Mail :size="13" /> <span class="truncate">{{ email }}</span>
            </a>
            <button v-else type="button" class="font-medium text-slate-500 hover:text-teal-700 dark:hover:text-teal-300" @click="startCustomerEdit">Email не указан · добавить</button>
          </div>
        </div>
        <div class="col-start-2 row-start-2 mt-1 flex shrink-0 gap-1 sm:col-start-3 sm:row-start-1 sm:mt-0">
          <button v-if="validPhone" type="button" class="icon-action" aria-label="Скопировать телефон" @click="emit('copy', phone, 'Телефон')"><Copy :size="15" /></button>
          <button type="button" class="icon-action" aria-label="Редактировать клиента" @click="startCustomerEdit"><Pencil :size="15" /></button>
          <button type="button" class="icon-action hidden sm:flex" aria-label="Открыть полную карточку клиента" @click="emit('open-customer')"><Route :size="15" /></button>
        </div>
      </div>

      <div class="flex min-w-0 items-center gap-3 px-3 py-2.5">
        <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-teal-50 text-teal-700 dark:bg-teal-500/15 dark:text-teal-200"><MapPin :size="17" /></span>
        <div class="min-w-0 flex-1">
          <p class="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-400">{{ branch?.name || 'Объект' }}</p>
          <p v-if="address" class="truncate text-sm font-medium text-slate-800 dark:text-slate-100">{{ address }}</p>
          <button v-else type="button" class="text-sm font-medium text-amber-700 dark:text-amber-300" @click="startObjectEdit">Адрес не указан · добавить</button>
          <p v-if="hasComment" class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">Есть комментарий к объекту</p>
        </div>
        <div class="flex shrink-0 gap-1">
          <a v-if="address" :href="mapUrl" target="_blank" class="icon-action" aria-label="Открыть объект на карте"><Route :size="15" /></a>
          <button v-if="address" type="button" class="icon-action" aria-label="Скопировать адрес объекта" @click="emit('copy', address, 'Адрес')"><Copy :size="15" /></button>
          <button type="button" class="icon-action" aria-label="Редактировать объект" @click="startObjectEdit"><Pencil :size="15" /></button>
        </div>
      </div>
    </div>

    <div v-if="editingCustomer" class="border-t border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-950/50">
      <div class="grid gap-2 sm:grid-cols-2">
        <input v-model="customerName" class="field-input sm:col-span-2" placeholder="Имя или название клиента" />
        <input v-model="customerPhone" class="field-input" placeholder="Телефон" inputmode="tel" />
        <input v-model="customerEmail" class="field-input" placeholder="Email" inputmode="email" />
      </div>
      <div class="mt-2 flex flex-wrap justify-between gap-2">
        <div class="flex gap-2">
          <button type="button" class="btn-mini-outline text-xs" @click="emit('change-customer')">Сменить клиента</button>
          <button type="button" class="btn-mini-outline text-xs" @click="emit('toggle-branch')">Филиал</button>
        </div>
        <div class="flex gap-2">
          <button type="button" class="btn-mini-outline text-xs" @click="editingCustomer = false">Отмена</button>
          <button type="button" class="btn-mini text-xs" :disabled="savingCustomer || !customerName" @click="saveCustomer">{{ savingCustomer ? 'Сохраняем' : 'Сохранить' }}</button>
        </div>
      </div>
    </div>

    <div v-if="editingObject" class="border-t border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-950/50">
      <AddressSuggestInput v-model="objectAddress" label="Адрес объекта" />
      <div class="mt-2 flex justify-between gap-2">
        <button type="button" class="btn-mini-outline text-xs" @click="emit('toggle-branch')">Выбрать филиал</button>
        <div class="flex gap-2">
          <button type="button" class="btn-mini-outline text-xs" @click="editingObject = false">Отмена</button>
          <button type="button" class="btn-mini text-xs" @click="saveObject">Применить</button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.icon-action {
  display: inline-flex;
  height: 2rem;
  width: 2rem;
  align-items: center;
  justify-content: center;
  border-radius: 0.5rem;
  color: rgb(100 116 139);
  transition: color 150ms, background-color 150ms;
}
.icon-action:hover {
  background: rgb(241 245 249);
  color: rgb(15 118 110);
}
:global(.dark) .icon-action:hover {
  background: rgb(30 41 59);
  color: rgb(94 234 212);
}
</style>
