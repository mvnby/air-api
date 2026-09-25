<script setup lang="ts">
import { computed, nextTick, onScopeDispose, ref, watch } from 'vue';
import {
  ManagerInstallationEstimatesService, ManagerOrdersService,
  type InstallationInput, type InstallationPreviewPayload,
  type ManagerInstallationConfirmResponse, type ManagerInstallationPreviewResponse,
  type OrderProductLineResponse, type TypedInstallationProfile_Input,
} from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
import { managerSession } from '../../services/manager-session';
import { formatMoney } from './order-utils';

type Mode = 'collapsed' | 'detailed';
type Source = 'proposal' | 'manual';
type Work = { route: number | null; diamond: number | null; pumpSupply: boolean; pumpInstall: boolean; chase: number };
type Slot = { key: string; label: string; productId: number };
type StoredIntent = {
  fingerprint: string;
  previewKey: string;
  confirmKey: string;
  attachKey: string;
  preview?: ManagerInstallationPreviewResponse;
  confirmed?: ManagerInstallationConfirmResponse;
  attachRetryRequired?: boolean;
};
type StoredDraft = {
  source: Source;
  selected: string[];
  work: Record<string, Work>;
  manualKey: string;
  manualProfile: TypedInstallationProfile_Input;
  scaffold: boolean;
  lift: boolean;
  mode: Mode;
  intent?: StoredIntent;
};

const props = defineProps<{
  orderId: number;
  proposalId: number;
  beforeAction: () => Promise<boolean>;
  beginAttach: (orderId: number, proposalId: number, scopeKey: string, token: string) => Promise<boolean>;
  afterAttach: (orderId: number, proposalId: number, scopeKey: string, token: string) => Promise<boolean>;
  endAttach: (token: string) => void;
}>();
const open = ref(false);
const busy = ref(false);
const error = ref('');
const notice = ref('');
const products = ref<OrderProductLineResponse[]>([]);
const source = ref<Source>('proposal');
const selected = ref<string[]>([]);
const work = ref<Record<string, Work>>({});
const manualKey = ref<string>(crypto.randomUUID());
const manualProfile = ref<TypedInstallationProfile_Input>({ product_kind: '', confirmed: false });
const scaffold = ref(false);
const lift = ref(false);
const mode = ref<Mode>('collapsed');
const intent = ref<StoredIntent | null>(null);
const consent = ref(false);

const storageKey = computed(() => {
  const auth = managerSession.auth.value;
  const identity = auth ? `${auth.tenant_id}:${auth.staff_user_id || auth.username}` : 'anonymous';
  return `manager.installation-order:${identity}:${props.orderId}:${props.proposalId}`;
});
type ActionScope = {
  key: string;
  epoch: number;
  orderId: number;
  proposalId: number;
  beforeAction: () => Promise<boolean>;
  beginAttach: (orderId: number, proposalId: number, scopeKey: string, token: string) => Promise<boolean>;
  afterAttach: (orderId: number, proposalId: number, scopeKey: string, token: string) => Promise<boolean>;
  endAttach: (token: string) => void;
};
let epoch = 0;
let disposed = false;
const capture = (): ActionScope => ({
  key: storageKey.value, epoch, orderId: props.orderId, proposalId: props.proposalId,
  beforeAction: props.beforeAction, beginAttach: props.beginAttach,
  afterAttach: props.afterAttach, endAttach: props.endAttach,
});
const current = (scope: ActionScope) => !disposed && scope.epoch === epoch
  && scope.key === storageKey.value && scope.orderId === props.orderId && scope.proposalId === props.proposalId;
onScopeDispose(() => { disposed = true; epoch += 1; });
const makeWork = (): Work => ({ route: null, diamond: null, pumpSupply: false, pumpInstall: false, chase: 0 });
const slots = computed<Slot[]>(() => products.value
  .filter((line) => line.proposal_id === props.proposalId && line.product_id && line.quantity > 0 && line.price > 0 && !line.is_installation_included)
  .flatMap((line) => Array.from({ length: Math.min(line.quantity, 20) }, (_, index) => ({
    key: `p:${props.proposalId}:${line.id}:${index + 1}`,
    label: `${line.product_title} · шт. ${index + 1}`,
    productId: Number(line.product_id),
  }))));
