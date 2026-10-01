<script setup lang="ts">
import { computed, nextTick, onScopeDispose, ref, watch } from 'vue';
import {
  ManagerInstallationEstimatesService, ManagerOrdersService,
  type InstallationInput,
  type ManagerInstallationConfirmResponse, type ManagerInstallationPreviewResponse,
  type OrderProductLineResponse, type TypedInstallationProfile_Input,
  type ManagerInstallationPreviewPayload,
} from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
import { managerSession } from '../../services/manager-session';
import { formatMoney } from './order-utils';
import { installationStandardWork, resolveInstallationStandard, type StandardInstallationChoice } from '../../services/installation-estimate-api';

type Mode = 'collapsed' | 'detailed';
type Source = 'proposal' | 'manual';
type Work = { workKind: 'standard' | 'prelaid_route'; route: number | null; thin: number | null; thick: number | null; over80: number | null; pumpPackage: boolean; chase: number };
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
  manualTariff?: StandardInstallationChoice | null;
  scaffold: boolean;
  lift: boolean;
  scaffoldActual: number | null;
  scaffoldScope: string;
  liftActual: number | null;
  liftScope: string;
  mode: Mode;
  intent?: StoredIntent;
};

const props = defineProps<{
  orderId: number;
  proposalId: number;
  compact?: boolean;
  hideActions?: boolean;
  beforeAction: () => Promise<boolean>;
  beginAttach: (orderId: number, proposalId: number, scopeKey: string, token: string) => Promise<boolean>;
  afterAttach: (orderId: number, proposalId: number, scopeKey: string, token: string) => Promise<boolean>;
  endAttach: (token: string) => void;
}>();
const open = ref(false);
const busy = ref(false);
const quickBusy = ref(false);
const editing = ref<Record<string, boolean>>({});
const error = ref('');
const notice = ref('');
const products = ref<OrderProductLineResponse[]>([]);
const source = ref<Source>('proposal');
const selected = ref<string[]>([]);
const work = ref<Record<string, Work>>({});
const manualKey = ref<string>(crypto.randomUUID());
const manualProfile = ref<TypedInstallationProfile_Input>({ product_kind: '', confirmed: false });
const manualTariff = ref<StandardInstallationChoice | null>(null);
const scaffold = ref(false);
const lift = ref(false);
const scaffoldActual = ref<number | null>(null);
const scaffoldScope = ref('');
const liftActual = ref<number | null>(null);
const liftScope = ref('');
const accessApprovalPending = computed(() =>
  (scaffold.value && (scaffoldActual.value == null || scaffoldScope.value.trim().length < 8)) ||
  (lift.value && (liftActual.value == null || liftScope.value.trim().length < 8)));
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
const makeWork = (): Work => ({ workKind: 'standard', route: null, thin: null, thick: null, over80: null, pumpPackage: false, chase: 0 });
const eligibleProducts = computed(() => products.value
  .filter((line) => line.proposal_id === props.proposalId && line.product_id && line.quantity > 0 && line.price > 0 && !line.is_installation_included));
const slots = computed<Slot[]>(() => eligibleProducts.value
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
  if (preview.value.reason_code === 'site_access_requires_approval') return 'Стоимость доступа ориентировочная. Укажите согласованную сумму и состав работ, затем рассчитайте заново.';
  if (preview.value.reason_code === 'wall_over_80_requires_quote') return 'Проход стены свыше 80 см требует индивидуальной сметы.';
  if (preview.value.reason_code === 'prelaid_new_route_requires_quote') return 'Новая трасса при монтаже на готовую трассу требует отдельной оценки.';
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
    price_changed: 'Книга цен изменилась. Рассчитайте смету заново и проверьте сумму.',
  };
  return (detail?.code && messages[detail.code]) || getApiErrorMessage(failure);
};

