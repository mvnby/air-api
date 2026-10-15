<script setup lang="ts">
import type { EnvelopeBranding, EnvelopeParty, EnvelopePreviewResponse } from '../../client';

defineProps<{ sender: EnvelopeParty; recipient: EnvelopeParty; normalized: EnvelopePreviewResponse | null; branding: EnvelopeBranding }>();
</script>

<template>
  <div class="envelope-preview" aria-label="Расположение адресов на конверте">
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
.envelope-preview { container-type: inline-size; position: relative; width: 100%; aspect-ratio: 2; margin: 18px 0 12px; border: 1px solid #cbd5e1; background: white; color: #111; font-size: clamp(5px, 1.5cqi, 12px); line-height: 1.28; overflow: hidden; }
.preview-sender, .preview-recipient { position: absolute; overflow-wrap: anywhere; font-size: 1.6cqi; }
.preview-sender { left: 3.64%; top: 11.8%; width: 42.7%; }
.preview-recipient { left: 50%; bottom: 12.73%; width: 46.36%; }
small { display: block; margin-bottom: .6cqi; color: #475569; font-size: .7em; }
strong { display: block; font-weight: 700; }
.preview-postal b { font-size: 1.15em; }
.preview-branding { position: absolute; left: 3.64%; bottom: 13.64%; width: 37.27%; height: 16.36%; display: flex; align-items: center; gap: 4.88%; font-size: 1.44cqi; }
.preview-branding img { width: 29.3%; height: 100%; flex-shrink: 0; object-fit: contain; object-position: left center; }
.preview-branding strong { flex: 1; overflow-wrap: anywhere; }
.preview-stamp { position: absolute; right: 3.64%; top: 8%; color: #94a3b8; font-size: 1.2cqi; }
</style>
