<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import { Download, X } from 'lucide-vue-next';
import { api } from '../../api';
import { ManagerDocumentSystemService, ManagerService, type DocumentLegalEntityItem, type EnvelopeBranding, type EnvelopeParty, type EnvelopePreviewResponse, type ManagerCatalogCustomerItemResponse } from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
import { envelopeAddresses, splitPostalAddress } from './envelope-addresses';
import { downloadEnvelope } from './envelope-print-api';
import PostcodeLookup from './PostcodeLookup.vue';
import EnvelopePreview from './EnvelopePreview.vue';
import EnvelopeBrandingFields from './EnvelopeBrandingFields.vue';
import { envelopeFormats, type EnvelopeFormat } from './envelope-formats';

const props = defineProps<{ customerId: number; orderAddress?: string }>();
const emit = defineEmits<{ close: [] }>();
const customer = ref<ManagerCatalogCustomerItemResponse | null>(null);
const entities = ref<DocumentLegalEntityItem[]>([]);
const selectedEntity = ref('');
const selectedAddress = ref('');
const format = ref<EnvelopeFormat>('DL');
const size = computed(() => envelopeFormats[format.value]);
const recipient = reactive<EnvelopeParty>({ name: '', address: '', postal_code: '' });
const sender = reactive<EnvelopeParty>({ name: '', address: '', postal_code: '' });
const branding = ref<EnvelopeBranding>({ name: '', logo_data_url: null });
const logoLoading = ref(false);
const normalized = ref<EnvelopePreviewResponse | null>(null);
const previewError = ref('');
let previewTimer: ReturnType<typeof setTimeout> | undefined;
let previewVersion = 0;
const loading = ref(true);
const busy = ref(false);
const error = ref('');
const senderWarning = ref('');
const dialog = ref<HTMLElement | null>(null);
const previousFocus = document.activeElement as HTMLElement | null;
const previousOverflow = document.body.style.overflow;
let alive = true;
const addresses = computed(() => customer.value ? envelopeAddresses(customer.value, props.orderAddress) : []);
const missing = computed(() => {
  const fields: string[] = [];
  for (const [party, label] of [[recipient, 'получателя'], [sender, 'отправителя']] as const) {
    if (!party.name.trim()) fields.push(`название / ФИО ${label}`);
    if (!party.address.trim()) fields.push(`адрес ${label}`);
    if (!/^[0-9]{6}$/.test(party.postal_code)) fields.push(`индекс ${label} (6 цифр)`);
  }
  return fields;
});
function chooseAddress() {
  if (selectedAddress.value === 'custom') return;
  Object.assign(recipient, splitPostalAddress(addresses.value.find(item => item.id === selectedAddress.value)?.address || ''));
}
function manualAddress() { selectedAddress.value = 'custom'; }
function chooseSender() {
  const entity = entities.value.find(item => String(item.id) === selectedEntity.value);
  sender.name = entity?.legal_name || entity?.display_name || '';
  Object.assign(sender, splitPostalAddress(entity?.requisites.legal_address || ''));
  branding.value = { name: entity?.envelope_branding?.name || '', logo_data_url: entity?.envelope_branding?.logo_data_url || null };
}
function extractIndex(party: EnvelopeParty) {
  const parsed = splitPostalAddress(party.address);
  if (parsed.postal_code && (!party.postal_code || party.postal_code === parsed.postal_code)) Object.assign(party, parsed);
}
async function load() {
  loading.value = true; error.value = ''; senderWarning.value = '';
  const [detail, issuers] = await Promise.allSettled([
    api.getManagerCustomerDetail(props.customerId),
    ManagerDocumentSystemService.listManagerDocumentLegalEntities(),
  ]);
  if (!alive) return;
  if (detail.status === 'rejected') { error.value = getApiErrorMessage(detail.reason); loading.value = false; return; }
  customer.value = detail.value;
  recipient.name = detail.value.full_legal_name || detail.value.name || '';
  selectedAddress.value = addresses.value.length === 1 ? addresses.value[0]!.id : addresses.value.length ? '' : 'custom';
  chooseAddress();
  if (issuers.status === 'fulfilled') {
    entities.value = issuers.value.items.filter(item => item.status === 'active');
    selectedEntity.value = String(entities.value.find(item => item.is_default)?.id || entities.value[0]?.id || '');
    chooseSender();
  } else senderWarning.value = 'Не удалось загрузить отправителей. Заполните данные вручную.';
  loading.value = false;
}
async function generate() {
  if (loading.value || busy.value || logoLoading.value || !customer.value || missing.value.length) return;
  busy.value = true; error.value = '';
  const printFormat = format.value;
  try {
    const blob = await downloadEnvelope(props.customerId, { format: printFormat, sender: { ...sender }, recipient: { ...recipient }, branding: { ...branding.value } });
    if (!alive) return;
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url; link.download = `envelope-${printFormat.toLowerCase()}-${props.customerId}.pdf`;
    document.body.append(link); link.click(); link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
  } catch (e) { if (alive) error.value = getApiErrorMessage(e); }
  finally { if (alive) busy.value = false; }
}
watch(() => JSON.stringify([sender, recipient, missing.value]), () => {
  clearTimeout(previewTimer);
  const version = ++previewVersion;
  normalized.value = null; previewError.value = '';
  if (missing.value.length) return;
  const payload = { sender: { ...sender }, recipient: { ...recipient } };
  previewTimer = setTimeout(async () => {
    try {
      const result = await ManagerService.previewManagerCustomerEnvelope(props.customerId, payload);
      if (alive && version === previewVersion) normalized.value = result;
    } catch { if (alive && version === previewVersion) previewError.value = 'Не удалось обновить предпросмотр. Порядок строк будет проверен при формировании PDF.'; }
  }, 250);
});
function close() { if (!busy.value) emit('close'); }
function keydown(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.stopPropagation(); event.preventDefault(); close(); }
  if (event.key !== 'Tab') return;
  const elements = [...(dialog.value?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), a[href]') || [])];
  const first = elements[0], last = elements[elements.length - 1];
  if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.value)) { event.preventDefault(); last?.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
}
onMounted(async () => { document.body.style.overflow = 'hidden'; await nextTick(); dialog.value?.focus(); void load(); });
onUnmounted(() => { alive = false; clearTimeout(previewTimer); document.body.style.overflow = previousOverflow; previousFocus?.focus(); });
</script>

