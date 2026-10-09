<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { ApiError, ManagerMaintenanceObservationsService as api, ManagerOrdersService,
  type MaintenanceObservationItem, type MaintenanceOfferItem, type MaintenanceOfferCommand,
  type PrepareMaintenanceOffer, type ResolveMaintenanceObservation, type OrderProposalResponse } from '../../client';
import MoneyAmount from '../money/MoneyAmount.vue';
import { getApiErrorMessage } from '../../utils/api-errors';
const emit = defineEmits<{ refresh: [] }>();
const props = defineProps<{ orderId: number; observations: MaintenanceObservationItem[] }>();
const offers = ref<MaintenanceOfferItem[]>([]);
const total = ref(0);
const continuationId = ref<number | null>(null);
const proposals = ref<OrderProposalResponse[]>([]);
const proposalId = ref<number | null>(null);
const mappings = ref<Record<string, { observation: number | null; purpose: 'diagnosis' | 'repair' }>>({});
const busy = ref(false);
const error = ref('');
const source = ref('');
const comment = ref('');
const occurredAt = ref('');
const accepted = ref<Record<number, string[]>>({});
const resolution = ref({ observationId: null as number | null, offerId: null as number | null, evidence: '', date: '' });
const pending = ref<{ type: 'prepare'; payload: PrepareMaintenanceOffer } | { type: 'command'; offerId: number; payload: MaintenanceOfferCommand } | null>(null);
let generation = 0;
const formOwner = computed(() => `maintenance-offer-${props.orderId}`);
const selectedProposal = computed(() => proposals.value.find((p) => p.id === proposalId.value));
const lines = computed(() => [
  ...(selectedProposal.value?.service_lines || []).map((l) => ({ kind: 'service' as const, id: l.id, key: `service:${l.id}`, title: l.service_title, quantity: l.quantity, price: l.price })),
  ...(selectedProposal.value?.product_lines || []).map((l) => ({ kind: 'product' as const, id: l.id, key: `product:${l.id}`, title: l.product_title, quantity: l.quantity, price: l.price })),
]);
const ready = computed(() => lines.value.length > 0 && lines.value.every((l) => mappings.value[l.key]?.observation));
const labels: Record<string, string> = { draft: 'Черновик', issue: 'Выпущено', send: 'Отправка зарегистрирована', accept: 'Согласовано', reject: 'Отказ', defer: 'Отложено', continue: 'Передано в работу' };
const localNow = () => { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16); };
const frozenLines = (offer: MaintenanceOfferItem): Array<{key: string; label?: string; purpose: string; observation_id: number; data: {title?: string; title_snapshot?: string; quantity: number; price: number | string; description?: string; is_installation_included?: boolean; installation_price?: number; logistics_components?: Array<{title: string; quantity_per_parent?: number; unit?: string; unit_price?: number}>}}> => offer.snapshot.lines || [];
const agreedLines = (offer: MaintenanceOfferItem): string[] | null => [...offer.events].reverse().find(e => ['accept', 'continue'].includes(e.action))?.details.accepted_lines ?? null;
const amount = (offer: MaintenanceOfferItem, selected = false) => frozenLines(offer).filter(l => !selected || agreedLines(offer)?.includes(l.key)).reduce((total, l) => total + Number(l.data.price) * l.data.quantity, 0);
async function refresh() { error.value = ''; await load(); emit('refresh'); }
async function load(more = false) {
  const request = generation;
  try {
    const result = await api.listManagerMaintenanceOffers(props.orderId, 50, more ? offers.value.length : 0);
    if (request !== generation) return;
    offers.value = more ? [...offers.value, ...result.items] : result.items;
    total.value = result.total;
    for (const offer of result.items) accepted.value[offer.id] ??= [];
    continuationId.value ??= result.items[0]?.continuation_order_id ?? null;
  } catch (e) { if (request === generation) error.value = getApiErrorMessage(e); }
}
async function workspace() {
  const request = generation;
  busy.value = true; error.value = '';
  try {
    const result = await api.prepareManagerMaintenanceWorkspace(props.orderId);
    if (request !== generation) return;
    continuationId.value = result.continuation_order_id;
    const order = await ManagerOrdersService.getManagerOrderDetail(result.continuation_order_id);
    if (request !== generation) return;
    proposals.value = (order.proposals || []).filter((p) => !p.is_archived);
    proposalId.value = proposals.value.find((p) => p.status === 'draft')?.id ?? proposals.value.find((p) => p.is_selected)?.id ?? null;
  } catch (e) { if (request === generation) error.value = getApiErrorMessage(e); }
  finally { if (request === generation) busy.value = false; }
}
watch(lines, (values) => { for (const l of values) mappings.value[l.key] ??= { observation: null, purpose: 'diagnosis' }; });
async function execute() {
  if (busy.value || !pending.value) return;
  const request = generation; busy.value = true; error.value = '';
  try {
    const p = pending.value;
    if (p.type === 'prepare') await api.prepareManagerMaintenanceOffer(props.orderId, p.payload);
    else await api.commandManagerMaintenanceOffer(props.orderId, p.offerId, p.payload);
    if (request !== generation) return;
    pending.value = null;
    await load();
  } catch (e) {
    if (request !== generation) return;
    if (e instanceof ApiError && e.status >= 400 && e.status < 500) pending.value = null;
    error.value = getApiErrorMessage(e);
  } finally { if (request === generation) busy.value = false; }
}
async function prepare() {
  if (!ready.value || !proposalId.value || pending.value) return;
  pending.value = { type: 'prepare', payload: { command_key: crypto.randomUUID(), proposal_id: proposalId.value,
    lines: lines.value.map((l) => ({ kind: l.kind, line_id: l.id, purpose: mappings.value[l.key]!.purpose,
      observation_id: mappings.value[l.key]!.observation!, expected_version: props.observations.find((o) => o.id === mappings.value[l.key]!.observation)!.version })) } };
  await execute();
}
async function command(offer: MaintenanceOfferItem, action: MaintenanceOfferCommand['action']) {
  if (!source.value.trim() || !comment.value.trim() || !occurredAt.value || pending.value) { error.value = 'Укажите источник, дату и комментарий события.'; return; }
  pending.value = { type: 'command', offerId: offer.id, payload: { command_key: crypto.randomUUID(), expected_version: offer.version, action,
    source: source.value.trim(), comment: comment.value.trim(), occurred_at: new Date(occurredAt.value).toISOString(),
    accepted_lines: action === 'accept' ? accepted.value[offer.id] || [] : [] } };
  await execute();
}
const pendingResolution = ref<{ observationId: number; payload: ResolveMaintenanceObservation } | null>(null);
async function resolve() {
  const r = resolution.value;
  if (!pendingResolution.value) {
    const observation = props.observations.find((o) => o.id === r.observationId);
    if (!observation || !r.offerId || !r.evidence.trim() || !r.date) return;
    pendingResolution.value = { observationId: observation.id, payload: { command_key: crypto.randomUUID(), expected_version: observation.version,
      offer_id: r.offerId, evidence: r.evidence.trim(), resolved_at: new Date(r.date).toISOString() } };
  }
  const request = generation; busy.value = true; error.value = '';
  try {
    await api.resolveManagerMaintenanceObservation(pendingResolution.value.observationId, pendingResolution.value.payload);
    if (request !== generation) return;
    pendingResolution.value = null; resolution.value.observationId = null; await load(); emit('refresh');
  } catch(e) {
    if (request !== generation) return;
    if (e instanceof ApiError && e.status >= 400 && e.status < 500) pendingResolution.value = null;
    error.value = getApiErrorMessage(e);
  } finally { if (request === generation) busy.value = false; }
}
watch(() => props.orderId, () => { generation++; offers.value = []; continuationId.value = null; proposals.value = []; mappings.value = {}; pending.value = null; pendingResolution.value = null; accepted.value = {}; source.value = ''; comment.value = ''; resolution.value = { observationId: null, offerId: null, evidence: '', date: '' }; error.value = ''; busy.value = false; occurredAt.value = localNow(); void load(); }, { immediate: true });
onBeforeUnmount(() => { generation++; });
</script>
<template>
<section class="offer-panel" aria-label="Предложения и согласование ТО">
  <h3 class="font-semibold">Предложения и согласование</h3>
  <p class="text-sm">Подготовьте диагностику или известный ремонт в обычной карточке: услуги, тарифы и сметы. Неизвестный объём оставьте на уточнение. Согласие не означает устранение.</p>
  <p v-if="error" role="alert" class="text-sm text-red-600">{{ error }}</p>
  <button v-if="pending" type="button" :disabled="busy" @click="execute">Повторить сохранённую команду</button>
  <button v-if="pendingResolution" type="button" :disabled="busy" @click="resolve">Повторить подтверждение устранения</button>
  <fieldset :disabled="busy || Boolean(pending) || Boolean(pendingResolution)" class="space-y-3">
    <button type="button" @click="refresh">Обновить предложения и замечания</button>
    <button type="button" data-testid="maintenance-workspace" @click="workspace">Подготовить / обновить карточку продолжения</button>
    <a v-if="continuationId" :href="`/manager/orders/kanban?orderId=${continuationId}`" target="_blank" rel="noopener">Ремонтная карточка #{{ continuationId }} ↗</a>
    <template v-if="proposals.length">
      <label>Вариант со штатными ценами<select :form="formOwner" v-model="proposalId"><option v-for="p in proposals" :key="p.id" :value="p.id">{{ p.name }}</option></select></label>
      <p v-if="!lines.length" class="text-sm">Добавьте строки в ремонтной карточке, затем обновите состав здесь.</p>
      <div v-for="line in lines" :key="line.key" class="offer-line">
        <span>{{ line.title }} · {{ line.quantity }} × <MoneyAmount :value="line.price" /></span>
        <label>Замечание<select :form="formOwner" v-model="mappings[line.key]!.observation" :aria-label="`Замечание для ${line.title}`"><option :value="null">Выберите</option><option v-for="o in observations" :key="o.id" :value="o.id">#{{ o.id }} {{ o.equipment_description }} · v{{ o.version }}</option></select></label>
        <label>Цель<select :form="formOwner" v-model="mappings[line.key]!.purpose"><option value="diagnosis">Диагностика / уточнение</option><option value="repair">Известный ремонт</option></select></label>
      </div>
      <button type="button" data-testid="prepare-offer" :disabled="!ready" @click="prepare">Сохранить новую версию предложения</button>
    </template>
    <div v-if="offers.length" class="grid gap-2 sm:grid-cols-2">
      <label>Источник / канал события<input :form="formOwner" v-model="source" placeholder="Письмо клиента, звонок, встреча…" /></label>
      <label>Дата события<input :form="formOwner" v-model="occurredAt" type="datetime-local" /></label>
      <label class="sm:col-span-2">Комментарий / подтверждение<textarea :form="formOwner" v-model="comment" /></label>
    </div>
    <article v-for="offer in offers" :key="offer.id" class="offer-line space-y-2">
      <h4 class="font-semibold">КП #{{ offer.id }} · {{ labels[offer.state] }} · версия событий {{ offer.version }}</h4>
      <p class="text-sm">{{ offer.snapshot.proposal_name }} · Полный состав: <MoneyAmount :value="amount(offer)" /><span v-if="agreedLines(offer)"> · Согласовано: <MoneyAmount :value="amount(offer, true)" /></span></p>
      <label v-for="line in frozenLines(offer)" :key="line.key" class="flex gap-2">
        <input v-if="['send', 'reject', 'defer'].includes(offer.state)" :form="formOwner" v-model="accepted[offer.id]" type="checkbox" :value="line.key" :aria-label="`Согласовать ${line.key}`" />
        <span>#{{ line.observation_id }} · {{ line.purpose === 'diagnosis' ? 'Диагностика' : 'Ремонт' }} · {{ line.label || line.data.title || line.data.title_snapshot || line.key }} · {{ line.data.quantity }} × <MoneyAmount :value="Number(line.data.price)" />
          <strong v-if="agreedLines(offer)" class="block" :class="agreedLines(offer)!.includes(line.key) ? 'text-green-700' : 'text-amber-700'">{{ agreedLines(offer)!.includes(line.key) ? 'Согласовано' : 'Не согласовано' }}</strong>
          <span v-if="line.data.description" class="block whitespace-pre-wrap">{{ line.data.description }}</span>
          <span v-if="line.data.is_installation_included" class="block text-xs">Монтаж включён в цену<span v-if="line.data.installation_price"> · <MoneyAmount :value="line.data.installation_price" /></span></span>
          <span v-for="(part, index) in line.data.logistics_components || []" :key="index" class="block text-xs">Состав: {{ part.title }} · {{ part.quantity_per_parent }} {{ part.unit }}<span v-if="part.unit_price != null"> · <MoneyAmount :value="part.unit_price" /></span></span>
        </span>
      </label>
      <div class="flex flex-wrap gap-2">
        <button v-if="offer.state === 'draft'" type="button" @click="command(offer, 'issue')">Выпустить</button>
        <button v-if="offer.state === 'issue'" type="button" @click="command(offer, 'send')">Зафиксировать отправку клиенту</button>
        <template v-if="['send', 'reject', 'defer'].includes(offer.state)">
          <button type="button" :disabled="!accepted[offer.id]?.length" @click="command(offer, 'accept')">Согласовать выбранные строки</button>
          <button v-if="offer.state !== 'reject'" type="button" @click="command(offer, 'reject')">Зафиксировать отказ</button>
          <button v-if="offer.state !== 'defer'" type="button" @click="command(offer, 'defer')">Отложить</button>
        </template>
        <button v-if="offer.state === 'accept'" type="button" @click="command(offer, 'continue')">Продолжить согласованные работы в этой карточке</button>
      </div>
      <details><summary>История решений</summary><p v-for="event in offer.events" :key="event.id" class="text-sm">{{ labels[event.action] }} · {{ event.occurred_at }} · {{ event.actor }} · {{ event.details.source }} · {{ event.details.comment }} <span v-if="event.details.accepted_lines?.length">Состав: {{ event.details.accepted_lines.join(', ') }}</span></p></details>
      <p v-for="r in offer.resolutions" :key="r.id" class="text-sm">Замечание #{{ r.observation_id }} устранено · {{ r.resolved_at }} · {{ r.actor }} · {{ r.evidence }}</p>
      <template v-if="offer.state === 'continue'">
        <button v-for="id in [...new Set(frozenLines(offer).filter(l => l.purpose === 'repair' && offer.events[offer.events.length - 1]?.details.accepted_lines.includes(l.key)).map(l => l.observation_id))].filter(id => !offer.resolutions.some(r => r.observation_id === id))" :key="id" type="button" @click="resolution = { observationId: id, offerId: offer.id, evidence: '', date: localNow() }; pendingResolution = null">Подтвердить устранение #{{ id }}</button>
      </template>
    </article>
    <button v-if="offers.length < total" type="button" @click="load(true)">Ещё предложения</button>
    <div v-if="resolution.observationId" class="offer-line space-y-2">
      <h4>Подтверждение фактического устранения #{{ resolution.observationId }}</h4>
      <label>Дата ремонта<input :form="formOwner" v-model="resolution.date" type="datetime-local" /></label>
      <label>Выполненные работы и доказательство<textarea :form="formOwner" v-model="resolution.evidence" /></label>
      <button type="button" :disabled="!resolution.evidence.trim() || !resolution.date" @click="resolve">Подтвердить устранение и записать ремонт в историю</button>
    </div>
  </fieldset>
</section>
</template>
<style scoped>
.offer-panel { border: 1px solid var(--mv-border, #ddd); border-radius: 10px; padding: 12px; display: grid; gap: 12px; }
.offer-line { border: 1px solid var(--mv-border, #ddd); border-radius: 8px; padding: 10px; display: grid; gap: 8px; }
label { display: grid; gap: 4px; font-size: 13px; } input:not([type=checkbox]), select, textarea { width: 100%; min-width: 0; border: 1px solid var(--mv-border, #ddd); border-radius: 6px; padding: 7px; background: var(--mv-panel, white); } button { border: 1px solid var(--mv-border, #ddd); border-radius: 6px; padding: 7px 10px; font-size: 13px; } button:disabled { opacity: .5; } a { color: var(--kitlane-accent-text, #2563eb); margin-left: 8px; }
</style>
