<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { ArrowLeftRight, Copy, ExternalLink, MapPin, Pencil } from 'lucide-vue-next';
import { api } from '../../api';
import { useCompanyAddressSuggestion } from '../../composables/useCompanyAddressSuggestion';
import type { ManagerCatalogCustomerItemResponse, ManagerCustomerBranchItemResponse, ManagerOrderDetailResponse } from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
import { confirmDialog } from '../../services/ui-feedback';
import { buildYandexMapUrl } from '../../utils/address';
import AddressSuggestInput from '../ui/AddressSuggestInput.vue';
import CustomerSearchSelect from '../customers/CustomerSearchSelect.vue';
import OrderWorkspaceContext from './OrderWorkspaceContext.vue';

type ObjectDraft = { address: string; branchId: number | null; comment: string };
const props = withDefaults(defineProps<{
  order: ManagerOrderDetailResponse; total?: number; paid?: number; balance?: number; disabled?: boolean;
  addressError?: string; commentError?: string; saveError?: string;
  beforeNavigate?: () => Promise<boolean>; beforeSave?: () => Promise<boolean>;
  persistObject?: (draft: ObjectDraft) => Promise<boolean>;
}>(), { total: 0, paid: 0, balance: 0, disabled: false });
const emit = defineEmits<{
  toast: [payload: { message: string; type: 'success' | 'error' }];
  updated: [order: ManagerOrderDetailResponse]; reload: [orderId: number]; payments: [];
}>();
const deliveryAddress = defineModel<string>('deliveryAddress', { required: true });
const customerBranchId = defineModel<number | null>('customerBranchId', { required: true });
const comment = defineModel<string>('comment', { required: true });
const editTarget = defineModel<'customer' | 'object' | null>('editTarget', { default: null });
const customerMode = ref<'summary' | 'edit' | 'change'>('summary');
const customerName = ref(''), customerPhone = ref(''), customerEmail = ref('');
const searchedCustomer = ref<ManagerCatalogCustomerItemResponse | null>(null);
const savingCustomer = ref(false), assigningCustomer = ref(false), savingObject = ref(false);
const customerError = ref(''), objectError = ref('');
const draftAddress = ref(deliveryAddress.value), draftBranchId = ref(customerBranchId.value), draftComment = ref(comment.value);
const branches = ref<ManagerCustomerBranchItemResponse[]>([]);
const branchesLoading = ref(false), branchError = ref(''), creatingBranch = ref(false), newBranchOpen = ref(false);
const newBranchName = ref(''), newBranchAddress = ref('');
const customerNameField = ref<HTMLTextAreaElement | null>(null);
let epoch = 0, branchesRequest = 0;
const customer = computed(() => props.order.customer ?? null);
const displayName = computed(() => customer.value?.full_legal_name || customer.value?.name || '');
const phone = computed(() => String(customer.value?.phone || '').trim());
const email = computed(() => String(customer.value?.email || '').trim());
const phoneDigits = computed(() => phone.value.replace(/\D/g, ''));
const validPhone = computed(() => phoneDigits.value.length >= 7);
const validEmail = computed(() => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value));
const busy = computed(() => props.disabled || savingCustomer.value || assigningCustomer.value || savingObject.value || creatingBranch.value);
const selectedBranch = computed(() => branches.value.find(item => item.id === draftBranchId.value)
  || (props.order.customer_branch?.id === draftBranchId.value ? props.order.customer_branch : null));
const objectAddress = computed(() => deliveryAddress.value.trim() || props.order.customer_branch?.delivery_address || '');
const { candidates: addressCandidates, loading: addressLoading, error: addressLookupError,
  searched: addressSearched, suggest: suggestAddress, reset: resetAddressSuggestions } = useCompanyAddressSuggestion();