<template>
  <Teleport to="body">
    <div class="envelope-overlay" @click.self="close">
      <section ref="dialog" role="dialog" aria-modal="true" aria-labelledby="envelope-title" tabindex="-1" class="envelope-dialog" @keydown="keydown">
        <header><div><h2 id="envelope-title">Печать конверта</h2><p>{{ format }} · {{ size.width }} × {{ size.height }} мм · Беларусь</p></div><button type="button" aria-label="Закрыть печать конверта" :disabled="busy" @click="close"><X :size="20" /></button></header>
        <p v-if="loading" role="status">Загрузка адресов…</p>
        <p v-if="error" role="alert" class="envelope-error">{{ error }} <button v-if="!customer && !loading" type="button" @click="load">Повторить</button></p>
        <form v-if="customer && !loading" @submit.prevent="generate">
          <label for="envelope-format">Формат конверта<select id="envelope-format" v-model="format" :disabled="busy"><option v-for="(item, code) in envelopeFormats" :key="code" :value="code">{{ code }} · {{ item.width }} × {{ item.height }} мм — {{ item.description }}</option></select></label>
          <div class="envelope-fields">
            <fieldset :disabled="busy"><legend>Получатель</legend>
              <label v-if="addresses.length" for="envelope-address">Адрес из карточки<select id="envelope-address" v-model="selectedAddress" @change="chooseAddress"><option value="" disabled>Выберите адрес или введите ниже</option><option v-for="item in addresses" :key="item.id" :value="item.id">{{ item.label }}: {{ item.address }}</option><option value="custom">Другой адрес — ввести вручную</option></select></label>
              <label for="envelope-recipient-name">Название / ФИО<input id="envelope-recipient-name" v-model="recipient.name" required maxlength="300" /></label>
              <label for="envelope-recipient-address">Адрес без индекса<textarea id="envelope-recipient-address" v-model="recipient.address" required maxlength="600" rows="3" @input="manualAddress" @blur="extractIndex(recipient)" /></label>
              <label for="envelope-recipient-index">Почтовый индекс<input id="envelope-recipient-index" v-model="recipient.postal_code" required inputmode="numeric" pattern="[0-9]{6}" maxlength="6" placeholder="6 цифр" /></label>
              <PostcodeLookup :customer-id="customerId" :address="recipient.address" :disabled="busy" @selected="recipient.postal_code = $event" />
            </fieldset>
            <fieldset :disabled="busy"><legend>Отправитель</legend>
              <label v-if="entities.length" for="envelope-sender">Наши реквизиты<select id="envelope-sender" v-model="selectedEntity" @change="chooseSender"><option v-for="entity in entities" :key="entity.id" :value="String(entity.id)">{{ entity.display_name }}</option><option value="">Другой отправитель</option></select></label>
              <p v-if="senderWarning" role="status">{{ senderWarning }}</p>
              <label for="envelope-sender-name">Название / ФИО<input id="envelope-sender-name" v-model="sender.name" required maxlength="300" /></label>
              <label for="envelope-sender-address">Адрес без индекса<textarea id="envelope-sender-address" v-model="sender.address" required maxlength="600" rows="3" @blur="extractIndex(sender)" /></label>
              <label for="envelope-sender-index">Почтовый индекс<input id="envelope-sender-index" v-model="sender.postal_code" required inputmode="numeric" pattern="[0-9]{6}" maxlength="6" placeholder="6 цифр" /></label>
              <PostcodeLookup :customer-id="customerId" :address="sender.address" :disabled="busy" @selected="sender.postal_code = $event" />
            </fieldset>
          </div>
          <EnvelopeBrandingFields :key="selectedEntity" v-model="branding" :disabled="busy" @loading="logoLoading = $event" />
          <EnvelopePreview :format="format" :sender="sender" :recipient="recipient" :normalized="normalized" :branding="branding" />
          <p v-if="previewError" role="status" class="envelope-hint">{{ previewError }}</p>
          <template v-if="normalized"><p v-for="(warning, index) in normalized.recipient.warnings" :key="`r-${index}`" role="status" class="envelope-hint">Получатель: {{ warning }}</p><p v-for="(warning, index) in normalized.sender.warnings" :key="`s-${index}`" role="status" class="envelope-hint">Отправитель: {{ warning }}</p></template>
          <p class="envelope-hint">В настройках принтера выберите размер {{ size.width }} × {{ size.height }} мм ({{ format }}), альбомную ориентацию и масштаб 100%, без подгонки под страницу. Перед тиражом проверьте подачу на одном конверте.</p>
          <p class="envelope-hint">Изменения в этом окне используются только для печати.</p>
          <p v-if="missing.length" role="status" class="envelope-missing">Укажите: {{ missing.join('; ') }}.</p>
          <footer><button type="button" class="btn-mini-outline" :disabled="busy" @click="close">Закрыть</button><button type="submit" class="btn-mini" :disabled="busy || logoLoading || missing.length > 0"><Download :size="15" />{{ busy ? 'Формирование…' : 'Скачать PDF для печати' }}</button></footer>
        </form>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.envelope-overlay { position: fixed; inset: 0; z-index: 10000; display: grid; place-items: center; padding: 16px; background: rgb(15 23 42 / 45%); }
