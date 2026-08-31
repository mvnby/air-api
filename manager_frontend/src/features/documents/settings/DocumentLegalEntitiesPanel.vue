<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { DocumentLegalEntityItem, DocumentLegalEntityUpdatePayload } from '../../../client';
import { useB2BLookup } from '../../../composables/useB2BLookup';
import { normalizeIban, normalizeUnp } from '../../../utils/legal-requisites';

type SellerEntityType = 'organization' | 'individual_entrepreneur';
type SigningMode = 'self' | 'statutory_body' | 'power_of_attorney';

const props = defineProps<{
  items: DocumentLegalEntityItem[];
  selectedId: number | null;
  loading: boolean;
  saving: boolean;
}>();

const emit = defineEmits<{
  select: [id: number];
  create: [name: string];
  update: [id: number, changes: DocumentLegalEntityUpdatePayload];
}>();

const newName = ref('');
const legalName = ref('');
const unp = ref('');
const entityType = ref<SellerEntityType>('organization');
const isVatPayer = ref(false);
const city = ref('');
const legalAddress = ref('');
const bankName = ref('');
const iban = ref('');
const bic = ref('');
const signingMode = ref<SigningMode>('statutory_body');
const signerPosition = ref('');
const signerName = ref('');
const actingBasis = ref('');
const offerUrl = ref('');
const offerVersion = ref('');
const offerPublishedOn = ref('');
const defaultGoodsWarrantyMonths = ref<number | null>(36);
const defaultWorkWarrantyMonths = ref<number | null>(null);
const egrLookupSucceeded = ref(false);
const bankLookupSucceeded = ref(false);
const {
  lookupCompany,
  lookupBank,
  isEgrLoading,
  isBankLoading,
  egrError,
  bankError,
} = useB2BLookup();

const isIndividualEntrepreneur = computed(() => entityType.value === 'individual_entrepreneur');
const isPowerOfAttorney = computed(() => signingMode.value === 'power_of_attorney');
const showsSignerFields = computed(() => !isIndividualEntrepreneur.value || isPowerOfAttorney.value);

const selectEntityType = (value: SellerEntityType) => {
  entityType.value = value;
  if (value === 'organization' && signingMode.value === 'self') signingMode.value = 'statutory_body';
  if (value === 'individual_entrepreneur' && signingMode.value === 'statutory_body') signingMode.value = 'self';
};

const selectSigningMode = (value: SigningMode) => {
  signingMode.value = value;
  if (value === 'statutory_body' && !actingBasis.value.trim()) actingBasis.value = 'Устава';
};

const syncForm = () => {
  const entity = props.items.find((item) => item.id === props.selectedId);
  legalName.value = entity?.legal_name || '';
  unp.value = entity?.unp || '';
  entityType.value = entity?.entity_type === 'individual_entrepreneur'
    ? 'individual_entrepreneur'
    : 'organization';
  isVatPayer.value = Boolean(entity?.is_vat_payer);
  city.value = entity?.requisites.city || '';
  legalAddress.value = entity?.requisites.legal_address || '';
  bankName.value = entity?.requisites.bank_name || '';
  iban.value = entity?.requisites.iban || '';
  bic.value = entity?.requisites.bic || '';
  const defaultMode: SigningMode = entityType.value === 'individual_entrepreneur' ? 'self' : 'statutory_body';
  const storedMode = entity?.requisites.signing_mode;
  signingMode.value = storedMode === 'power_of_attorney' || storedMode === 'self' || storedMode === 'statutory_body'
    ? storedMode
    : defaultMode;
  if (entityType.value === 'organization' && signingMode.value === 'self') signingMode.value = 'statutory_body';
  if (entityType.value === 'individual_entrepreneur' && signingMode.value === 'statutory_body') signingMode.value = 'self';
  signerPosition.value = entity?.requisites.signer_position || entity?.requisites.director_title || '';
  signerName.value = entity?.requisites.signer_name || entity?.requisites.director_name || '';
  actingBasis.value = entity?.requisites.acting_basis || entity?.requisites.acts_on_basis || '';
  offerUrl.value = entity?.requisites.offer_url || '';
  offerVersion.value = entity?.requisites.offer_version || '';
  offerPublishedOn.value = entity?.requisites.offer_published_on || '';
  const rawGoodsMonths = entity?.requisites.default_goods_warranty_months;
  const goodsMonths = rawGoodsMonths == null || rawGoodsMonths === '' ? Number.NaN : Number(rawGoodsMonths);
  defaultGoodsWarrantyMonths.value = Number.isFinite(goodsMonths) ? goodsMonths : 36;
  const rawWorkMonths = entity?.requisites.default_work_warranty_months;
  const workMonths = rawWorkMonths == null || rawWorkMonths === '' ? Number.NaN : Number(rawWorkMonths);
  defaultWorkWarrantyMonths.value = Number.isFinite(workMonths) ? workMonths : null;
  egrError.value = '';
  bankError.value = '';
  egrLookupSucceeded.value = false;
  bankLookupSucceeded.value = false;
};

