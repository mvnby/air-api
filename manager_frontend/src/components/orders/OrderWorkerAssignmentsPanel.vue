<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue';
import { HardHat, Loader2, Plus } from 'lucide-vue-next';
import PersonAvatar from '../common/PersonAvatar.vue';
import { orderWorkerAssignmentsApi as api, type CollectionUpdate, type ManagerInstallerWorkspace, type WorkerAssignment, type WorkerPerson } from '../../services/order-worker-assignments';
import { managerSession } from '../../services/manager-session';
import { managerStorefrontSelection } from '../../services/manager-storefront-selection';
import { MANAGER_CAPABILITY, hasManagerCapability } from '../../manager-capabilities';
import { getApiErrorMessage } from '../../utils/api-errors';
const props = defineProps<{ orderId: number; contextVersion?: string; workStages?: { id: number; name: string }[]; disabled?: boolean; beforeAction: () => Promise<boolean> }>();
const emit = defineEmits<{ busy: [value: boolean] }>();
const state = ref<ManagerInstallerWorkspace | null>(null), people = ref<WorkerPerson[]>([]), loading = ref(false), busy = ref(false), error = ref('');
const staffId = ref(''), stageId = ref(''), editingId = ref<number | null>(null), title = ref(''), instructions = ref(''), materialIds = ref<number[]>([]);
const editingVersion = ref<number | null>(null);
const recipient = ref(''), amount = ref(''), currency = ref<'BYN' | 'USD' | 'EUR'>('BYN');
const canEdit = computed(() => Boolean(managerSession.auth.value?.staff_user_id && hasManagerCapability(managerSession.auth.value, MANAGER_CAPABILITY.crmManage) && !managerSession.auth.value?.demo_read_only));
const blocked = computed(() => !canEdit.value || props.disabled || busy.value || loading.value);
const assignments = computed(() => state.value?.assignments.filter(item => item.is_active && !item.revoked_at) ?? []);
const scope = computed(() => `${props.orderId}:${managerSession.auth.value?.staff_user_id}:${managerStorefrontSelection.selectedTenantId.value}:${managerStorefrontSelection.selectedSlug.value}`);
let generation = 0;
let refreshRequested = false;
let activeScope = scope.value;
const collectionFields = (result: ManagerInstallerWorkspace) => ({
  recipient: result.collection.assignment_id === null ? '' : String(result.collection.assignment_id),
  amount: result.collection.amount ?? '',
  currency: result.collection.currency ?? 'BYN',
});
let collectionReview: (ReturnType<typeof collectionFields> & { version: number; fingerprint: string }) | null = null;
const collectionDirty = () => Boolean(collectionReview && (
  recipient.value !== collectionReview.recipient
  || amount.value.trim().replace(',', '.') !== collectionReview.amount
  || currency.value !== collectionReview.currency
));
const apply = (result: ManagerInstallerWorkspace, preserveDraft = false, reviewedConflict = false) => {
  const keepCollection = preserveDraft && (reviewedConflict || collectionDirty());
  state.value = result;
  if (!preserveDraft) { editingId.value = null; editingVersion.value = null; }
  else if (reviewedConflict && editingId.value !== null) editingVersion.value = result.assignments.find(item => item.id === editingId.value)?.version ?? null;
  const fields = collectionFields(result);
  if (!keepCollection) { recipient.value = fields.recipient; amount.value = fields.amount; currency.value = fields.currency; }
  // A retained draft must keep the versions reviewed with it until an explicit conflict review.
  if (!keepCollection || reviewedConflict) collectionReview = { ...fields, version: result.collection.version, fingerprint: result.financial_fingerprint };
};
const load = async (preserveDraft = false) => {
  const requested = ++generation; loading.value = true; if (!preserveDraft) error.value = '';
  try {
    const result = await api.get(props.orderId); if (requested !== generation) return; apply(result, preserveDraft);
    const first = await api.candidates(1), candidates = [...first.items];
    for (let page = 2; candidates.length < first.total; page++) { if (requested !== generation) return; const next = await api.candidates(page); if (!next.items.length) break; candidates.push(...next.items); }
    if (requested === generation) people.value = candidates;
  } catch (cause) { if (requested === generation) error.value = getApiErrorMessage(cause); }
  finally { if (requested === generation) { loading.value = false; refreshContext(); } }
};
const refreshContext = () => {
  if (scope.value !== activeScope || !refreshRequested || busy.value || loading.value) return;
  refreshRequested = false;
  void load(true);
};
watch([scope, () => props.contextVersion], ([nextScope], previous) => {
  if (nextScope !== previous?.[0]) {
    activeScope = nextScope; refreshRequested = false; ++generation; state.value = null; people.value = []; staffId.value = ''; stageId.value = ''; editingId.value = null; editingVersion.value = null; collectionReview = null; busy.value = false; emit('busy', false); void load();
  } else {
    refreshRequested = true;
    refreshContext();
  }
}, { immediate: true });
onScopeDispose(() => { refreshRequested = false; ++generation; emit('busy', false); });
const run = async (operation: () => PromiseLike<ManagerInstallerWorkspace>) => {
  if (blocked.value) return false;
  const requested = generation, orderId = props.orderId; busy.value = true; emit('busy', true); error.value = '';
  const current = () => requested === generation && props.orderId === orderId;
  try {
    // Read versions/payloads before this barrier; an intervening change must conflict, never silently replay.
    if (!await props.beforeAction() || !current() || props.disabled || !canEdit.value) return false;
    const result = await operation(); if (!current()) return false; apply(result); return true;
  } catch (cause) {
    if (!current()) return false;
    if ((cause as { status?: number })?.status === 409) {
      try { const fresh = await api.get(orderId); if (current()) { apply(fresh, true, true); error.value = 'Данные работы или оплаты изменились. Проверьте актуальные данные и сохраните заново.'; } }
      catch (refreshError) { if (current()) error.value = getApiErrorMessage(refreshError); }
    } else error.value = getApiErrorMessage(cause);
    return false;
  } finally { if (current()) { busy.value = false; emit('busy', false); refreshContext(); } }
};
const assign = async () => { const person = Number(staffId.value), stage = stageId.value ? Number(stageId.value) : null, orderId = props.orderId; if (!people.value.some(item => item.staff_user_id === person)) return; if (await run(() => api.assign(orderId, person, stage))) staffId.value = ''; };
const edit = (item: WorkerAssignment) => { editingId.value = item.id; editingVersion.value = item.version; title.value = item.title; instructions.value = item.instructions; materialIds.value = [...item.material_link_ids]; };
const publish = () => { const item = assignments.value.find(item => item.id === editingId.value); if (!item || editingVersion.value === null || !title.value.trim()) return; const orderId = props.orderId, id = item.id, body = { expected_version: editingVersion.value, title: title.value.trim(), instructions: instructions.value, material_link_ids: [...materialIds.value] }; void run(() => api.publish(orderId, id, body)); };
const revoke = (item: WorkerAssignment) => { const orderId = props.orderId, id = item.id, version = item.version; void run(() => api.revoke(orderId, id, version)); };
const saveCollection = () => {
  if (!state.value || !collectionReview) return; const assignmentId = recipient.value ? Number(recipient.value) : null;
  const normalized = amount.value.trim().replace(',', '.');
  if (assignmentId !== null && (!/^\d{1,12}(?:\.\d{1,2})?$/.test(normalized) || !assignments.value.some(item => item.id === assignmentId))) { error.value = 'Укажите получателя и неотрицательную сумму с точностью до копеек.'; return; }
  const orderId = props.orderId, body: CollectionUpdate = { expected_version: collectionReview.version, assignment_id: assignmentId, amount: assignmentId === null ? null : normalized, currency: assignmentId === null ? null : currency.value, financial_fingerprint: collectionReview.fingerprint };
  void run(() => api.collection(orderId, body));
};
</script>
<template>
  <section class="mt-4 space-y-4 rounded-xl border border-gray-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900" aria-label="Работы исполнителей">
    <header><h2 class="flex items-center gap-2 font-semibold"><HardHat class="h-5 w-5 text-gray-400" aria-hidden="true" />Работы исполнителей</h2><p class="mt-1 text-xs text-gray-500">Личные назначения и указания, которые сотрудник увидит в «Моих работах».</p></header>
    <p v-if="loading" class="flex items-center gap-2 text-sm text-gray-500" role="status"><Loader2 class="h-4 w-4 animate-spin" aria-hidden="true" />Загрузка назначений…</p>
    <p v-if="error" role="alert" class="text-sm text-red-700">{{ error }} <button v-if="!state" type="button" class="underline" @click="load(Boolean(state))">Повторить</button></p>
    <template v-if="state">
      <p v-if="!assignments.length" class="text-sm text-gray-500">Работы пока никому не назначены.</p>
      <article v-for="item in assignments" :key="item.id" class="rounded-lg border border-gray-200 p-3 dark:border-slate-700">
        <div class="flex items-start justify-between gap-3"><div class="flex min-w-0 items-center gap-2"><PersonAvatar :name="item.display_name" :src="people.find(person => person.staff_user_id === item.staff_user_id)?.avatar_url" size="sm" /><div><p class="text-sm font-semibold">{{ item.display_name }}</p><p class="text-xs text-gray-500">{{ item.work_stage_id ? workStages?.find(stage => stage.id === item.work_stage_id)?.name || 'Выезд' : 'Весь заказ' }}</p></div></div><button type="button" class="min-h-9 px-2 text-xs text-red-600 disabled:opacity-40" :disabled="blocked" @click="revoke(item)">Отозвать</button></div>
        <p class="mt-3 text-sm font-medium">{{ item.title }}</p><p v-if="item.instructions" class="mt-1 whitespace-pre-wrap text-xs text-gray-500">{{ item.instructions }}</p>
        <button v-if="editingId !== item.id" type="button" class="mt-2 min-h-9 text-xs font-medium text-brand-600 disabled:opacity-40" :disabled="blocked" @click="edit(item)">Указания и материалы</button>
        <form v-else class="mt-3 space-y-3" @submit.prevent="publish"><label class="block text-xs font-medium">Название работы<input v-model="title" aria-label="Название работы" maxlength="160" required class="mt-1 w-full rounded-lg border bg-transparent p-2 text-sm" :disabled="blocked" /></label><label class="block text-xs font-medium">Указания исполнителю<textarea v-model="instructions" aria-label="Указания исполнителю" maxlength="8000" rows="3" class="mt-1 w-full rounded-lg border bg-transparent p-2 text-sm" :disabled="blocked" /></label><fieldset v-if="state.materials.length" :disabled="blocked"><legend class="mb-2 text-xs font-medium">Разрешённые материалы</legend><label v-for="material in state.materials.filter(material => item.work_stage_id === null || material.work_stage_id === null || material.work_stage_id === item.work_stage_id)" :key="material.link_id" class="flex min-h-9 items-center gap-2 text-xs"><input v-model="materialIds" type="checkbox" :value="material.link_id" />{{ material.label }}</label><p class="mt-1 text-xs text-gray-500">Исполнитель увидит только выбранные технические материалы.</p></fieldset><div class="flex gap-3"><button type="submit" class="min-h-9 rounded-lg bg-brand-600 px-3 text-xs font-semibold text-white disabled:opacity-40" :disabled="blocked || !title.trim()">Сохранить указания</button><button type="button" class="min-h-9 text-xs text-gray-500" :disabled="busy" @click="editingId = null">Отмена</button></div></form>
      </article>
      <form class="grid gap-3 sm:grid-cols-2" @submit.prevent="assign"><label class="text-xs font-medium">Исполнитель<select v-model="staffId" aria-label="Исполнитель работы" class="mt-1 min-h-10 w-full rounded-lg border bg-transparent p-2 text-sm" :disabled="blocked"><option value="">Выберите сотрудника</option><option v-for="person in people" :key="person.staff_user_id" :value="String(person.staff_user_id)">{{ person.display_name }}</option></select></label><label class="text-xs font-medium">Работа<select v-model="stageId" aria-label="Выезд или весь заказ" class="mt-1 min-h-10 w-full rounded-lg border bg-transparent p-2 text-sm" :disabled="blocked"><option value="">Весь заказ</option><option v-for="stage in workStages" :key="stage.id" :value="String(stage.id)">{{ stage.name }}</option></select></label><button type="submit" class="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border px-3 text-sm font-medium disabled:opacity-40 sm:col-span-2" :disabled="blocked || !staffId"><Plus class="h-4 w-4" aria-hidden="true" />Назначить работу</button></form>
      <form class="space-y-3 border-t border-gray-100 pt-4 dark:border-slate-700" @submit.prevent="saveCollection"><h3 class="text-sm font-semibold">Поручение получить оплату</h3><p v-if="state.collection.status === 'requires_review'" role="status" class="text-xs text-amber-700">Состав или оплата заказа изменились. Проверьте сумму и подтвердите поручение заново.</p><label class="block text-xs font-medium">Кому поручено<select v-model="recipient" aria-label="Получатель оплаты" class="mt-1 min-h-10 w-full rounded-lg border bg-transparent p-2 text-sm" :disabled="blocked"><option value="">Никому</option><option v-for="item in assignments" :key="item.id" :value="String(item.id)">{{ item.display_name }} · {{ item.work_stage_id ? workStages?.find(stage => stage.id === item.work_stage_id)?.name || 'Выезд' : 'Весь заказ' }}</option></select></label><div v-if="recipient" class="grid grid-cols-[1fr_6rem] gap-3"><label class="text-xs font-medium">Сумма<input v-model="amount" aria-label="Сумма к получению" inputmode="decimal" autocomplete="off" class="mt-1 min-h-10 w-full rounded-lg border bg-transparent p-2 text-sm" :disabled="blocked" /></label><label class="text-xs font-medium">Валюта<select v-model="currency" aria-label="Валюта к получению" class="mt-1 min-h-10 w-full rounded-lg border bg-transparent p-2 text-sm" :disabled="blocked"><option>BYN</option><option>USD</option><option>EUR</option></select></label></div><p v-if="state.balances.length" class="text-xs text-gray-500">Остаток по заказу: {{ state.balances.map(balance => `${balance.remaining_amount} ${balance.currency}`).join(' · ') }}. Сумму поручения укажите отдельно.</p><button type="submit" class="min-h-10 rounded-lg bg-brand-600 px-4 text-sm font-medium text-white disabled:opacity-40" :disabled="blocked">{{ busy ? 'Сохраняем…' : recipient ? 'Сохранить поручение' : 'Снять поручение' }}</button></form>
    </template>
  </section>
</template>
