<script setup lang="ts">
import { computed } from 'vue';
import type { EnvelopeBranding, EnvelopeParty, EnvelopePreviewResponse } from '../../client';
import { envelopeFormats, type EnvelopeFormat } from './envelope-formats';

const props = defineProps<{ format: EnvelopeFormat; sender: EnvelopeParty; recipient: EnvelopeParty; normalized: EnvelopePreviewResponse | null; branding: EnvelopeBranding }>();
const pageStyle = computed(() => {
  const { width, height } = envelopeFormats[props.format];
  const horizontal = (mm: number) => `${100 * mm / width}%`;
  const vertical = (mm: number) => `${100 * mm / height}%`;
  return {
    aspectRatio: `${width} / ${height}`,
    '--margin-x': horizontal(8), '--sender-top': vertical(10),
    '--sender-width': horizontal(width / 2 - 16), '--recipient-width': horizontal(width / 2 - 8),
    '--recipient-bottom': vertical(14), '--brand-bottom': vertical(15),
    '--brand-width': horizontal(Math.min(82, width / 2 - 28)), '--brand-height': vertical(18),
    '--logo-width': `${2400 / Math.min(82, width / 2 - 28)}%`,
    '--brand-gap': `${400 / Math.min(82, width / 2 - 28)}%`,
    '--party-font': `${352.78 / width}cqi`, '--brand-font': `${317.5 / width}cqi`,
    '--stamp-font': `${264.58 / width}cqi`,
  };
});
</script>

<template>
  <div class="envelope-preview" :style="pageStyle" :aria-label="`Расположение адресов на конверте ${format}`">
    <div v-for="key in (['sender', 'recipient'] as const)" :key="key" :class="`preview-${key}`">
      <small>{{ key === 'sender' ? 'Отправитель' : 'Получатель' }}</small>
      <strong>{{ (key === 'sender' ? sender : recipient).name || 'Название / ФИО' }}</strong>
      <template v-if="normalized">
        <div v-for="(line, index) in normalized[key].delivery_lines" :key="`delivery-${index}`">{{ line }}</div>
        <div class="preview-postal"><b>{{ (key === 'sender' ? sender : recipient).postal_code }}</b>{{ normalized[key].postal_line.slice(6) }}</div>
        <div v-for="(line, index) in normalized[key].area_lines" :key="`area-${index}`">{{ line }}</div>
        <div>{{ normalized[key].country }}</div>
      </template>
      <template v-else><div>{{ (key === 'sender' ? sender : recipient).address || 'Адрес' }}</div><div>Индекс, населённый пункт</div><div>Республика Беларусь</div></template>
    </div>
    <div v-if="branding.name || branding.logo_data_url" class="preview-branding"><img v-if="branding.logo_data_url" :src="branding.logo_data_url" alt="Логотип" /><strong>{{ branding.name }}</strong></div>
    <span class="preview-stamp">Место для марки</span>
  </div>
</template>

<style scoped>
.envelope-preview { container-type: inline-size; position: relative; width: 100%; margin: 18px 0 12px; border: 1px solid #cbd5e1; background: white; color: #111; line-height: 1.28; overflow: hidden; }
.preview-sender, .preview-recipient { position: absolute; overflow-wrap: anywhere; font-size: var(--party-font); }
.preview-sender { left: var(--margin-x); top: var(--sender-top); width: var(--sender-width); }
.preview-recipient { left: 50%; bottom: var(--recipient-bottom); width: var(--recipient-width); }
small { display: block; margin-bottom: .6cqi; color: #475569; font-size: .7em; }
strong { display: block; font-weight: 700; }
.preview-postal b { font-size: 1.15em; }
.preview-branding { position: absolute; left: var(--margin-x); bottom: var(--brand-bottom); width: var(--brand-width); height: var(--brand-height); display: flex; align-items: center; gap: var(--brand-gap); font-size: var(--brand-font); }
.preview-branding img { width: var(--logo-width); height: 100%; flex-shrink: 0; object-fit: contain; object-position: left center; }
.preview-branding strong { flex: 1; overflow-wrap: anywhere; }
.preview-stamp { position: absolute; right: var(--margin-x); top: 8%; color: #94a3b8; font-size: var(--stamp-font); }
</style>