watch(() => [props.selectedId, props.items], syncForm, { immediate: true, deep: true });

const create = () => {
  const name = newName.value.trim();
  if (!name) return;
  emit('create', name);
  newName.value = '';
};

const onUnpInput = () => {
  unp.value = normalizeUnp(unp.value);
  egrError.value = '';
  egrLookupSucceeded.value = false;
};

const onUnpBlur = async () => {
  const requestedUnp = normalizeUnp(unp.value);
  unp.value = requestedUnp;
  if (requestedUnp.length !== 9) return;
  const company = await lookupCompany(requestedUnp);
  if (!company || normalizeUnp(unp.value) !== requestedUnp) return;
  if (!legalName.value.trim()) legalName.value = company.fullLegalName || '';
  if (!legalAddress.value.trim()) legalAddress.value = company.legalAddress || '';
  egrLookupSucceeded.value = true;
};

const onIbanInput = () => {
  iban.value = normalizeIban(iban.value);
  bankError.value = '';
  bankLookupSucceeded.value = false;
};

const onIbanBlur = async () => {
  const requestedIban = normalizeIban(iban.value);
  iban.value = requestedIban;
  if (requestedIban.length < 15) return;
  const bank = await lookupBank(requestedIban);
  if (!bank || normalizeIban(iban.value) !== requestedIban) return;
  if (!bankName.value.trim()) bankName.value = bank.bankName || '';
  if (!bic.value.trim()) bic.value = bank.bic || '';
  bankLookupSucceeded.value = true;
};

const updateWarrantyMonths = (kind: 'goods' | 'work', event: Event) => {
  const rawValue = (event.target as HTMLInputElement).value;
  const parsed = rawValue === '' ? null : Number(rawValue);
  const value = Number.isFinite(parsed) ? parsed : null;
  if (kind === 'goods') defaultGoodsWarrantyMonths.value = value ?? 36;
  else defaultWorkWarrantyMonths.value = value;
};

const save = () => {
  if (!props.selectedId) return;
  const requisites = {
    offer_url: offerUrl.value.trim() || null,
    offer_version: offerVersion.value.trim() || null,
    offer_published_on: offerPublishedOn.value.trim() || null,
    default_goods_warranty_months: defaultGoodsWarrantyMonths.value ?? 36,
    default_work_warranty_months: defaultWorkWarrantyMonths.value,
    legal_address: legalAddress.value.trim() || null,
    city: city.value.trim() || null,
    bank_name: bankName.value.trim() || null,
    iban: iban.value.trim() || null,
    bic: bic.value.trim() || null,
    signing_mode: signingMode.value,
    signer_position: signerPosition.value.trim() || null,
    signer_name: signerName.value.trim() || null,
    acting_basis: actingBasis.value.trim() || null,
  };
  emit('update', props.selectedId, {
    legal_name: legalName.value.trim() || null,
    unp: unp.value.trim() || null,
    entity_type: entityType.value,
    is_vat_payer: isVatPayer.value,
    requisites,
  });
};
</script>

