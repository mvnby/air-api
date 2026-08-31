<script setup lang="ts">
import type { TransportTerms } from '../model/transport-terms';

const props = defineProps<{
  documentType: string;
  terms: TransportTerms;
}>();
const emit = defineEmits<{ updateTerms: [terms: TransportTerms] }>();

const update = (field: keyof TransportTerms, value: string) => {
  emit('updateTerms', { ...props.terms, [field]: value || null });
};
</script>

<template>
  <section class="mt-4 rounded-xl border border-sky-200 bg-sky-50/60 p-4 dark:border-sky-900/70 dark:bg-sky-950/20" data-testid="transport-terms-panel">
    <div>
      <p class="text-sm font-bold text-slate-900 dark:text-white">Транспортные реквизиты</p>
      <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
        Заполняются в печатной форме {{ documentType === 'ttn1' ? 'ТТН-1' : 'ТН-2' }}. CRM пока не отправляет электронную накладную в EDI.
      </p>
    </div>
    <div class="mt-3 grid gap-3 md:grid-cols-2">
      <label class="native-field">
        <span>Автомобиль</span>
        <input :value="terms.car_model || ''" class="native-input" placeholder="Например, ГАЗель Next" @input="update('car_model', ($event.target as HTMLInputElement).value)" />
      </label>
      <label class="native-field">
        <span>Регистрационный номер</span>
        <input :value="terms.car_number || ''" class="native-input" placeholder="1234 АВ-2" @input="update('car_number', ($event.target as HTMLInputElement).value)" />
      </label>
      <label class="native-field">
        <span>Водитель</span>
        <input :value="terms.driver_name || ''" class="native-input" placeholder="ФИО водителя" @input="update('driver_name', ($event.target as HTMLInputElement).value)" />
      </label>
      <label class="native-field">
        <span>Перевозчик</span>
        <input :value="terms.carrier || ''" class="native-input" placeholder="Наименование или ФИО" @input="update('carrier', ($event.target as HTMLInputElement).value)" />
      </label>
    </div>
    <p v-if="documentType === 'ttn1' && (!terms.car_number || !terms.driver_name || !terms.carrier)" class="mt-3 text-xs font-semibold text-amber-700 dark:text-amber-300">
      Черновик можно сохранить, но перед выпуском проверьте номер автомобиля, водителя и перевозчика.
    </p>
  </section>
</template>