const activeKeys = computed(() => source.value === 'manual' ? [manualKey.value] : selected.value);
const preview = computed(() => {
  if (!intent.value?.preview) return null;
  try { return JSON.stringify(payload()) === intent.value.fingerprint ? intent.value.preview : null; }
  catch { return null; }
});
const confirmed = computed(() => intent.value?.confirmed ?? null);
const attachRetryRequired = computed(() => Boolean(intent.value?.attachRetryRequired));
const projectedLines = computed(() => mode.value === 'collapsed' ? preview.value?.collapsed_lines : preview.value?.detailed_lines);
const statusText = computed(() => {
  if (!preview.value) return '';
  if (preview.value.reason_code === 'price_book_not_published') return 'Книга цен ещё не опубликована. Опубликуйте тарифы монтажа перед расчётом.';
  if (preview.value.status === 'from') return 'Цена указана «от» и не может быть подтверждена как точная смета.';
  if (preview.value.status === 'quote') return 'Для этого состава нужна индивидуальная смета.';
  if (preview.value.status === 'unavailable') return 'По выбранному оборудованию нет доступного тарифа.';
  return '';
});
const readableError = (failure: unknown): string => {
  const detail = (failure as { body?: { detail?: { code?: string } } })?.body?.detail;
  const messages: Record<string, string> = {
    preview_expired: 'Срок расчёта истёк. Рассчитайте смету заново.',
    preview_not_found: 'Расчёт не найден. Рассчитайте смету заново.',
    installation_already_attached: 'Монтаж для этого оборудования уже прикреплён к предложению.',
    equipment_not_in_proposal: 'Оборудование изменилось или уже не подходит для отдельного монтажа. Проверьте предложение.',
    proposal_not_editable: 'Редакция предложения закрыта. Создайте новый черновик предложения.',
    estimate_already_attached: 'Смета уже прикреплена в другом виде. Обновите заказ.',
    idempotency_key_reused: 'Данные расчёта изменились. Запустите новый расчёт.',
  };
  return (detail?.code && messages[detail.code]) || getApiErrorMessage(failure);
};

const save = (scope?: ActionScope) => {
  if (scope && !current(scope)) return;
  try {
    const draft: StoredDraft = {
      source: source.value, selected: selected.value, work: work.value,
      manualKey: manualKey.value, manualProfile: manualProfile.value,
      scaffold: scaffold.value, lift: lift.value, mode: mode.value,
      intent: intent.value ?? undefined,
    };
    sessionStorage.setItem(scope?.key ?? storageKey.value, JSON.stringify(draft));
  } catch { /* Restricted storage must not block the estimate. */ }
};
const restore = () => {
  try {
    const raw = sessionStorage.getItem(storageKey.value);
    if (!raw) return;
    const draft = JSON.parse(raw) as StoredDraft;
    source.value = draft.source === 'manual' ? 'manual' : 'proposal';
    selected.value = Array.isArray(draft.selected) ? draft.selected : [];
    work.value = draft.work || {};
    manualKey.value = draft.manualKey || crypto.randomUUID();
    manualProfile.value = draft.manualProfile || { product_kind: '', confirmed: false };
    scaffold.value = Boolean(draft.scaffold);
    lift.value = Boolean(draft.lift);
    mode.value = draft.mode === 'detailed' ? 'detailed' : 'collapsed';
    intent.value = draft.intent || null;
  } catch { /* A stale browser draft can be discarded. */ }
};
const reset = () => {
  busy.value = false;
  open.value = false;
  products.value = [];
  source.value = 'proposal';
  selected.value = [];
  work.value = {};
  manualKey.value = crypto.randomUUID();
  manualProfile.value = { product_kind: '', confirmed: false };
  scaffold.value = false;
  lift.value = false;
  mode.value = 'collapsed';
  intent.value = null;
  consent.value = false;
  error.value = '';
  notice.value = '';
  restore();
};
watch(storageKey, () => { epoch += 1; reset(); }, { immediate: true, flush: 'sync' });
watch([source, selected, work, manualKey, manualProfile, scaffold, lift, mode, intent], () => save(), { deep: true });
watch([source, selected, work, manualProfile, scaffold, lift], () => { consent.value = false; }, { deep: true });