const canSuggestAddress = computed(() => customer.value?.type === 'company' && !draftAddress.value.trim() && Boolean(displayName.value.trim()));
const notify = (message: string, type: 'success' | 'error') => emit('toast', { message, type });
const current = (scope: number, orderId: number) => scope === epoch && props.order.id === orderId;
const prepare = async () => !props.beforeSave || await props.beforeSave();
const resetObjectDraft = () => {
  draftAddress.value = deliveryAddress.value; draftBranchId.value = customerBranchId.value; draftComment.value = comment.value;
  objectError.value = ''; newBranchOpen.value = false; newBranchName.value = ''; newBranchAddress.value = '';
  resetAddressSuggestions();
};
const toggle = (target: 'customer' | 'object') => { if (!busy.value) editTarget.value = editTarget.value === target ? null : target; };
const editCustomer = async () => {
  customerName.value = displayName.value; customerPhone.value = phone.value; customerEmail.value = email.value;
  customerError.value = ''; customerMode.value = 'edit';
  await nextTick(); customerNameField.value?.focus({ preventScroll: true });
};
const changeCustomer = () => { customerError.value = ''; customerMode.value = 'change'; };
const cancelCustomer = () => { customerError.value = ''; customerMode.value = 'summary'; searchedCustomer.value = null; editTarget.value = null; };
const copy = async (value: string, label: string) => {
  try { await navigator.clipboard.writeText(value); notify(label + ' скопирован', 'success'); }
  catch { notify('Не удалось скопировать ' + label.toLowerCase(), 'error'); }
};
const openCustomerProfile = async () => {
  const id = customer.value?.id, orderId = props.order.id;
  const returnTo = window.location.pathname + window.location.search;
  // Successful navigation intentionally unmounts this editor.
  if (!id || (props.beforeNavigate && !await props.beforeNavigate()) || props.order.id !== orderId) return;
  const query = new URLSearchParams({ customerId: String(id), returnTo });
  window.history.pushState({}, '', '/manager/customers/profile?' + query.toString());
  window.dispatchEvent(new PopStateEvent('popstate'));
};
const saveCustomer = async () => {
  const id = customer.value?.id;
  if (!id || busy.value || !customerName.value.trim()) return;
  const scope = epoch, orderId = props.order.id;
  const payload = { name: customerName.value.trim(),
    full_legal_name: customer.value?.type === 'company' ? customerName.value.trim() : undefined,
    phone: customerPhone.value.trim() || null, email: customerEmail.value.trim() || null };
  savingCustomer.value = true; customerError.value = '';
  try {
    if (!await prepare()) { if (current(scope, orderId)) customerError.value = props.saveError || 'Не удалось сохранить текущие изменения заказа.'; return; }
    if (!current(scope, orderId)) return;
    const updated = await api.patchManagerCustomer(id, payload);
    if (!current(scope, orderId)) return;
    emit('updated', { ...props.order, customer: { ...customer.value!,
      name: updated?.name || payload.name, phone: updated?.phone ?? payload.phone ?? '',
      email: updated?.email ?? payload.email,
      full_legal_name: updated?.full_legal_name ?? payload.full_legal_name ?? customer.value?.full_legal_name,
    } });
    customerMode.value = 'summary'; editTarget.value = null;
    notify('Данные клиента сохранены', 'success'); emit('reload', orderId);
  } catch (error) { if (current(scope, orderId)) customerError.value = 'Не удалось сохранить клиента: ' + getApiErrorMessage(error); }
  finally { if (current(scope, orderId)) savingCustomer.value = false; }
};
const assignCustomer = async () => {
  const chosen = searchedCustomer.value;
  if (!chosen || chosen.id === customer.value?.id || busy.value) return;
  const scope = epoch, orderId = props.order.id;
  assigningCustomer.value = true; customerError.value = '';
  try {
    if (!await prepare()) { if (current(scope, orderId)) customerError.value = props.saveError || 'Не удалось сохранить текущие изменения заказа.'; return; }
    if (!current(scope, orderId)) return;
    const updated = await api.patchManagerOrder(orderId, { customer_id: chosen.id, customer_branch_id: null });
    if (!current(scope, orderId)) return;
    customerBranchId.value = updated.customer_branch?.id ?? null;
    emit('updated', updated); customerMode.value = 'summary'; searchedCustomer.value = null; editTarget.value = null;
    notify('Клиент изменён', 'success');
  } catch (error) { if (current(scope, orderId)) customerError.value = 'Не удалось сменить клиента: ' + getApiErrorMessage(error); }
  finally { if (current(scope, orderId)) assigningCustomer.value = false; }
};
const loadBranches = async (id: number) => {
  const request = ++branchesRequest; branchesLoading.value = true; branchError.value = '';
  try { const response = await api.getManagerCustomerBranches(id); if (request === branchesRequest) branches.value = response.items || []; }
  catch { if (request === branchesRequest) branchError.value = 'Филиалы не загрузились. Адрес можно указать вручную.'; }
  finally { if (request === branchesRequest) branchesLoading.value = false; }
};
const selectBranch = (event: Event) => {
  const id = (event.target as HTMLSelectElement).value;
  draftBranchId.value = id ? Number(id) : null;
  const branch = branches.value.find(item => item.id === draftBranchId.value);
  if (branch) draftAddress.value = branch.delivery_address;
};
const createBranch = async () => {
  const id = customer.value?.id;
  if (!id || busy.value || !newBranchAddress.value.trim()) return;
  const scope = epoch, orderId = props.order.id; creatingBranch.value = true; objectError.value = '';
  try {
    const created = await api.createManagerCustomerBranch(id, { name: newBranchName.value.trim() || undefined,
      delivery_address: newBranchAddress.value.trim(), is_default: branches.value.length === 0 });
    if (!current(scope, orderId)) return;
    branches.value = [created, ...branches.value.filter(item => item.id !== created.id)];
    draftBranchId.value = created.id; draftAddress.value = created.delivery_address;
    newBranchOpen.value = false; newBranchName.value = ''; newBranchAddress.value = '';
    notify('Филиал создан. Сохраните объект, чтобы привязать его к заказу.', 'success');
  } catch (error) { if (current(scope, orderId)) objectError.value = 'Не удалось создать филиал: ' + getApiErrorMessage(error); }
  finally { if (current(scope, orderId)) creatingBranch.value = false; }
};
const saveObject = async () => {
  if (busy.value) return;
  const scope = epoch, orderId = props.order.id;
  const draft = { address: draftAddress.value.trim(), branchId: draftBranchId.value, comment: draftComment.value };
  savingObject.value = true; objectError.value = '';
  try {
    if (props.persistObject) {
      if (!await props.persistObject(draft)) {
        if (current(scope, orderId)) objectError.value = props.saveError || 'Не удалось сохранить объект. Попробуйте ещё раз.';
        return;
      }
    } else {
      if (!await prepare()) { if (current(scope, orderId)) objectError.value = props.saveError || 'Не удалось сохранить текущие изменения заказа.'; return; }
      if (!current(scope, orderId)) return;
      const updated = await api.patchManagerOrder(orderId, { customer_delivery_address: draft.address, customer_branch_id: draft.branchId, comment: draft.comment });
      if (!current(scope, orderId)) return;
      deliveryAddress.value = draft.address; customerBranchId.value = updated.customer_branch?.id ?? draft.branchId; comment.value = draft.comment;
      emit('updated', updated);
    }
    if (!current(scope, orderId)) return;
    resetObjectDraft(); editTarget.value = null; notify('Объект сохранён', 'success');
  } catch (error) { if (current(scope, orderId)) objectError.value = 'Не удалось сохранить объект: ' + getApiErrorMessage(error); }
  finally { if (current(scope, orderId)) savingObject.value = false; }
};
watch([deliveryAddress, customerBranchId, comment], (values, previous) => {
  if (savingObject.value) return;
  if (draftAddress.value === previous[0]) draftAddress.value = values[0];
  if (draftBranchId.value === previous[1]) draftBranchId.value = values[1];
  if (draftComment.value === previous[2]) draftComment.value = values[2];
});
watch([() => props.order.id, () => customer.value?.id], (values, previous) => {
  epoch += 1; branchesRequest += 1; branches.value = [];
  savingCustomer.value = false; assigningCustomer.value = false; savingObject.value = false; creatingBranch.value = false;
  customerMode.value = customer.value?.id ? 'summary' : 'change'; searchedCustomer.value = null; customerError.value = '';
  if (!previous.length || values[0] !== previous[0]) resetObjectDraft();
  else {
    // A corrected customer does not change the physical object's draft address.
    draftBranchId.value = props.order.customer_branch?.id ?? null;
    newBranchOpen.value = false; newBranchName.value = ''; newBranchAddress.value = '';
    resetAddressSuggestions();
  }
  if (customer.value?.id) void loadBranches(customer.value.id);
}, { immediate: true });
watch([() => customer.value?.id, () => props.order.customer_branch?.id], ([id, branchId], [previousId, previousBranchId]) => {
  if (id && id === previousId && branchId !== previousBranchId) void loadBranches(id);
});
onBeforeUnmount(() => { epoch += 1; branchesRequest += 1; });
const beforeClose = async () => {
  if (savingCustomer.value || assigningCustomer.value || savingObject.value || creatingBranch.value) return false;
  const customerDirty = customerMode.value === 'edit' && (
    customerName.value.trim() !== displayName.value.trim()
    || customerPhone.value.trim() !== phone.value || customerEmail.value.trim() !== email.value
  );
  const objectDirty = draftAddress.value !== deliveryAddress.value || draftBranchId.value !== customerBranchId.value || draftComment.value !== comment.value;
  if (!customerDirty && !objectDirty && !searchedCustomer.value && !newBranchAddress.value.trim() && !newBranchName.value.trim()) return true;
  const scope = epoch, orderId = props.order.id;
  const discard = await confirmDialog({ title: 'Закрыть без сохранения?', description: 'В клиенте или объекте остались несохранённые изменения.', confirmText: 'Закрыть без сохранения', variant: 'warning' });
  return discard && current(scope, orderId);
};
defineExpose({ beforeClose });
</script>