const save = (scope?: ActionScope) => {
  if (scope && !current(scope)) return;
  try {
    const draft: StoredDraft = {
      source: source.value, selected: selected.value, work: work.value,
      manualKey: manualKey.value, manualProfile: manualProfile.value,
      manualTariff: manualTariff.value,
      scaffold: scaffold.value, lift: lift.value, mode: mode.value,
      scaffoldActual: scaffoldActual.value, scaffoldScope: scaffoldScope.value,
      liftActual: liftActual.value, liftScope: liftScope.value,
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
    manualTariff.value = draft.manualTariff || null;
    scaffold.value = Boolean(draft.scaffold);
    lift.value = Boolean(draft.lift);
    scaffoldActual.value = draft.scaffoldActual ?? null;
    scaffoldScope.value = draft.scaffoldScope || '';
    liftActual.value = draft.liftActual ?? null;
    liftScope.value = draft.liftScope || '';
    mode.value = draft.mode === 'detailed' ? 'detailed' : 'collapsed';
    intent.value = draft.intent || null;
  } catch { /* A stale browser draft can be discarded. */ }
};
const reset = () => {
  busy.value = false;
  quickBusy.value = false;
  editing.value = {};
  open.value = false;
  products.value = [];
  source.value = 'proposal';
  selected.value = [];
  work.value = {};
  manualKey.value = crypto.randomUUID();
  manualProfile.value = { product_kind: '', confirmed: false };
  manualTariff.value = null;
  scaffold.value = false;
  lift.value = false;
  scaffoldActual.value = null;
  scaffoldScope.value = '';
  liftActual.value = null;
  liftScope.value = '';
  mode.value = 'collapsed';
  intent.value = null;
  consent.value = false;
  error.value = '';
  notice.value = '';
  restore();
};
watch(storageKey, () => { epoch += 1; reset(); }, { immediate: true, flush: 'sync' });
watch([source, selected, work, manualKey, manualProfile, manualTariff, scaffold, lift, scaffoldActual, scaffoldScope, liftActual, liftScope, mode, intent], () => save(), { deep: true });
watch([source, selected, work, manualProfile, scaffold, lift, scaffoldActual, scaffoldScope, liftActual, liftScope], () => { consent.value = false; }, { deep: true });

const workFor = (key: string): Work => {
  if (!work.value[key]) work.value[key] = makeWork();
  else if (work.value[key].thin === undefined) work.value[key] = { ...makeWork(), ...work.value[key] };
  return work.value[key];
};
const fillStandard = async (key: string, scope: ActionScope) => {
  const item = workFor(key);
  const slot = slots.value.find((candidate) => candidate.key === key);
  const tariff = await resolveInstallationStandard(source.value === 'manual'
    ? { typed_profile: manualProfile.value, work_kind: item.workKind }
    : { product_id: slot?.productId, work_kind: item.workKind });
  if (!current(scope)) return;
  Object.assign(item, installationStandardWork(tariff));
};
const toggleSlot = async (key: string) => {
  selected.value = selected.value.includes(key)
    ? selected.value.filter((item) => item !== key)
    : [...selected.value, key];
  if (!selected.value.includes(key) || work.value[key]?.route != null) return;
  const scope = capture();
  busy.value = true;
  error.value = '';
  try { await fillStandard(key, scope); }
  catch (failure) { if (current(scope)) { error.value = readableError(failure); editing.value[key] = true; } }
  finally { if (current(scope)) busy.value = false; }
};
const setWorkKind = async (key: string, kind: Work['workKind']) => {
  const scope = capture();
  workFor(key).workKind = kind;
  busy.value = true;
  error.value = '';
  try { await fillStandard(key, scope); }
  catch (failure) { if (current(scope)) error.value = readableError(failure); }
  finally { if (current(scope)) busy.value = false; }
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
const payload = (): ManagerInstallationPreviewPayload => {
  if (!activeKeys.value.length) throw new Error('Выберите оборудование или укажите параметры установки без товара.');
  if (activeKeys.value.length > 20) throw new Error('За один расчёт можно добавить не более 20 установок.');
  const installations: InstallationInput[] = activeKeys.value.map((key, index) => {
    const item = workFor(key);
    if (item.route == null || item.thin == null || item.thick == null || item.over80 == null ||
      !Number.isFinite(Number(item.route)) || Number(item.route) < 0 || Number(item.route) > 1000 ||
      [item.thin, item.thick, item.over80].some((value) => !Number.isInteger(Number(value)) || Number(value) < 0 || Number(value) > 100)) {
      throw new Error('Для каждой установки укажите новую трассу и проходы стен, даже если их количество 0.');
    }
    if (!Number.isFinite(Number(item.chase)) || Number(item.chase) < 0 || Number(item.chase) > 1000) {
      throw new Error('Укажите допустимую длину штробления.');
    }
    const extras = [];
    if (item.pumpPackage) extras.push({ code: 'pump.package', quantity: 1 });
    if (Number(item.chase) > 0) extras.push({ code: 'chase.extra_m', quantity: Number(item.chase) });
    const base = { key, display_label: `№${index + 1}`, work_kind: item.workKind,
      route_length_m: Number(item.route),
      holes_by_type: { through_thin: Number(item.thin), through_thick: Number(item.thick), through_over_80: Number(item.over80) }, extras };
    if (source.value === 'manual') {
      if (!manualProfile.value.confirmed) throw new Error('Подтвердите параметры оборудования для установки без товара.');
      if (!manualProfile.value.product_kind) throw new Error('Укажите вид оборудования.');
      if (manualProfile.value.product_kind === 'multi_split_system' &&
          (!manualProfile.value.indoor_unit_count || !manualProfile.value.composition_note?.trim())) {
        throw new Error('Для мультисплита подтвердите количество и состав внутренних блоков.');
      }
      const typedProfile = Object.fromEntries(Object.entries(manualProfile.value)
        .filter(([field, value]) => value !== '' && value !== null && value !== undefined &&
          (manualProfile.value.product_kind !== 'multi_split_system' || !['indoor_type', 'capacity_cooling_kw', 'pipe_liquid', 'pipe_gas',
            'weight_indoor', 'weight_outdoor', 'weight_indoor_package', 'weight_outdoor_package'].includes(field)) &&
          (manualProfile.value.product_kind === 'multi_split_system' || !['indoor_unit_count', 'composition_note'].includes(field)))) as TypedInstallationProfile_Input;
      return { ...base, typed_profile: typedProfile };
    }
    const slot = slots.value.find((candidate) => candidate.key === key);
    if (!slot) throw new Error('Оборудование изменилось. Обновите предложение и повторите расчёт.');
    return { ...base, product_id: slot.productId };
  });
  const site_extras = [
    ...(scaffold.value ? [{ code: 'access.scaffold', quantity: 1 }] : []),
    ...(lift.value ? [{ code: 'access.lift', quantity: 1 }] : []),
  ];
  const approved_site_access = [
    ...(scaffold.value && scaffoldActual.value != null && scaffoldScope.value.trim().length >= 8
      ? [{ code: 'access.scaffold' as const, actual_total: scaffoldActual.value, scope_note: scaffoldScope.value.trim() }] : []),
    ...(lift.value && liftActual.value != null && liftScope.value.trim().length >= 8
      ? [{ code: 'access.lift' as const, actual_total: liftActual.value, scope_note: liftScope.value.trim() }] : []),
  ];
  return { installations, site_extras, approved_site_access,
    ...(source.value === 'manual' && manualTariff.value ? { tariff_selections: { [manualKey.value]: manualTariff.value.code } } : {}),
    ...(source.value === 'manual' && manualTariff.value?.bookRevision ? { expected_revision: manualTariff.value.bookRevision } : {}),
  };
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
  } catch (failure) {
    if (current(scope)) {
      if ((failure as { body?: { detail?: { code?: string } } })?.body?.detail?.code === 'price_changed' && manualTariff.value) manualTariff.value.bookRevision = null;
      error.value = readableError(failure);
    }
  }
  finally { if (current(scope)) busy.value = false; }
};
const confirmEstimate = async () => {
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
      if (manualTariff.value) manualTariff.value.bookRevision = null;
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
const addCalculated = async () => {
  const scope = capture();
  if (!preview.value || preview.value.status !== 'fixed') return;
  consent.value = true;
  await confirmEstimate();
  if (current(scope) && confirmed.value && !error.value) await attach();
};
const addStandard = async () => {
  if (busy.value || quickBusy.value) return;
  const scope = capture();
  quickBusy.value = true;
  error.value = '';
  try {
    if (!open.value) await show();
    if (!current(scope) || error.value || !open.value) return;
    if (confirmed.value) { await attach(); return; }
    // Browser drafts are intentional work: continue them without replacing their measurements/extras.
    if (Object.keys(work.value).length) {
      await calculate();
      if (current(scope)) notice.value = 'Сохранён состав монтажа. Проверьте его и нажмите «Добавить монтаж».';
      return;
    }
    if (eligibleProducts.value.reduce((sum, line) => sum + line.quantity, 0) > 20) {
      throw new Error('В одной смете можно добавить до 20 установок. Выберите нужное оборудование в настройках монтажа.');
    }
    source.value = 'proposal';
    selected.value = slots.value.map((slot) => slot.key);
    if (!selected.value.length) throw new Error('Нет оборудования для стандартного монтажа. Выберите установку без товара.');
    busy.value = true;
    for (const key of selected.value) {
      await fillStandard(key, scope);
      if (!current(scope)) return;
    }
    busy.value = false;
    mode.value = 'collapsed';
    await calculate();
    if (current(scope) && !error.value) await addCalculated();
  } catch (failure) { if (current(scope)) error.value = readableError(failure); }
  finally { if (current(scope)) { busy.value = false; quickBusy.value = false; } }
};
const selectStandardTariff = async (tariff: StandardInstallationChoice, edit = false) => {
  if (busy.value || quickBusy.value) return;
  const scope = capture();
  if (!open.value) await show();
  if (!current(scope) || error.value || !open.value) return;
  if (confirmed.value || Object.keys(work.value).length) {
    notice.value = 'Сначала завершите текущую смету или начните новый расчёт.';
    return;
  }
  source.value = 'manual';
  manualTariff.value = tariff;
  manualProfile.value = { product_kind: tariff.product_kind,
    indoor_type: tariff.indoor_type as TypedInstallationProfile_Input['indoor_type'], confirmed: true };
  work.value[manualKey.value] = { ...makeWork(), ...installationStandardWork({
    status: 'fixed', scope_ref: '', included: { route_m: tariff.route_m, holes_by_type: tariff.holes_by_type },
  }) };
  editing.value[manualKey.value] = edit;
  await calculate();
  if (!edit && current(scope) && !error.value) {
    if (preview.value?.status === 'fixed' && Number(preview.value.total) !== Number(tariff.price)) {
      error.value = 'Цена тарифа изменилась. Проверьте новую сумму перед добавлением.';
      return;
    }
    await addCalculated();
  }
};
defineExpose({ openPanel: async () => { if (!open.value) await show(); }, actionBusy: computed(() => busy.value || quickBusy.value), addStandard, selectStandardTariff });
</script>

<template>
  <div>
    <div v-if="!hideActions" class="mt-3" :class="compact ? 'flex flex-wrap gap-2' : 'space-y-2'">
      <button type="button" data-testid="installation-standard-add" class="btn-mini justify-center" :class="compact ? 'text-xs' : 'w-full'" :disabled="busy || quickBusy" @click="addStandard">{{ quickBusy ? 'Добавляем монтаж…' : 'Стандартный монтаж' }}</button>
      <button type="button" data-testid="installation-open" class="btn-mini-outline justify-center" :class="compact ? 'text-xs' : 'w-full'" :disabled="busy || quickBusy" @click="show">{{ open ? 'Скрыть настройки монтажа' : 'Настроить состав' }}</button>
    </div>
    <p v-if="error && !open" role="alert" class="mt-2 text-sm text-red-700">{{ error }}</p>
    <p v-if="notice && !open" role="status" class="mt-2 text-sm text-emerald-700">{{ notice }}</p>
    <div v-if="open" class="mt-3 space-y-4 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm">
      <button v-if="hideActions" type="button" class="btn-mini-outline ml-auto flex text-xs" :disabled="busy || quickBusy" @click="show">Закрыть расчёт</button>
      <p class="text-slate-600">Расчёт относится к текущему черновику предложения. Строки и суммы берутся из опубликованной книги цен.</p>
      <div class="flex gap-2">
        <button type="button" class="btn-mini-outline" :class="source === 'proposal' ? 'border-brand-500 bg-brand-50 text-brand-700' : ''" :disabled="busy || quickBusy || Boolean(confirmed)" @click="source = 'proposal'">Товар в предложении</button>
        <button type="button" class="btn-mini-outline" :class="source === 'manual' ? 'border-brand-500 bg-brand-50 text-brand-700' : ''" :disabled="busy || quickBusy || Boolean(confirmed)" @click="source = 'manual'">Без товара</button>
      </div>
      <div v-if="source === 'proposal'" class="space-y-2">
        <p v-if="!slots.length" class="text-amber-800">Нет оплачиваемого оборудования без включённого монтажа. Сохраните товар в предложении или выберите установку без товара.</p>
        <label v-for="slot in slots" :key="slot.key" class="flex items-center gap-2"><input data-testid="installation-product" type="checkbox" :checked="selected.includes(slot.key)" :disabled="busy || quickBusy || Boolean(confirmed)" @change="toggleSlot(slot.key)" />{{ slot.label }}</label>
      </div>
      <div v-else-if="!manualTariff" class="grid gap-2 sm:grid-cols-2">
        <label class="space-y-1">Вид оборудования<select v-model="manualProfile.product_kind" class="field-input" :disabled="busy || quickBusy || Boolean(confirmed)"><option value="">Выберите</option><option value="complete_split_system">Комплект сплит-системы</option><option value="multi_split_system">Мультисплит-система</option><option value="indoor_unit">Отдельный внутренний блок</option><option value="outdoor_unit">Отдельный наружный блок</option><option value="other">Другое</option></select></label>
        <label v-if="manualProfile.product_kind !== 'multi_split_system'" class="space-y-1">Тип внутреннего блока<select v-model="manualProfile.indoor_type" class="field-input" :disabled="busy || quickBusy || Boolean(confirmed)"><option :value="undefined">Выберите</option><option value="wall">Настенный</option><option value="cassette">Кассетный</option><option value="duct">Канальный</option><option value="floor_ceiling">Напольно-потолочный</option><option value="column">Колонный</option><option value="console">Консольный</option></select></label>
        <label v-if="manualProfile.product_kind === 'multi_split_system'" class="space-y-1">Внутренних блоков в системе<input v-model.number="manualProfile.indoor_unit_count" type="number" min="2" max="20" step="1" class="field-input" :disabled="busy || quickBusy || Boolean(confirmed)" /></label>
        <label v-if="manualProfile.product_kind === 'multi_split_system'" class="space-y-1 sm:col-span-2">Проверенный состав системы<textarea v-model="manualProfile.composition_note" class="field-input" rows="2" placeholder="Например, два внутренних блока и один наружный блок" :disabled="busy || quickBusy || Boolean(confirmed)" /></label>
        <template v-if="manualProfile.product_kind !== 'multi_split_system'">
          <label class="space-y-1">Холодопроизводительность, кВт<input v-model.number="manualProfile.capacity_cooling_kw" type="number" min="0.001" step="0.001" class="field-input" :disabled="busy || quickBusy || Boolean(confirmed)" /></label>
          <label class="space-y-1">Жидкостная труба<input v-model="manualProfile.pipe_liquid" class="field-input" placeholder="Например 1/4&quot;" :disabled="busy || quickBusy || Boolean(confirmed)" /></label>
          <label class="space-y-1">Газовая труба<input v-model="manualProfile.pipe_gas" class="field-input" placeholder="Например 3/8&quot;" :disabled="busy || quickBusy || Boolean(confirmed)" /></label>
          <label class="space-y-1">Вес внутреннего блока, кг<input v-model.number="manualProfile.weight_indoor" type="number" min="0.01" step="0.01" class="field-input" :disabled="busy || quickBusy || Boolean(confirmed)" /></label>
          <label class="space-y-1">Вес наружного блока, кг<input v-model.number="manualProfile.weight_outdoor" type="number" min="0.01" step="0.01" class="field-input" :disabled="busy || quickBusy || Boolean(confirmed)" /></label>
          <label class="space-y-1">Вес упаковки внутреннего блока, кг<input v-model.number="manualProfile.weight_indoor_package" type="number" min="0.01" step="0.01" class="field-input" :disabled="busy || quickBusy || Boolean(confirmed)" /></label>
          <label class="space-y-1">Вес упаковки наружного блока, кг<input v-model.number="manualProfile.weight_outdoor_package" type="number" min="0.01" step="0.01" class="field-input" :disabled="busy || quickBusy || Boolean(confirmed)" /></label>
        </template>
        <label class="flex items-center gap-2 sm:col-span-2"><input v-model="manualProfile.confirmed" type="checkbox" :disabled="busy || quickBusy || Boolean(confirmed)" />Параметры оборудования проверены; установка выполняется без продажи товара в этом предложении</label>
      </div>
      <p v-else class="font-medium">{{ manualTariff.title }} · монтаж без товара</p>
      <div v-for="(key, index) in activeKeys" :key="key" class="space-y-2 border-t border-slate-200 pt-3">
        <p class="font-medium">Установка №{{ index + 1 }} · {{ source === 'manual' ? 'без товара' : slots.find((slot) => slot.key === key)?.label }}</p>
        <template v-if="(source === 'proposal' || manualTariff) && !editing[key] && workFor(key).route != null">
          <p class="text-slate-600" data-testid="installation-standard-summary">Трасса {{ workFor(key).route }} м · проходы: {{ Number(workFor(key).thin) + Number(workFor(key).thick) + Number(workFor(key).over80) }} · {{ workFor(key).pumpPackage ? 'с насосом' : 'без насоса' }}</p>
          <p v-if="workFor(key).chase" class="text-slate-600">Штробление {{ workFor(key).chase }} м</p>
          <button type="button" data-testid="installation-edit-work" class="btn-mini-outline" :disabled="busy || quickBusy || Boolean(confirmed)" @click="editing[key] = true">Изменить состав</button>
        </template>
        <template v-else>
        <button v-if="source === 'manual' && !manualTariff" type="button" class="btn-mini-outline" :disabled="busy || quickBusy || Boolean(confirmed) || !manualProfile.confirmed" @click="setWorkKind(key, workFor(key).workKind)">Заполнить базу по тарифу</button>
        <div v-if="!manualTariff" class="flex gap-2"><button type="button" class="btn-mini-outline" :class="workFor(key).workKind === 'standard' ? 'border-brand-500 bg-brand-50 text-brand-700' : ''" :disabled="busy || quickBusy || Boolean(confirmed)" @click="setWorkKind(key, 'standard')">Обычный монтаж</button><button type="button" class="btn-mini-outline" :class="workFor(key).workKind === 'prelaid_route' ? 'border-brand-500 bg-brand-50 text-brand-700' : ''" :disabled="busy || quickBusy || Boolean(confirmed)" @click="setWorkKind(key, 'prelaid_route')">На готовую трассу</button></div>
        <div class="grid gap-2 sm:grid-cols-3">
          <label class="space-y-1">{{ workFor(key).workKind === 'prelaid_route' ? 'Новая дополнительная трасса, м' : 'Вся новая трасса, м' }}<input data-testid="installation-route" v-model.number="workFor(key).route" type="number" min="0" step="0.01" class="field-input" :disabled="busy || quickBusy || Boolean(confirmed)" /></label>
          <label class="space-y-1">Доп. межкомнатные проходы до 20 см<input data-testid="installation-holes" v-model.number="workFor(key).thin" type="number" min="0" step="1" class="field-input" :disabled="busy || quickBusy || Boolean(confirmed)" /></label>
          <label class="space-y-1">Проходы основных стен до 80 см<input data-testid="installation-thick-holes" v-model.number="workFor(key).thick" type="number" min="0" step="1" class="field-input" :disabled="busy || quickBusy || Boolean(confirmed)" /></label>
          <label class="space-y-1">Проходы свыше 80 см (по запросу)<input data-testid="installation-over80-holes" v-model.number="workFor(key).over80" type="number" min="0" step="1" class="field-input" :disabled="busy || quickBusy || Boolean(confirmed)" /></label>
          <label class="space-y-1">Штробление, м<input v-model.number="workFor(key).chase" type="number" min="0" step="0.01" class="field-input" :disabled="busy || quickBusy || Boolean(confirmed)" /></label>
        </div>
        <label class="flex items-center gap-2"><input v-model="workFor(key).pumpPackage" type="checkbox" :disabled="busy || quickBusy || Boolean(confirmed)" />Насос с установкой</label>
        </template>
      </div>
      <div class="flex flex-wrap gap-4 border-t border-slate-200 pt-3"><label class="flex items-center gap-2"><input v-model="scaffold" type="checkbox" :disabled="busy || quickBusy || Boolean(confirmed)" />Леса на объекте</label><label class="flex items-center gap-2"><input v-model="lift" type="checkbox" :disabled="busy || quickBusy || Boolean(confirmed)" />Вышка на объекте</label></div>
      <div v-if="scaffold || lift" class="grid gap-2 sm:grid-cols-2"><p v-if="accessApprovalPending" class="sm:col-span-2 text-amber-800">Цены доступа пока ориентировочные. Для точной сметы укажите согласованные сумму и состав работ.</p><template v-if="scaffold"><label class="space-y-1">Леса: согласованная сумма, BYN<input data-testid="scaffold-actual" v-model.number="scaffoldActual" type="number" min="0" step="0.01" class="field-input" :disabled="busy || quickBusy || Boolean(confirmed)" /></label><label class="space-y-1">Леса: согласованный состав<input data-testid="scaffold-scope" v-model="scaffoldScope" class="field-input" :disabled="busy || quickBusy || Boolean(confirmed)" /></label></template><template v-if="lift"><label class="space-y-1">Вышка: согласованная сумма, BYN<input v-model.number="liftActual" type="number" min="0" step="0.01" class="field-input" :disabled="busy || quickBusy || Boolean(confirmed)" /></label><label class="space-y-1">Вышка: согласованный состав и время<input v-model="liftScope" class="field-input" :disabled="busy || quickBusy || Boolean(confirmed)" /></label></template></div>
      <button type="button" data-testid="installation-preview" class="btn-mini" :disabled="busy || quickBusy || Boolean(confirmed)" @click="calculate">{{ busy ? 'Проверяем…' : 'Рассчитать по книге' }}</button>
      <div v-if="preview" class="space-y-3 border-t border-slate-200 pt-3">
        <p class="font-semibold">{{ preview.status === 'fixed' ? 'Точная цена' : preview.status === 'from' ? 'Цена от' : preview.status === 'provisional' ? 'Ориентировочная сумма' : 'Цена недоступна' }}<span v-if="preview.total"> · {{ formatMoney(Number(preview.total)) }}</span></p>
        <p v-if="statusText" class="text-amber-800">{{ statusText }} <a href="/manager/tariffs" class="underline">Тарифы</a></p>
        <template v-if="preview.status === 'fixed'">
          <div class="flex gap-2"><button type="button" class="btn-mini-outline" :class="mode === 'collapsed' ? 'border-brand-500 bg-brand-50 text-brand-700' : ''" :disabled="busy || quickBusy || Boolean(confirmed)" @click="mode = 'collapsed'">Одной строкой</button><button type="button" class="btn-mini-outline" :class="mode === 'detailed' ? 'border-brand-500 bg-brand-50 text-brand-700' : ''" :disabled="busy || quickBusy || Boolean(confirmed)" @click="mode = 'detailed'">По работам</button></div>
          <div class="space-y-2"><div v-for="(line, index) in projectedLines" :key="index" class="border-b border-slate-200 pb-2"><div class="flex justify-between gap-4"><span class="min-w-0 break-words font-medium">{{ line.title }}</span><strong class="shrink-0">{{ line.quantity || 1 }} × {{ formatMoney(Number(line.price)) }}</strong></div><p v-if="line.description" class="mt-1 text-xs font-normal text-slate-500">{{ line.description }}</p></div></div>
          <p class="font-semibold">Итого: {{ formatMoney(Number(preview.total)) }}</p>
          <button v-if="!confirmed" type="button" data-testid="installation-add" class="btn-mini" :disabled="busy || quickBusy" @click="addCalculated">Добавить монтаж</button>
          <p v-else class="text-emerald-800">Цена подтверждена. Повторите прикрепление к текущему предложению.</p>
        </template>
      </div>
      <div v-if="confirmed" class="flex flex-wrap gap-2 border-t border-slate-200 pt-3">
        <button type="button" data-testid="installation-attach" class="btn-mini" :disabled="busy || quickBusy" @click="attach">{{ attachRetryRequired ? 'Повторить прикрепление' : 'Прикрепить к предложению' }}</button>
        <button type="button" data-testid="installation-start-new" class="btn-mini-outline" :disabled="busy || quickBusy || attachRetryRequired" @click="startNew">Новый расчёт</button>
      </div>
      <p v-if="error" role="alert" class="text-red-700">{{ error }}</p>
      <p v-if="notice" role="status" class="text-amber-800">{{ notice }}</p>
    </div>
  </div>
</template>
