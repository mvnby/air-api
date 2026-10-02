<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { leadInboxApi, notifyInboxChanged, type InboxItem, type InboxHistory, type InboxContactRequest } from '../../services/lead-inbox';
import LeadInboxDetails from './LeadInboxDetails.vue';
import LeadRefusalPanel from './LeadRefusalPanel.vue';
const props = defineProps<{ item: InboxItem; isArchive?: boolean; contactSaving?: boolean }>();
const emit = defineEmits<{
  (e: 'qualify', item: InboxItem): void; (e: 'no-answer', request: InboxContactRequest): void;
  (e: 'review-source', item: InboxItem): void; (e: 'link-changed'): void;
  (e: 'updated', item: InboxItem): void; (e: 'archived', item: InboxItem): void;
  (e: 'restore', item: InboxItem): void; (e: 'details-closed'): void;
}>();
const expanded = ref(false);
const refusing = ref(false);
const refusalMode = ref<'refusal' | 'not_request'>('refusal');
const detailLoading = ref(false);
const error = ref('');
const detail = ref<InboxItem | null>(null);
const history = ref<InboxHistory[]>([]);
const readSaving = ref(false);
const current = computed(() => detail.value ? { ...detail.value, ...props.item } : props.item);
const unread = computed(() => props.item.is_read === undefined ? props.item.is_new : !props.item.is_read);
const regionId = computed(() => `lead-details-${props.item.entity_kind || 'order'}-${props.item.id}`);
const sources: Record<string, string> = { site: 'Сайт', phone: 'Телефон', bot: 'Бот', email: 'Почта', manager: 'Менеджер', referral: 'Рекомендация', belzakupki: 'Тендер', other: 'Другое' };
const reasons: Record<string, string> = { profile: 'Не наш профиль', region: 'Не наш регион', terms: 'Не подходят условия', capacity: 'Нет ресурсов / сроков', unclear: 'Не хватает данных', other: 'Другое' };
const outcomes: Record<string, string> = { spam: 'Спам', duplicate: 'Дубликат', deadline_expired: 'Срок истёк', legacy_lost: 'Архивное обращение', refusal: 'Не берём', linked: 'Связано с заказом' };
const title = computed(() => props.item.title || props.item.summary || props.item.comment?.split('\n').find(line => line.trim()) || 'Обращение без описания');
const summary = computed(() => props.item.summary || (props.item.comment?.trim() !== title.value.trim() ? props.item.comment : ''));
const customer = computed(() => props.item.customer_full_legal_name || props.item.customer_name || 'Клиент не указан');
const date = (value: string) => { const parsed = new Date(value); return Number.isNaN(parsed.getTime()) ? 'Дата не указана' : parsed.toLocaleString('ru-RU', { timeZone: 'Europe/Minsk', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }); };
const displayDate = computed(() => props.item.source_created_at || props.item.created_at);
const deadline = computed(() => props.item.deadline_at || props.item.tender?.deadline_at);
const budget = computed(() => props.item.budget_amount == null ? null : new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(props.item.budget_amount));
const setRead = async (isRead: boolean) => {
  if (readSaving.value) return;
  readSaving.value = true; error.value = '';
  try { const updated = await leadInboxApi.read(props.item.id, isRead, props.item.entity_kind); emit('updated', updated); notifyInboxChanged(); }
  catch (caught) { error.value = caught instanceof Error ? caught.message : 'Не удалось сохранить отметку просмотра'; }
  finally { readSaving.value = false; }
};
const loadDetails = async () => {
  detailLoading.value = true; error.value = '';
  try {
    const result = await leadInboxApi.detail(props.item.id, props.item.entity_kind);
    if (!expanded.value) return;
    detail.value = result; history.value = result.history || [];
    if (unread.value) await setRead(true);
  } catch (caught) { error.value = caught instanceof Error ? caught.message : 'Не удалось загрузить подробности'; }
  finally { detailLoading.value = false; }
};
watch(() => props.item.no_answer_count, (value, oldValue) => { if (expanded.value && value !== oldValue) void loadDetails(); });
const toggleDetails = () => {
  expanded.value = !expanded.value;
  if (expanded.value) { refusing.value = false; void loadDetails(); }
  else emit('details-closed');
};
const sourceUpdated = (updated: InboxItem, events: InboxHistory[]) => { detail.value = { ...detail.value, ...updated }; history.value = events; emit('updated', updated); notifyInboxChanged(); };
const markUnread = async () => { await setRead(false); if (!error.value) expanded.value = false; };
</script>
<template>
  <article class="inbox-card" :class="{ 'is-unread': unread && !isArchive }" :data-testid="`inbox-card-${item.entity_kind || 'order'}-${item.id}`">
    <div class="card-body">
      <div class="card-meta"><span v-if="unread && !isArchive" class="unread-dot" aria-label="Непросмотрено" /><span class="source">{{ sources[item.source || ''] || item.source || 'Источник не указан' }}</span><span class="lead-id">#{{ item.id }}</span><time :datetime="displayDate" class="time">{{ date(displayDate) }}</time></div>
      <div class="headline"><div class="subject"><h2><button type="button" class="title" :title="title" :aria-expanded="expanded" :aria-controls="regionId" @click="toggleDetails">{{ title }}</button></h2><p class="customer">{{ customer }}<span v-if="item.customer_type === 'individual_entrepreneur'"> · ИП</span><span v-if="item.customer_inn"> · УНП {{ item.customer_inn }}</span></p></div><div v-if="budget !== null" class="budget"><small>Бюджет</small><strong>{{ budget }} {{ item.budget_currency || '' }}</strong></div></div>
      <div v-if="deadline || item.auto_archive_at || item.location || item.quantity != null || item.attachment_count" class="facts"><span v-if="deadline" class="deadline">{{ item.source_kind === 'tender' || item.source === 'belzakupki' ? 'Срок подачи' : 'Срок' }}: {{ date(deadline) }}</span><span v-if="!isArchive && item.auto_archive_at">В архив автоматически: {{ date(item.auto_archive_at) }}</span><span v-if="item.quantity != null">{{ item.quantity }} ед.</span><span v-if="item.location">{{ item.location }}</span><button v-if="item.attachment_count && item.entity_kind !== 'lead'" type="button" :aria-expanded="expanded" :aria-controls="`lead-attachments-${item.id}`" :aria-label="`Показать вложения обращения: ${item.attachment_count}`" @click="toggleDetails">Вложения: {{ item.attachment_count }}</button></div>
      <p v-if="summary" class="blurb">{{ summary }}</p>
      <p v-if="item.commercial_terms_summary?.length" class="terms-summary">{{ item.commercial_terms_summary.join(' · ') }}</p>
      <div v-if="item.related_requests?.length" class="related-requests"><p v-for="related in item.related_requests" :key="related.order_id"><strong>Эта закупка уже встречалась:</strong> <a :href="`/manager/orders/kanban?orderId=${related.order_id}`">#{{ related.order_id }} {{ related.title }}</a><span v-if="related.outcome"> · {{ outcomes[related.outcome] || related.outcome }}</span><span v-if="related.reason"> · {{ reasons[related.reason] || related.reason }}</span><span v-if="related.note"> · {{ related.note }}</span></p></div>
      <p v-if="item.no_answer_at" class="no-answer">Нет ответа: {{ date(item.no_answer_at) }}<span v-if="item.no_answer_count && item.no_answer_count > 1"> · Попыток: {{ item.no_answer_count }}</span><span v-if="item.next_followup_at"> · Следующий контакт: {{ date(item.next_followup_at) }}</span></p>
      <p v-if="isArchive && item.archive" class="decision"><strong>{{ outcomes[item.archive.outcome] || item.archive.outcome }}</strong><span v-if="item.archive.reason"> · {{ reasons[item.archive.reason] || item.archive.reason }}</span><span v-if="item.archive.note"> · {{ item.archive.note }}</span><small v-if="item.archive.archived_at">{{ date(item.archive.archived_at) }}<span v-if="item.archive.actor"> · {{ item.archive.actor }}</span></small></p>
      <p v-if="item.linked_order_id" class="decision">Связано с <a :href="`/manager/orders/kanban?orderId=${item.linked_order_id}`">заказом #{{ item.linked_order_id }}</a></p>
    </div>
    <div class="card-footer">
      <template v-if="!isArchive"><button type="button" class="inbox-button primary" title="Перевести в переговоры" @click="emit('qualify', item)">В переговоры</button><button type="button" class="inbox-button" :aria-expanded="refusing" @click="refusalMode = 'refusal'; refusing = !refusing; expanded = false">Не брать</button></template>
      <button v-else-if="!item.linked_order_id" type="button" class="inbox-button" @click="emit('restore', item)">Вернуть в работу</button>
      <button type="button" class="inbox-button subtle" :aria-expanded="expanded" :aria-controls="regionId" @click="toggleDetails">{{ expanded ? 'Скрыть подробности' : 'Подробнее' }}</button>
      <span class="read-status">{{ unread ? 'Не просмотрено' : 'Просмотрено' }}</span>
    </div>
    <p v-if="error" class="card-error" role="alert">{{ error }}<button v-if="expanded" type="button" @click="loadDetails">Повторить</button></p>
    <LeadRefusalPanel v-if="refusing" :order-id="item.id" :entity-kind="item.entity_kind" :mode="refusalMode" @cancel="refusing = false" @archived="emit('archived', item)" />
    <div v-if="expanded && detailLoading" class="detail-loading" role="status">Загружаем подробности…</div>
    <LeadInboxDetails v-else-if="expanded && detail" :item="current" :history="history" :contact-saving="contactSaving" @updated="sourceUpdated" @not-request="refusalMode = 'not_request'; refusing = true; expanded = false" @review-source="emit('review-source', $event)" @no-answer="emit('no-answer', $event)" @mark-unread="markUnread" @link-changed="emit('link-changed')" />
  </article>
