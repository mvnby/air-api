<script setup lang="ts">
import { computed, ref } from 'vue';
import type { InboxItem, InboxHistory, InboxContactRequest } from '../../services/lead-inbox';
import OrderAttachmentsPanel from '../service-attachments/OrderAttachmentsPanel.vue';
import EmailOriginals from './EmailOriginals.vue';
import EmailContractReviewLauncher from './EmailContractReviewLauncher.vue';
import EmailLeadOrderLink from './EmailLeadOrderLink.vue';
import EmailLeadTenderContext from './EmailLeadTenderContext.vue';
import CommercialTermsPanel from '../orders/CommercialTermsPanel.vue';
import TenderWorkflowPanel from '../orders/TenderWorkflowPanel.vue';
const props = defineProps<{ item: InboxItem; history: InboxHistory[]; contactSaving?: boolean }>();
const emit = defineEmits<{ (e: 'review-source', item: InboxItem): void; (e: 'no-answer', request: InboxContactRequest): void; (e: 'link-changed'): void; (e: 'mark-unread', item: InboxItem): void; (e: 'not-request'): void; (e: 'updated', item: InboxItem, history: InboxHistory[]): void }>();
const date = (value: string) => new Date(value).toLocaleString('ru-RU', { timeZone: 'Europe/Minsk', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
const tenderUrl = computed(() => { try { const url = new URL(props.item.tender?.url || ''); return ['http:', 'https:'].includes(url.protocol) ? url.href : null; } catch { return null; } });
const followup = ref('');
const contactNote = ref('');
const submitNoAnswer = () => emit('no-answer', { item: props.item, note: contactNote.value.trim() || undefined, nextFollowupAt: followup.value ? new Date(`${followup.value}+03:00`).toISOString() : undefined });
const historyLabels: Record<string, string> = { no_answer: 'Нет ответа', archive: 'В архив', restore: 'Возвращено в работу', tender_context: 'Контекст тендера обновлён' };
</script>
<template>
  <div class="lead-details" :id="`lead-details-${item.entity_kind || 'order'}-${item.id}`" role="region" :aria-label="`Подробности обращения #${item.id}`">
    <div class="details-grid">
      <div><h3>{{ item.original_text ? 'Исходный запрос' : 'Описание обращения' }}</h3><p class="whitespace-pre-line">{{ item.original_text || item.comment || item.summary || 'Текст запроса не указан' }}</p><p v-if="item.original_text_truncated" class="context-note">Показана часть исходного текста. Полный запрос доступен в оригинале.</p>
        <div class="contacts"><a v-if="item.phone" :href="`tel:${item.phone}`">{{ item.phone }}</a><a v-if="item.email" :href="`mailto:${item.email}`">{{ item.email }}</a><span v-if="item.customer_inn">УНП {{ item.customer_inn }}</span></div>
        <div v-if="item.tender" class="tender-context"><span v-if="item.tender.source">Площадка: {{ item.tender.source }}</span><span v-if="item.tender.profile_name">Профиль: {{ item.tender.profile_name }}</span><span v-if="item.tender.reason">Причина: {{ item.tender.reason }}</span><a v-if="tenderUrl" :href="tenderUrl" target="_blank" rel="noopener noreferrer">Открыть закупку</a></div>
        <EmailLeadTenderContext v-if="item.entity_kind !== 'lead' && item.source === 'email' && !item.archive && !item.linked_order_id" :item="item" @updated="(updated, history) => emit('updated', updated, history)" />
        <TenderWorkflowPanel v-if="item.entity_kind !== 'lead' && (item.source === 'email' || item.source === 'belzakupki') && !item.linked_order_id" :order-id="item.id" @changed="emit('link-changed')" />
      </div>
      <div v-if="item.entity_kind !== 'lead'">
        <h3>Документы и данные</h3>
        <div v-if="item.attachment_count" data-testid="lead-readonly-attachments" :id="`lead-attachments-${item.id}`"><OrderAttachmentsPanel :order-id="item.id" :initial-count="item.attachment_count" :default-expanded="true" :readonly="true" :embedded="true" /></div>
        <EmailOriginals v-if="item.source === 'email' && !item.attachment_count" :order-id="item.id" />
        <EmailContractReviewLauncher v-if="item.source === 'email'" :order-id="item.id" />
        <CommercialTermsPanel v-if="item.source === 'email' || item.source === 'belzakupki'" :order-id="item.id" :email-source="item.source === 'email'" />
      </div>
    </div>
    <EmailLeadOrderLink v-if="item.entity_kind !== 'lead' && item.source === 'email' && (item.status === 'new_lead' || item.linked_order_id)" :source-order-id="item.id" :linked-order-id="item.linked_order_id" @changed="emit('link-changed')" />
    <p v-if="item.source === 'email' && !item.linked_order_id" class="context-note">Если это продолжение переписки по существующему заказу, привяжите письмо к нему.</p>
    <div class="detail-actions">
      <button v-if="item.entity_kind !== 'lead' && item.source === 'belzakupki' && !item.archive" type="button" title="Проверить данные из закупки перед созданием сделки" @click="emit('review-source', item)">Проработать источник</button>
      <button v-if="!item.archive && !item.linked_order_id" type="button" @click="emit('not-request')">Это не новая заявка</button>
      <button type="button" @click="emit('mark-unread', item)">Пометить непросмотренным</button>
    </div>
    <form v-if="!item.archive && !item.linked_order_id" class="contact-attempt" @submit.prevent="submitNoAnswer">
      <div class="contact-fields"><label :for="`next-contact-${item.entity_kind || 'order'}-${item.id}`">Следующий контакт (Минск, необязательно)<input :id="`next-contact-${item.entity_kind || 'order'}-${item.id}`" v-model="followup" type="datetime-local" :disabled="contactSaving" /></label><label :for="`contact-note-${item.entity_kind || 'order'}-${item.id}`">Заметка к попытке (необязательно)<input :id="`contact-note-${item.entity_kind || 'order'}-${item.id}`" v-model="contactNote" type="text" maxlength="2000" :disabled="contactSaving" /></label></div>
      <button class="inbox-button" type="submit" :disabled="contactSaving">{{ contactSaving ? 'Сохраняем…' : 'Нет ответа · оставить в работе' }}</button>
    </form>
    <div v-if="history.length" class="history"><h3>История действий</h3><p v-for="event in history" :key="event.id">{{ date(event.created_at) }} · {{ historyLabels[event.kind] || event.kind }}<span v-if="event.actor"> · {{ event.actor }}</span><span v-if="event.note"> · {{ event.note }}</span></p></div>
  </div>
</template>
<style scoped>
.lead-details {
  padding: 18px 21px;
  border-top: 1px solid var(--inbox-border);
  background: var(--inbox-detail);
  font-size: 12px;
  line-height: 1.65;
}
.details-grid {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 22px;
  min-width: 0;
}
.details-grid>div {
  min-width: 0;
}
h3 {
  font-size: 12px;
  font-weight: 650;
  margin: 0 0 7px;
}
p {
  margin: 0 0 14px;
  color: var(--inbox-muted);
}
.contacts,.tender-context,.detail-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.tender-context {
  margin-top: 12px;
}
.detail-actions,.history {
  border-top: 1px solid var(--inbox-border);
  padding-top: 13px;
  margin-top: 14px;
}
.detail-actions button,a {
  color: var(--inbox-blue);
  text-decoration: underline;
  text-underline-offset: 3px;
}
.detail-actions button {
  min-height: 36px;
}
.context-note {
  font-size: 11px;
  margin-top: 12px;
}
.contact-attempt {
  border-top: 1px solid var(--inbox-border);
  margin-top: 14px;
  padding-top: 13px;
}
.contact-fields {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.contact-fields label {
  flex: 1;
  min-width: 220px;
  color: var(--inbox-muted);
  font-size: 11px;
}
.contact-fields input {
  display: block;
  margin-top: 5px;
  width: 100%;
  border: 1px solid var(--inbox-border);
  border-radius: 6px;
  padding: 9px;
  background: var(--inbox-card);
  color: inherit;
  font-size: 12px;
}
.history p {
  margin: 4px 0;
}
@media(max-width:760px) {
  .details-grid {
    grid-template-columns: 1fr;
  }
  .lead-details {
    padding: 17px 15px;
  }
}
</style>