<template>
  <section class="settings-card">
    <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h2 class="settings-title">Организации и ИП</h2>
        <p class="settings-help">Реквизиты продавца фиксируются в снимке при создании черновика.</p>
      </div>
      <span v-if="loading" class="material-icons-round animate-spin text-teal-600">progress_activity</span>
    </div>

    <div class="mt-5 grid gap-5 lg:grid-cols-[280px_minmax(0,1fr)]">
      <div class="space-y-2">
        <button
          v-for="entity in items"
          :key="entity.id"
          type="button"
          class="w-full rounded-xl border p-3 text-left transition"
          :class="entity.id === selectedId ? 'border-teal-500 bg-teal-50 dark:bg-teal-950/30' : 'border-slate-200 hover:border-slate-300 dark:border-slate-700'"
          @click="emit('select', entity.id)"
        >
          <span class="flex items-center justify-between gap-3">
            <span class="font-semibold text-slate-900 dark:text-white">{{ entity.display_name }}</span>
            <span v-if="entity.is_default" class="rounded-full bg-teal-100 px-2 py-0.5 text-[11px] font-bold text-teal-800">По умолчанию</span>
          </span>
          <span class="mt-1 block text-xs text-slate-500">{{ entity.unp ? `УНП ${entity.unp}` : 'УНП не указан' }}</span>
        </button>

        <form class="flex gap-2 pt-2" @submit.prevent="create">
          <input v-model="newName" class="settings-input min-w-0 flex-1" placeholder="ООО МВН или ИП Иванов" />
          <button class="settings-button-secondary" type="submit" :disabled="saving || !newName.trim()">+Добавить</button>
        </form>
      </div>

      <form v-if="selectedId" class="grid gap-4 sm:grid-cols-2" @submit.prevent="save">
        <div class="settings-field sm:col-span-2">
          <span>Тип продавца</span>
          <div data-testid="seller-entity-type" class="grid grid-cols-2 rounded-xl border border-slate-200 bg-slate-50 p-1 dark:border-slate-700 dark:bg-slate-950">
            <button
              v-for="option in ([
                { value: 'organization', label: 'Организация' },
                { value: 'individual_entrepreneur', label: 'ИП' },
              ] as const)"
              :key="option.value"
              type="button"
              class="h-9 rounded-lg px-3 text-sm font-semibold transition"
              :class="entityType === option.value ? 'bg-white text-teal-700 shadow-sm dark:bg-slate-800 dark:text-teal-300' : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-white'"
              :aria-pressed="entityType === option.value"
              @click="selectEntityType(option.value)"
            >{{ option.label }}</button>
          </div>
        </div>
        <label class="settings-field sm:col-span-2">
          <span>Полное наименование</span>
          <input v-model="legalName" data-testid="seller-legal-name" class="settings-input" />
        </label>
        <label class="settings-field">
          <span>УНП</span>
          <span class="relative">
            <input v-model="unp" data-testid="seller-unp" class="settings-input pr-10" inputmode="numeric" maxlength="9" @input="onUnpInput" @blur="onUnpBlur" />
            <span v-if="isEgrLoading" class="material-icons-round absolute right-3 top-2.5 animate-spin text-[18px] text-teal-600">progress_activity</span>
          </span>
          <span v-if="egrError" class="font-normal text-red-600">{{ egrError }}</span>
          <span v-else-if="egrLookupSucceeded" class="font-normal text-emerald-700">Наименование и адрес найдены в ЕГР</span>
        </label>
        <button
          type="button"
          class="mt-6 flex h-10 items-center justify-between rounded-xl border px-3 text-sm font-semibold"
          :class="isVatPayer ? 'border-teal-500 bg-teal-50 text-teal-800' : 'border-slate-200 text-slate-600 dark:border-slate-700 dark:text-slate-300'"
          @click="isVatPayer = !isVatPayer"
        >
          <span>Плательщик НДС</span>
          <span class="material-icons-round text-[20px]">{{ isVatPayer ? 'toggle_on' : 'toggle_off' }}</span>
        </button>
        <div class="settings-field rounded-xl border border-teal-100 bg-teal-50/60 p-4 sm:col-span-2 dark:border-teal-900/60 dark:bg-teal-950/20">
          <span class="text-sm font-bold text-teal-950 dark:text-teal-100">Документы для физлиц</span>
          <span class="font-normal text-slate-500">Оферта и гарантия подставляются в заказ-акты. В документе всегда сохраняется значение на дату создания черновика.</span>
          <div class="mt-3 grid gap-3 sm:grid-cols-2">
            <label class="settings-field sm:col-span-2"><span>Ссылка на публичную оферту</span><input v-model="offerUrl" data-testid="consumer-offer-url" class="settings-input" type="url" placeholder="https://example.by/offer" /></label>
            <label class="settings-field"><span>Версия оферты</span><input v-model="offerVersion" data-testid="consumer-offer-version" class="settings-input" placeholder="Редакция 1.0" /></label>
            <label class="settings-field"><span>Опубликована</span><input v-model="offerPublishedOn" data-testid="consumer-offer-published-on" class="settings-input" placeholder="04.06.2026" inputmode="numeric" /></label>
            <label class="settings-field"><span>Гарантия на оборудование по умолчанию, мес.</span><input :value="defaultGoodsWarrantyMonths ?? 36" data-testid="default-goods-warranty-months" class="settings-input" type="number" min="0" max="240" @input="updateWarrantyMonths('goods', $event)" /></label>
            <label class="settings-field"><span>Гарантия на работы по умолчанию, мес.</span><input :value="defaultWorkWarrantyMonths ?? ''" data-testid="default-work-warranty-months" class="settings-input" type="number" min="0" max="240" placeholder="Не задана" @input="updateWarrantyMonths('work', $event)" /></label>
          </div>
        </div>
        <label class="settings-field"><span>Город</span><input v-model="city" data-testid="seller-city" class="settings-input" placeholder="Например, Витебск" /></label>
        <label class="settings-field sm:col-span-2"><span>{{ isIndividualEntrepreneur ? 'Адрес регистрации' : 'Юридический адрес' }}</span><input v-model="legalAddress" data-testid="seller-legal-address" class="settings-input" /></label>
        <label class="settings-field sm:col-span-2"><span>Банк</span><input v-model="bankName" data-testid="seller-bank-name" class="settings-input" /></label>
        <label class="settings-field">
          <span>IBAN</span>
          <span class="relative">
            <input v-model="iban" data-testid="seller-iban" class="settings-input pr-10" autocomplete="off" @input="onIbanInput" @blur="onIbanBlur" />
            <span v-if="isBankLoading" class="material-icons-round absolute right-3 top-2.5 animate-spin text-[18px] text-teal-600">progress_activity</span>
          </span>
          <span v-if="bankError" class="font-normal text-red-600">{{ bankError }}</span>
          <span v-else-if="bankLookupSucceeded" class="font-normal text-emerald-700">Банк и BIC определены по IBAN</span>
        </label>
        <label class="settings-field"><span>BIC</span><input v-model="bic" data-testid="seller-bic" class="settings-input" /></label>
        <div class="settings-field sm:col-span-2">
          <span>Кто подписывает</span>
          <div data-testid="seller-signing-mode" class="grid grid-cols-2 rounded-xl border border-slate-200 bg-slate-50 p-1 dark:border-slate-700 dark:bg-slate-950">
            <button
              type="button"
              class="h-9 rounded-lg px-3 text-sm font-semibold transition"
              :class="!isPowerOfAttorney ? 'bg-white text-teal-700 shadow-sm dark:bg-slate-800 dark:text-teal-300' : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-white'"
              :aria-pressed="!isPowerOfAttorney"
              @click="selectSigningMode(isIndividualEntrepreneur ? 'self' : 'statutory_body')"
            >{{ isIndividualEntrepreneur ? 'Лично' : 'Руководитель' }}</button>
            <button
              type="button"
              class="h-9 rounded-lg px-3 text-sm font-semibold transition"
              :class="isPowerOfAttorney ? 'bg-white text-teal-700 shadow-sm dark:bg-slate-800 dark:text-teal-300' : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-white'"
              :aria-pressed="isPowerOfAttorney"
              @click="selectSigningMode('power_of_attorney')"
            >Представитель</button>
          </div>
          <span v-if="isIndividualEntrepreneur && !isPowerOfAttorney" class="font-normal text-slate-500">ИП действует от собственного имени — отдельное основание не требуется.</span>
        </div>
        <label class="settings-field sm:col-span-2"><span>{{ isIndividualEntrepreneur && !isPowerOfAttorney ? 'ФИО предпринимателя' : 'ФИО подписанта' }}</span><input v-model="signerName" data-testid="seller-signer-name" class="settings-input" /></label>
        <template v-if="showsSignerFields">
          <label class="settings-field"><span>Должность подписанта</span><input v-model="signerPosition" data-testid="seller-signer-position" class="settings-input" :placeholder="isPowerOfAttorney ? 'Представитель' : 'Директор'" /></label>
          <label class="settings-field"><span>Основание полномочий</span><input v-model="actingBasis" data-testid="seller-acting-basis" class="settings-input" :placeholder="isPowerOfAttorney ? 'доверенности № 4 от 01.08.2026' : 'Устава'" /></label>
        </template>
        <div class="flex flex-wrap gap-2 sm:col-span-2">
          <button class="settings-button-primary" type="submit" :disabled="saving">{{ saving ? 'Сохраняем…' : 'Сохранить реквизиты' }}</button>
          <button
            v-if="!items.find((item) => item.id === selectedId)?.is_default"
            type="button"
            class="settings-button-secondary"
            :disabled="saving"
            @click="emit('update', selectedId, { is_default: true })"
          >Сделать основным</button>
        </div>
      </form>
      <p v-else class="self-center text-sm text-slate-500">Добавьте организацию или ИП, чтобы настроить документы.</p>
    </div>
  </section>
</template>