</template>
<style scoped>
.inbox-card {
  border: 1px solid var(--inbox-border);
  border-radius: 11px;
  background: var(--inbox-card);
  overflow: hidden;
  box-shadow: 0 1px 2px #101c3010;
  scroll-margin: 15px;
}
.is-unread {
  border-left: 3px solid var(--inbox-blue);
}
.card-body {
  padding: 19px 21px 0;
}
.card-meta {
  display: flex;
  gap: 9px;
  align-items: center;
  font-size: 11px;
  color: var(--inbox-muted);
  flex-wrap: wrap;
}
.source {
  font-weight: 600;
}
.lead-id {
  opacity: .75;
}
.time {
  margin-left: auto;
}
.headline {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  margin-top: 9px;
}
.subject {
  min-width: 0;
  flex: 1;
}
h2 {
  margin: 0;
}
.title {
  font-size: 16px;
  font-weight: 680;
  line-height: 1.45;
  text-align: left;
  letter-spacing: -.18px;
  overflow-wrap: anywhere;
}
.title {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.title:hover,a {
  color: var(--inbox-blue);
}
.customer {
  font-size: 12px;
  color: var(--inbox-muted);
  margin: 5px 0 0;
  line-height: 1.6;
  overflow-wrap: anywhere;
}
.budget {
  flex-shrink: 0;
  text-align: right;
}
.budget small {
  display: block;
  font-size: 10px;
  color: var(--inbox-muted);
  margin-bottom: 4px;
}
.budget strong {
  font-size: 15px;
}
.facts {
  display: flex;
  gap: 8px 16px;
  flex-wrap: wrap;
  margin: 13px 0 10px;
  font-size: 12px;
  color: var(--inbox-muted);
  line-height: 1.5;
}
.facts button {
  color: var(--inbox-blue);
}
.deadline {
  color: #a75414;
  background: #fff5e7;
  border-radius: 4px;
  padding: 1px 6px;
}
.blurb {
  font-size: 12px;
  line-height: 1.65;
  margin: 10px 0 13px;
  color: var(--inbox-muted);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
}
.card-footer {
  padding: 13px 21px 16px;
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.read-status {
  font-size: 10px;
  color: var(--inbox-muted);
  margin-left: auto;
}
.terms-summary {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 12px;
  color: var(--inbox-muted);
  margin: 8px 0 12px;
  line-height: 1.6;
}
.related-requests {
  padding: 10px 12px;
  margin: 12px 0;
  background: var(--inbox-selected);
  border-left: 2px solid #91acd5;
  font-size: 12px;
  line-height: 1.6;
}
.related-requests p {
  margin: 0;
}
.decision,.no-answer {
  font-size: 12px;
  color: var(--inbox-muted);
  margin: 12px 0;
  line-height: 1.6;
}
.decision small {
  display: block;
  font-size: 11px;
}
.no-answer {
  color: #a75414;
}
.card-error,.detail-loading {
  padding: 14px 21px;
  font-size: 12px;
}
.card-error {
  color: #b94141;
}
.card-error button {
  text-decoration: underline;
  margin-left: 10px;
}
@media(max-width:760px) {
  .card-body {
    padding: 16px 15px 0;
  }
  .headline {
    flex-direction: column;
    gap: 10px;
  }
  .budget {
    text-align: left;
    display: flex;
    align-items: baseline;
    gap: 8px;
  }
  .budget small {
    margin: 0;
  }
  .title {
    font-size: 16px;
  }
  .card-footer {
    padding: 12px 15px 14px;
  }
  .time {
    font-size: 10px;
  }
  .read-status {
    font-size: 9px;
  }
}
</style>