const workFor = (key: string): Work => {
  if (!work.value[key]) work.value[key] = makeWork();
  return work.value[key];
};
const toggleSlot = (key: string) => {
  selected.value = selected.value.includes(key)
    ? selected.value.filter((item) => item !== key)
    : [...selected.value, key];
};
const loadProducts = async (scope: ActionScope): Promise<boolean> => {
  const order = await ManagerOrdersService.getManagerOrderDetail(scope.orderId);
  if (!current(scope)) return false;
  const proposal = (order.proposals || []).find((item) => item.id === scope.proposalId && !item.is_archived);
  if (!proposal || proposal.status !== 'draft') throw new Error('Выберите активный черновик предложения.');
  products.value = proposal.product_lines || [];
  selected.value = selected.value.filter((key) => slots.value.some((slot) => slot.key === key));
  return true;
};
const show = async () => {
  if (busy.value) return;
  if (open.value) { open.value = false; return; }
  const scope = capture();
  busy.value = true;
  error.value = '';
  try {
    const saved = await scope.beforeAction();
    if (!current(scope)) return;
    if (!saved) throw new Error('Сначала сохраните изменения заказа.');
    if (!await loadProducts(scope) || !current(scope)) return;
    open.value = true;
  } catch (failure) { if (current(scope)) error.value = readableError(failure); }
  finally { if (current(scope)) busy.value = false; }
};
const payload = (): InstallationPreviewPayload => {
  if (!activeKeys.value.length) throw new Error('Выберите оборудование или укажите параметры установки без товара.');
  if (activeKeys.value.length > 20) throw new Error('За один расчёт можно добавить не более 20 установок.');
  const installations: InstallationInput[] = activeKeys.value.map((key, index) => {
    const item = workFor(key);
    if (item.route == null || item.diamond == null || String(item.route).trim() === '' || String(item.diamond).trim() === ''
      || !Number.isFinite(Number(item.route)) || !Number.isInteger(Number(item.diamond))
      || Number(item.route) < 0 || Number(item.route) > 1000 || Number(item.diamond) < 0 || Number(item.diamond) > 100) {
      throw new Error('Для каждой установки укажите длину трассы и количество алмазных отверстий, даже если это 0.');
    }
    if (!Number.isFinite(Number(item.chase)) || Number(item.chase) < 0 || Number(item.chase) > 1000) {
      throw new Error('Укажите допустимую длину штробления.');
    }
    const extras = [];
    if (item.pumpSupply) extras.push({ code: 'pump.supply', quantity: 1 });
    if (item.pumpInstall) extras.push({ code: 'pump.install', quantity: 1 });
    if (Number(item.chase) > 0) extras.push({ code: 'chase.extra_m', quantity: Number(item.chase) });
    const base = { key, display_label: `№${index + 1}`, route_length_m: Number(item.route),
      holes_by_type: { diamond: Number(item.diamond) }, extras };
    if (source.value === 'manual') {
      if (!manualProfile.value.confirmed) throw new Error('Подтвердите параметры оборудования для установки без товара.');
      if (!manualProfile.value.product_kind) throw new Error('Укажите вид оборудования.');
      const typedProfile = Object.fromEntries(Object.entries(manualProfile.value)
        .filter(([, value]) => value !== '' && value !== null && value !== undefined)) as TypedInstallationProfile_Input;
      return { ...base, typed_profile: typedProfile };
    }
    const slot = slots.value.find((candidate) => candidate.key === key);
    if (!slot) throw new Error('Оборудование изменилось. Обновите предложение и повторите расчёт.');
    return { ...base, product_id: slot.productId };
  });
  return { installations, site_extras: [
    ...(scaffold.value ? [{ code: 'access.scaffold', quantity: 1 }] : []),
    ...(lift.value ? [{ code: 'access.lift', quantity: 1 }] : []),
  ] };
};
const ensureIntent = (fingerprint: string): StoredIntent => {
  if (intent.value?.fingerprint !== fingerprint) {
    intent.value = { fingerprint, previewKey: crypto.randomUUID(), confirmKey: crypto.randomUUID(), attachKey: crypto.randomUUID() };
  }
  return intent.value;
};
const calculate = async () => {
  if (busy.value) return;
  const scope = capture();
  busy.value = true;
  error.value = '';
  notice.value = '';
  consent.value = false;
  try {
    const saved = await scope.beforeAction();
    if (!current(scope)) return;
    if (!saved) throw new Error('Сначала сохраните изменения заказа.');
    if (!await loadProducts(scope) || !current(scope)) return;
    const input = payload();
    const fingerprint = JSON.stringify(input);
    if (intent.value?.fingerprint === fingerprint && intent.value.preview) intent.value = null;
    const attempt = ensureIntent(fingerprint);
    save(scope);
    // One key per immutable payload; a retry or page reload reuses that key.
    const result = await ManagerInstallationEstimatesService.previewManagerInstallationEstimate(attempt.previewKey, input);
    if (!current(scope) || intent.value !== attempt) return;
    attempt.preview = result;
    attempt.confirmed = undefined;
    save(scope);
  } catch (failure) { if (current(scope)) error.value = readableError(failure); }
  finally { if (current(scope)) busy.value = false; }
};
const confirm = async () => {
  if (busy.value || !preview.value?.preview_ref || !consent.value || !intent.value) return;
  const scope = capture();
  busy.value = true;
  error.value = '';
  try {
    const saved = await scope.beforeAction();
    if (!current(scope)) return;
    if (!saved) throw new Error('Сначала сохраните изменения заказа.');
    if (!await loadProducts(scope) || !current(scope)) return;
    const input = payload();
    const attempt = intent.value;
    const previewRef = preview.value?.preview_ref;
    if (!attempt || !previewRef || JSON.stringify(input) !== attempt.fingerprint) throw new Error('Состав изменился. Рассчитайте смету заново.');
    const result = await ManagerInstallationEstimatesService.confirmManagerInstallationEstimate(attempt.confirmKey, {
      preview_ref: previewRef,
      order_id: scope.orderId, proposal_id: scope.proposalId,
      verified_service_only_keys: source.value === 'manual' ? [manualKey.value] : [],
    });
    if (!current(scope) || intent.value !== attempt) return;
    attempt.confirmed = result;
    consent.value = false;
    save(scope);
  } catch (failure) {
    if (!current(scope)) return;
    const detail = (failure as { body?: { detail?: { code?: string; fresh_preview?: ManagerInstallationPreviewResponse } } })?.body?.detail;
    if (detail?.code === 'price_changed') {
      intent.value = null;
      error.value = 'Книга цен изменилась. Проверьте новый расчёт и подтвердите его заново.';
      // The fresh result is informational; a new preview creates a new attempt.
      notice.value = detail.fresh_preview?.total ? `Новая сумма: ${formatMoney(Number(detail.fresh_preview.total))}.` : '';
      save(scope);
    } else {
      if (detail?.code === 'preview_expired' || detail?.code === 'preview_not_found') intent.value = null;
      error.value = readableError(failure);
    }
  } finally { if (current(scope)) busy.value = false; }
};
const attach = async () => {
  if (busy.value || !confirmed.value || !intent.value) return;
  const scope = capture();
  const attempt = intent.value;
  const accepted = confirmed.value;
  const projection = mode.value;
  const token = crypto.randomUUID();
  busy.value = true;
  error.value = '';
  notice.value = '';
  try {
    const ready = await scope.beginAttach(scope.orderId, scope.proposalId, scope.key, token);
    if (!current(scope) || intent.value !== attempt) return;
    if (!ready) throw new Error('Сначала сохраните изменения заказа.');
    attempt.attachRetryRequired = true;
    save(scope);
    const result = await ManagerInstallationEstimatesService.attachManagerInstallationEstimate(
      accepted.estimate_id, scope.orderId, scope.proposalId, attempt.attachKey,
      { revision: accepted.revision, mode: projection },
    );
    if (!current(scope) || intent.value !== attempt) return;
    const refreshed = await scope.afterAttach(scope.orderId, scope.proposalId, scope.key, token);
    if (!current(scope) || intent.value !== attempt) return;
    if (!refreshed) throw new Error('Не удалось обновить заказ. Повторите прикрепление с тем же ключом.');
    sessionStorage.removeItem(scope.key);
    reset();
    await nextTick();
    if (!current(scope)) return;
    sessionStorage.removeItem(scope.key);
    notice.value = `Смета прикреплена к предложению: ${result.lines.length} строк, ${formatMoney(Number(result.total))}.`;
  } catch (failure) {
    if (!current(scope)) return;
    const code = (failure as { body?: { detail?: { code?: string } } })?.body?.detail?.code;
    if (['equipment_not_in_proposal', 'installation_already_attached', 'proposal_not_editable'].includes(code || '')) {
      attempt.attachRetryRequired = false;
      save(scope);
    }
    error.value = readableError(failure);
    if (attempt.attachRetryRequired) notice.value = 'Если ответ не дошёл, повторите прикрепление: будет использован тот же ключ.';
  } finally {
    scope.endAttach(token);
    if (current(scope)) busy.value = false;
  }
};
const startNew = () => {
  if (busy.value || attachRetryRequired.value) return;
  intent.value = null;
  consent.value = false;
  mode.value = 'collapsed';
  error.value = '';
  notice.value = 'Измените параметры и рассчитайте новую смету. Уже прикреплённые строки сохранятся.';
  save();
};
</script>