<template>
  <OrderWorkspaceContext :customer-name="displayName" :address="objectAddress" :total="total" :paid="paid" :balance="balance" :expanded="editTarget" :disabled="busy" @customer="toggle('customer')" @object="toggle('object')" @payments="emit('payments')">
    <template #customer>
      <fieldset :disabled="busy" class="min-w-0 space-y-3" data-testid="inline-customer-editor">
        <template v-if="customerMode === 'summary'">
          <div class="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-slate-600 dark:text-slate-300">
            <a v-if="validPhone" :href="'tel:' + phoneDigits">{{ phone }}</a><span v-else>Телефон не указан</span>
            <button v-if="validPhone" type="button" class="context-icon" aria-label="Скопировать телефон" title="Скопировать телефон" @click="copy(phone, 'Телефон')"><Copy :size="14" /></button>
            <a v-if="validEmail" :href="'mailto:' + email" class="break-all">{{ email }}</a>
          </div>
          <div class="flex flex-wrap gap-2">
            <button type="button" class="btn-mini-outline gap-1 text-xs" data-testid="change-customer" @click="changeCustomer"><ArrowLeftRight :size="14" /> Сменить клиента</button>
            <button type="button" class="context-icon" data-testid="edit-customer" aria-label="Редактировать данные клиента" title="Редактировать данные клиента" @click="editCustomer"><Pencil :size="16" /></button>
            <button type="button" class="context-icon" aria-label="Открыть полную карточку клиента" title="Открыть полную карточку клиента" data-order-usage="customer_open" @click="openCustomerProfile"><ExternalLink :size="16" /></button>
          </div>
        </template>
        <template v-else-if="customerMode === 'edit'">
          <label class="field-label">Имя или название<textarea ref="customerNameField" v-model="customerName" class="field-input mt-1 min-h-16 text-sm" rows="2" data-testid="customer-name" /></label>
          <label class="field-label">Телефон<input v-model="customerPhone" class="field-input mt-1 text-sm" inputmode="tel" data-testid="customer-phone" /></label>
          <label class="field-label">Email<input v-model="customerEmail" class="field-input mt-1 text-sm" type="email" data-testid="customer-email" /></label>
          <div class="flex flex-wrap justify-end gap-2"><button type="button" class="btn-mini-outline text-xs" @click="cancelCustomer">Отмена</button><button type="button" class="btn-mini text-xs" data-testid="save-customer" :disabled="!customerName.trim()" @click="saveCustomer">{{ savingCustomer ? 'Сохраняем…' : 'Сохранить' }}</button></div>
        </template>
        <template v-else>
          <p class="text-xs text-slate-500 dark:text-slate-400">Выберите другого клиента для этого заказа.</p>
          <CustomerSearchSelect v-model="searchedCustomer" result-test-id-prefix="assign-customer" :disabled="busy" />
          <div class="flex flex-wrap justify-end gap-2"><button type="button" class="btn-mini-outline text-xs" @click="cancelCustomer">Отмена</button><button type="button" class="btn-mini text-xs" data-testid="assign-customer" :disabled="!searchedCustomer || searchedCustomer.id === customer?.id" @click="assignCustomer">{{ assigningCustomer ? 'Меняем…' : 'Сменить клиента' }}</button></div>
        </template>
        <p v-if="customerError" class="text-xs text-red-700 dark:text-red-300" role="alert">{{ customerError }}</p>
      </fieldset>
    </template>
    <template #object>
      <fieldset :disabled="busy" class="min-w-0 space-y-3" data-testid="inline-object-editor">
        <label v-if="branches.length || draftBranchId" class="field-label">Филиал<select :value="draftBranchId ?? ''" class="field-input mt-1 text-sm" data-testid="customer-branch" :disabled="branchesLoading" @change="selectBranch"><option value="">Без филиала</option><option v-if="draftBranchId && !branches.some(item => item.id === draftBranchId)" :value="draftBranchId">{{ selectedBranch?.name || 'Текущий филиал' }}</option><option v-for="branch in branches" :key="branch.id" :value="branch.id">{{ branch.name || branch.delivery_address }}</option></select></label>
        <p v-if="branchError" class="text-xs text-slate-500 dark:text-slate-400">{{ branchError }}</p>
        <AddressSuggestInput v-model="draftAddress" label="Адрес объекта" :error="addressError" data-testid="object-address" />
        <div v-if="canSuggestAddress" class="space-y-2 text-xs">
          <button type="button" class="btn-mini-outline text-xs" data-testid="suggest-company-address" :disabled="addressLoading" @click="suggestAddress(displayName.trim())">{{ addressLoading ? 'Ищем адрес…' : 'Подобрать адрес по компании' }}</button>
          <p v-if="addressLookupError" class="text-red-700 dark:text-red-300">Не удалось найти адрес. Можно ввести его вручную.</p>
          <p v-else-if="addressSearched && !addressLoading && !addressCandidates.length" class="text-slate-500">Подсказок нет. Укажите адрес вручную.</p>
          <button v-for="candidate in addressCandidates" :key="candidate.value" type="button" :data-testid="'company-address-candidate-' + candidate.value" class="block w-full rounded-lg border border-slate-200 p-2 text-left dark:border-slate-700" @click="draftAddress = candidate.value; resetAddressSuggestions()">{{ candidate.value }}</button>
        </div>
        <div class="flex flex-wrap gap-2 text-xs">
          <a v-if="draftAddress" :href="buildYandexMapUrl(draftAddress)" target="_blank" rel="noopener" class="context-icon" aria-label="Открыть объект на карте" title="Открыть объект на карте"><MapPin :size="15" /></a>
          <button v-if="draftAddress" type="button" class="context-icon" aria-label="Скопировать адрес" title="Скопировать адрес" @click="copy(draftAddress, 'Адрес')"><Copy :size="15" /></button>
          <button v-if="customer?.id" type="button" class="btn-mini-outline text-xs" :aria-expanded="newBranchOpen" @click="newBranchOpen = !newBranchOpen">{{ newBranchOpen ? 'Закрыть новый филиал' : 'Новый филиал' }}</button>
        </div>
        <div v-if="newBranchOpen" class="space-y-2 rounded-lg border border-slate-200 p-2 dark:border-slate-700">
          <label class="field-label">Название филиала<input v-model="newBranchName" class="field-input mt-1 text-sm" /></label>
          <AddressSuggestInput v-model="newBranchAddress" label="Адрес филиала" />
          <button type="button" class="btn-mini-outline text-xs" :disabled="!newBranchAddress.trim()" @click="createBranch">{{ creatingBranch ? 'Создаём…' : 'Создать и выбрать' }}</button>
        </div>
        <label class="field-label">Комментарий к объекту<textarea v-model="draftComment" class="field-input mt-1 min-h-16 text-sm" rows="2" data-testid="object-comment" /><span v-if="commentError" class="text-xs text-red-700 dark:text-red-300">{{ commentError }}</span></label>
        <p v-if="order.contact_name || order.contact_phone" class="text-xs text-slate-500 dark:text-slate-400">Контакт на объекте: {{ [order.contact_name, order.contact_phone].filter(Boolean).join(' · ') }}</p>
        <p v-if="order.requested_date" class="text-xs text-slate-500 dark:text-slate-400">Пожелание по дате: {{ order.requested_date }}</p>
        <p v-if="objectError" class="text-xs text-red-700 dark:text-red-300" role="alert">{{ objectError }}</p>
        <div class="flex flex-wrap justify-end gap-2"><button type="button" class="btn-mini-outline text-xs" @click="resetObjectDraft(); editTarget = null">Отмена</button><button type="button" class="btn-mini text-xs" data-testid="save-object" @click="saveObject">{{ savingObject ? 'Сохраняем…' : 'Сохранить' }}</button></div>
      </fieldset>
    </template>
  </OrderWorkspaceContext>
</template>

<style scoped>
.context-icon { display: inline-flex; align-items: center; justify-content: center; min-width: 2rem; min-height: 2rem; border-radius: .5rem; color: rgb(100 116 139); }
.context-icon:hover { background: rgb(226 232 240); color: rgb(15 118 110); }
:global(.dark) .context-icon { color: rgb(148 163 184); }
:global(.dark) .context-icon:hover { background: rgb(30 41 59); color: rgb(94 234 212); }
</style>
