<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { ManagerService, type ManagerCustomerDocumentItem } from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
const props = defineProps<{ customerId: number }>();
const items = ref<ManagerCustomerDocumentItem[]>([]);
const loading = ref(true);
const error = ref('');
const names: Record<string,string> = { act: 'Акт', service_act: 'Акт оказанных услуг', maintenance_service_act: 'Акт обслуживания', contract: 'Договор', invoice: 'Счёт', tn2: 'Накладная', ttn1: 'ТТН', retail_receipt: 'Товарный чек', reconciliation: 'Акт сверки' };
const identityLabel = (doc: ManagerCustomerDocumentItem) => `${names[doc.doc_type] || doc.doc_type} ${doc.identity_source === 'unverified_legacy' ? '· внутр. №' : '№'} ${doc.number}`;
async function load() { loading.value = true; error.value = ''; try { items.value = (await ManagerService.getManagerCustomerDocs(props.customerId)).items; } catch(e) { error.value = getApiErrorMessage(e); } finally { loading.value = false; } }
onMounted(load);
</script>
<template>
  <section class="customer-panel"><div class="panel-heading"><h2>Документы <span class="muted text-xs font-normal">{{ items.length || '' }}</span></h2><button class="workspace-link" type="button" :disabled="loading" @click="load">Обновить</button></div>
    <p v-if="loading" class="muted text-sm">Загрузка документов…</p><p v-else-if="error" role="alert" class="request-error">{{ error }}</p>
    <ul v-else-if="items.length" class="document-list"><li v-for="doc in items" :key="doc.id"><div><a v-if="doc.edit_url" :href="doc.edit_url" target="_blank" rel="noopener noreferrer" class="workspace-link font-semibold">{{ identityLabel(doc) }}</a><strong v-else>{{ identityLabel(doc) }}</strong><p class="muted text-xs mt-1">{{ new Date(doc.date).toLocaleDateString('ru-RU') }}<span v-if="doc.identity_source === 'unverified_legacy'"> · Реквизиты оригинала не проверены</span></p></div><a :href="`/manager/orders/kanban?orderId=${doc.order_id}`" class="workspace-link whitespace-nowrap">Заказ #{{ doc.order_id }} ↗</a></li></ul><p v-else class="empty">Документов пока нет.</p>
  </section>
</template>
<style scoped src="../../styles/customer-workspace.css"></style>
<style scoped>.document-list li { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 0; border-top: 1px solid var(--mv-border); min-width: 0; }.document-list li div { min-width: 0; overflow-wrap: anywhere; }</style>