.envelope-dialog { width: min(760px, 100%); max-height: calc(100dvh - 32px); overflow-y: auto; padding: 22px; border-radius: 16px; background: var(--mv-surface, white); color: var(--mv-text, #0f172a); box-shadow: 0 20px 60px #0003; }
header { display: flex; align-items: start; justify-content: space-between; gap: 12px; margin-bottom: 18px; } h2 { font-size: 18px; font-weight: 600; } header p, .envelope-hint { color: var(--mv-text-muted, #64748b); font-size: 12px; margin-top: 5px; } header button { padding: 5px; }
.envelope-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 22px; } fieldset { min-width: 0; } legend { font-weight: 600; font-size: 14px; margin-bottom: 10px; } label { display: block; font-size: 12px; margin-bottom: 10px; } input, textarea, select { display: block; width: 100%; margin-top: 4px; padding: 8px 10px; border: 1px solid var(--mv-border, #cbd5e1); border-radius: 7px; background: var(--mv-surface, white); color: inherit; font: inherit; font-size: 13px; } textarea { resize: vertical; } a { font-size: 12px; color: var(--kitlane-accent-text, #2563eb); } button:disabled { opacity: .5; cursor: default; }
.envelope-error { color: #dc2626; margin: 10px 0; font-size: 13px; } .envelope-missing { margin-top: 10px; color: var(--mv-text-muted, #64748b); font-size: 12px; } footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 18px; } footer button { display: inline-flex; align-items: center; gap: 6px; }
@media (max-width: 600px) { .envelope-fields { grid-template-columns: 1fr; gap: 18px; } .envelope-dialog { padding: 16px; } footer { flex-wrap: wrap; } }
</style>
