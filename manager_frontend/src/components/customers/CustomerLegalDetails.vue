<script setup lang="ts">
import AddressSuggestInput from '../ui/AddressSuggestInput.vue';
import {
  customerPartyLabel,
  isBusinessCustomer,
  type CustomerForm,
} from './customer-profile-form';

const props = defineProps<{
  customer: CustomerForm;
  editing: boolean;
  fieldClass: (key: keyof CustomerForm) => Record<string, boolean>;
  ibanError: string;
  isBankLoading: boolean;
  serverErrors: Record<string, string>;
  lastDeliveryAddress: string;
}>();

const emit = defineEmits<{
  'update:customer': [customer: CustomerForm];
  ibanBlur: [];
}>();

const update = <K extends keyof CustomerForm>(key: K, value: CustomerForm[K]) => {
  emit('update:customer', { ...props.customer, [key]: value });
};

const eventValue = (event: Event) => (event.target as HTMLInputElement).value;

const business = () => isBusinessCustomer(props.customer.type);
const entrepreneurSigningPersonally = () => (
  props.customer.type === 'individual_entrepreneur' && props.customer.signing_mode === 'self'
);
</script>

<template>
  <article class="rounded-[1.5rem] border border-[var(--mv-border)] bg-[var(--mv-surface)] p-5 shadow-sm">
    <h2 class="mb-3 text-sm font-semibold uppercase tracking-[0.16em] text-[var(--mv-text-muted)]">Реквизиты и подписант</h2>

    <template v-if="!editing">
      <div class="space-y-2 text-sm">
        <p class="detail-value"><span>Тип</span><strong>{{ customerPartyLabel(customer.type) }}</strong></p>
        <p class="detail-value"><span>Город</span><strong>{{ customer.city || '—' }}</strong></p>
        <template v-if="business()">
          <p class="detail-value"><span>Полное наименование</span><strong>{{ customer.full_legal_name || '—' }}</strong></p>
          <p class="detail-value"><span>Юр. адрес</span><strong>{{ customer.legal_address || '—' }}</strong></p>
          <p class="detail-value"><span>Факт. адрес</span><strong>{{ customer.actual_address || '—' }}</strong></p>
          <p class="detail-value"><span>Банк</span><strong>{{ customer.bank_name || '—' }}</strong></p>
          <p class="detail-value"><span>BIC</span><strong>{{ customer.bic || '—' }}</strong></p>
          <p class="detail-value"><span>IBAN</span><strong>{{ customer.iban || '—' }}</strong></p>
          <p class="detail-value"><span>Подписант</span><strong>{{ customer.signer_name || '—' }}</strong></p>
          <template v-if="!entrepreneurSigningPersonally()">
            <p class="detail-value"><span>Должность</span><strong>{{ customer.signer_position || '—' }}</strong></p>
            <p class="detail-value"><span>Основание</span><strong>{{ customer.acting_basis || '—' }}</strong></p>
          </template>
          <p class="detail-value"><span>Последний адрес доставки</span><strong>{{ lastDeliveryAddress || '—' }}</strong></p>
        </template>
      </div>
    </template>

    <template v-else>
      <div class="space-y-3 text-sm">
        <input :value="customer.city" type="text" placeholder="Город" :class="fieldClass('city')" @input="update('city', eventValue($event))" />
        <div v-if="business()" class="space-y-3">
          <input :value="customer.full_legal_name" type="text" placeholder="Полное наименование" :class="fieldClass('full_legal_name')" @input="update('full_legal_name', eventValue($event))" />
          <AddressSuggestInput
            :model-value="customer.legal_address"
            placeholder="Юр. адрес"
            :input-class="fieldClass('legal_address')"
            :error="serverErrors.legal_address"
            @update:model-value="update('legal_address', $event)"
          />
          <AddressSuggestInput
            :model-value="customer.actual_address"
            placeholder="Факт. адрес"
            :input-class="fieldClass('actual_address')"
            :error="serverErrors.actual_address"
            @update:model-value="update('actual_address', $event)"
          />
          <input :value="customer.bank_name" type="text" placeholder="Название банка" :class="fieldClass('bank_name')" @input="update('bank_name', eventValue($event))" />
          <input :value="customer.bic" type="text" placeholder="BIC" :class="fieldClass('bic')" @input="update('bic', eventValue($event))" />
          <div class="relative">
            <input :value="customer.iban" type="text" placeholder="IBAN" :class="fieldClass('iban')" @input="update('iban', eventValue($event))" @blur="emit('ibanBlur')" />
            <div v-if="isBankLoading" class="absolute right-3 top-2">
              <span class="material-icons-round animate-spin text-teal-500 text-sm">refresh</span>
            </div>
          </div>
          <span v-if="ibanError" class="field-error">{{ ibanError }}</span>

          <div class="space-y-2">
            <p class="text-xs font-medium text-[var(--mv-text-muted)]">Подписание договора</p>
            <div class="flex rounded-lg bg-[var(--mv-panel)] p-1">
              <button
                type="button"
                class="flex-1 rounded-md px-3 py-2 text-sm transition-all"
                :class="customer.signing_mode !== 'power_of_attorney' ? 'bg-white font-medium text-teal-700 shadow-sm dark:bg-slate-600 dark:text-teal-300' : 'text-[var(--mv-text-muted)]'"
                @click="update('signing_mode', customer.type === 'company' ? 'statutory_body' : 'self')"
              >{{ customer.type === 'company' ? 'Руководитель' : 'Лично' }}</button>
              <button
                type="button"
                class="flex-1 rounded-md px-3 py-2 text-sm transition-all"
                :class="customer.signing_mode === 'power_of_attorney' ? 'bg-white font-medium text-teal-700 shadow-sm dark:bg-slate-600 dark:text-teal-300' : 'text-[var(--mv-text-muted)]'"
                @click="update('signing_mode', 'power_of_attorney')"
              >Представитель</button>
            </div>
          </div>
          <input :value="customer.signer_name" type="text" placeholder="Подписант" :class="fieldClass('signer_name')" @input="update('signer_name', eventValue($event))" />
          <p v-if="entrepreneurSigningPersonally()" class="rounded-lg bg-teal-500/10 px-3 py-2 text-xs text-[var(--mv-text-muted)]">
            ИП подписывает договор лично; должность и основание действий не требуются.
          </p>
          <template v-else>
            <input :value="customer.signer_position" type="text" placeholder="Должность подписанта" :class="fieldClass('signer_position')" @input="update('signer_position', eventValue($event))" />
            <input :value="customer.acting_basis" type="text" placeholder="Основание действий" :class="fieldClass('acting_basis')" @input="update('acting_basis', eventValue($event))" />
          </template>
        </div>
        <p v-else class="text-xs text-[var(--mv-text-muted)]">Для физлица реквизиты и режим подписания не требуются.</p>
      </div>
    </template>
  </article>
</template>