<template>
  <div class="mt-3">
    <button type="button" data-testid="installation-open" class="btn-mini-outline w-full justify-center" :disabled="busy" @click="show">{{ open ? 'Скрыть монтаж по книге' : 'Монтаж по книге цен' }}</button>
    <p v-if="error && !open" role="alert" class="mt-2 text-sm text-red-700">{{ error }}</p>
    <p v-if="notice && !open" role="status" class="mt-2 text-sm text-emerald-700">{{ notice }}</p>
    <div v-if="open" class="mt-3 space-y-4 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm">
      <p class="text-slate-600">Расчёт относится к текущему черновику предложения. Строки и суммы берутся из опубликованной книги цен.</p>
      <div class="flex gap-2">
        <button type="button" class="btn-mini-outline" :class="source === 'proposal' ? 'border-brand-500 bg-brand-50 text-brand-700' : ''" :disabled="busy || Boolean(confirmed)" @click="source = 'proposal'">Товар в предложении</button>
        <button type="button" class="btn-mini-outline" :class="source === 'manual' ? 'border-brand-500 bg-brand-50 text-brand-700' : ''" :disabled="busy || Boolean(confirmed)" @click="source = 'manual'">Без товара</button>
      </div>
      <div v-if="source === 'proposal'" class="space-y-2">
        <p v-if="!slots.length" class="text-amber-800">Нет оплачиваемого оборудования без включённого монтажа. Сохраните товар в предложении или выберите установку без товара.</p>
        <label v-for="slot in slots" :key="slot.key" class="flex items-center gap-2"><input data-testid="installation-product" type="checkbox" :checked="selected.includes(slot.key)" :disabled="busy || Boolean(confirmed)" @change="toggleSlot(slot.key)" />{{ slot.label }}</label>
      </div>
      <div v-else class="grid gap-2 sm:grid-cols-2">
        <label class="space-y-1">Вид оборудования<select v-model="manualProfile.product_kind" class="field-input" :disabled="busy || Boolean(confirmed)"><option value="">Выберите</option><option value="complete_split_system">Комплект сплит-системы</option><option value="indoor_unit">Отдельный внутренний блок</option><option value="outdoor_unit">Отдельный наружный блок</option><option value="other">Другое</option></select></label>
        <label class="space-y-1">Тип внутреннего блока<select v-model="manualProfile.indoor_type" class="field-input" :disabled="busy || Boolean(confirmed)"><option :value="undefined">Выберите</option><option value="wall">Настенный</option><option value="cassette">Кассетный</option><option value="duct">Канальный</option><option value="floor_ceiling">Напольно-потолочный</option><option value="column">Колонный</option><option value="console">Консольный</option></select></label>
        <label class="space-y-1">Холодопроизводительность, кВт<input v-model.number="manualProfile.capacity_cooling_kw" type="number" min="0.001" step="0.001" class="field-input" :disabled="busy || Boolean(confirmed)" /></label>
        <label class="space-y-1">Жидкостная труба<input v-model="manualProfile.pipe_liquid" class="field-input" placeholder="Например 1/4&quot;" :disabled="busy || Boolean(confirmed)" /></label>
        <label class="space-y-1">Газовая труба<input v-model="manualProfile.pipe_gas" class="field-input" placeholder="Например 3/8&quot;" :disabled="busy || Boolean(confirmed)" /></label>
        <label class="space-y-1">Вес внутреннего блока, кг<input v-model.number="manualProfile.weight_indoor" type="number" min="0.01" step="0.01" class="field-input" :disabled="busy || Boolean(confirmed)" /></label>
        <label class="space-y-1">Вес наружного блока, кг<input v-model.number="manualProfile.weight_outdoor" type="number" min="0.01" step="0.01" class="field-input" :disabled="busy || Boolean(confirmed)" /></label>
        <label class="space-y-1">Вес упаковки внутреннего блока, кг<input v-model.number="manualProfile.weight_indoor_package" type="number" min="0.01" step="0.01" class="field-input" :disabled="busy || Boolean(confirmed)" /></label>
        <label class="space-y-1">Вес упаковки наружного блока, кг<input v-model.number="manualProfile.weight_outdoor_package" type="number" min="0.01" step="0.01" class="field-input" :disabled="busy || Boolean(confirmed)" /></label>
        <label class="flex items-center gap-2 sm:col-span-2"><input v-model="manualProfile.confirmed" type="checkbox" :disabled="busy || Boolean(confirmed)" />Параметры оборудования проверены; установка выполняется без продажи товара в этом предложении</label>
      </div>
      <div v-for="(key, index) in activeKeys" :key="key" class="space-y-2 border-t border-slate-200 pt-3">
        <p class="font-medium">Установка №{{ index + 1 }} · {{ source === 'manual' ? 'без товара' : slots.find((slot) => slot.key === key)?.label }}</p>
        <div class="grid gap-2 sm:grid-cols-3">
          <label class="space-y-1">Трасса, м<input data-testid="installation-route" v-model.number="workFor(key).route" type="number" min="0" step="0.01" class="field-input" :disabled="busy || Boolean(confirmed)" /></label>
          <label class="space-y-1">Алмазные отверстия, шт<input data-testid="installation-holes" v-model.number="workFor(key).diamond" type="number" min="0" step="1" class="field-input" :disabled="busy || Boolean(confirmed)" /></label>
          <label class="space-y-1">Штробление, м<input v-model.number="workFor(key).chase" type="number" min="0" step="0.01" class="field-input" :disabled="busy || Boolean(confirmed)" /></label>
        </div>
        <div class="flex flex-wrap gap-4"><label class="flex items-center gap-2"><input v-model="workFor(key).pumpSupply" type="checkbox" :disabled="busy || Boolean(confirmed)" />Поставка насоса</label><label class="flex items-center gap-2"><input v-model="workFor(key).pumpInstall" type="checkbox" :disabled="busy || Boolean(confirmed)" />Монтаж насоса</label></div>
      </div>
      <div class="flex flex-wrap gap-4 border-t border-slate-200 pt-3"><label class="flex items-center gap-2"><input v-model="scaffold" type="checkbox" :disabled="busy || Boolean(confirmed)" />Леса на объекте</label><label class="flex items-center gap-2"><input v-model="lift" type="checkbox" :disabled="busy || Boolean(confirmed)" />Вышка на объекте</label></div>
      <button type="button" data-testid="installation-preview" class="btn-mini" :disabled="busy || Boolean(confirmed)" @click="calculate">{{ busy ? 'Проверяем…' : 'Рассчитать по книге' }}</button>
      <div v-if="preview" class="space-y-3 border-t border-slate-200 pt-3">
        <p class="font-semibold">{{ preview.status === 'fixed' ? 'Точная цена' : preview.status === 'from' ? 'Цена от' : 'Цена недоступна' }}<span v-if="preview.total"> · {{ formatMoney(Number(preview.total)) }}</span></p>
        <p v-if="statusText" class="text-amber-800">{{ statusText }} <a href="/manager/tariffs" class="underline">Тарифы</a></p>
        <template v-if="preview.status === 'fixed'">
          <div class="flex gap-2"><button type="button" class="btn-mini-outline" :class="mode === 'collapsed' ? 'border-brand-500 bg-brand-50 text-brand-700' : ''" :disabled="busy || Boolean(confirmed)" @click="mode = 'collapsed'">Одной строкой</button><button type="button" class="btn-mini-outline" :class="mode === 'detailed' ? 'border-brand-500 bg-brand-50 text-brand-700' : ''" :disabled="busy || Boolean(confirmed)" @click="mode = 'detailed'">По работам</button></div>
          <div class="space-y-2"><div v-for="(line, index) in projectedLines" :key="index" class="flex flex-col gap-1 border-b border-slate-200 pb-2 sm:flex-row sm:justify-between sm:gap-4"><span class="min-w-0 break-words">{{ line.title }}</span><strong class="shrink-0">{{ formatMoney(Number(line.price)) }}</strong></div></div>
          <p class="font-semibold">Итого: {{ formatMoney(Number(preview.total)) }}</p>
          <label v-if="!confirmed" class="flex items-start gap-2"><input data-testid="installation-consent" v-model="consent" type="checkbox" :disabled="busy" />Подтверждаю состав работ и цену по этой редакции книги</label>
          <button v-if="!confirmed" type="button" data-testid="installation-confirm" class="btn-mini" :disabled="busy || !consent" @click="confirm">Подтвердить цену</button>
          <p v-else class="text-emerald-800">Цена подтверждена. Прикрепите {{ mode === 'collapsed' ? 'одну строку' : 'строки работ' }} к текущему предложению.</p>
        </template>
      </div>
      <div v-if="confirmed" class="flex flex-wrap gap-2 border-t border-slate-200 pt-3">
        <button type="button" data-testid="installation-attach" class="btn-mini" :disabled="busy" @click="attach">{{ attachRetryRequired ? 'Повторить прикрепление' : 'Прикрепить к предложению' }}</button>
        <button type="button" data-testid="installation-start-new" class="btn-mini-outline" :disabled="busy || attachRetryRequired" @click="startNew">Новый расчёт</button>
      </div>
      <p v-if="error" role="alert" class="text-red-700">{{ error }}</p>
      <p v-if="notice" role="status" class="text-amber-800">{{ notice }}</p>
    </div>
  </div>
</template>
