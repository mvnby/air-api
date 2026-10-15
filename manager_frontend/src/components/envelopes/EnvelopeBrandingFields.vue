<script setup lang="ts">
import { onUnmounted, ref } from 'vue';
import type { EnvelopeBranding } from '../../client';

const props = withDefaults(defineProps<{ modelValue: EnvelopeBranding; disabled: boolean; idPrefix?: string; expanded?: boolean }>(), { idPrefix: 'envelope-brand', expanded: false });
const emit = defineEmits<{ 'update:modelValue': [value: EnvelopeBranding]; loading: [value: boolean] }>();
const error = ref('');
const loading = ref(false);
let selection = 0;
function setLoading(value: boolean) { loading.value = value; emit('loading', value); }
async function chooseLogo(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  const current = ++selection;
  input.value = '';
  error.value = '';
  setLoading(false);
  if (!file) return;
  if (!['image/png', 'image/jpeg'].includes(file.type) || file.size > 256 * 1024) {
    error.value = 'Выберите PNG или JPEG не больше 256 КБ.'; return;
  }
  setLoading(true);
  try {
    const data = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsDataURL(file);
    });
    const image = new Image(); image.src = data; await image.decode();
    if (current !== selection) return;
    if (Math.max(image.naturalWidth, image.naturalHeight) > 2000) { error.value = 'Размер логотипа — до 2000 × 2000 пикселей.'; return; }
    emit('update:modelValue', { ...props.modelValue, logo_data_url: data });
  } catch { if (current === selection) error.value = 'Не удалось прочитать изображение.'; }
  finally { if (current === selection) setLoading(false); }
}
function removeLogo() { selection++; setLoading(false); emit('update:modelValue', { ...props.modelValue, logo_data_url: null }); }
onUnmounted(() => { selection++; setLoading(false); });
</script>

<template>
  <details class="branding-fields" :open="expanded"><summary>Логотип и название внизу слева</summary>
    <fieldset :disabled="disabled">
      <label :for="`${idPrefix}-name`">Название организации (необязательно)<input :id="`${idPrefix}-name`" :value="modelValue.name" maxlength="100" @input="emit('update:modelValue', { ...modelValue, name: ($event.target as HTMLInputElement).value })" /></label>
      <label :for="`${idPrefix}-logo`">Логотип · PNG или JPEG до 256 КБ<input :id="`${idPrefix}-logo`" type="file" accept="image/png,image/jpeg" @change="chooseLogo" /></label>
      <p v-if="loading" role="status">Загрузка логотипа…</p>
      <button v-if="modelValue.logo_data_url" type="button" class="btn-mini-outline" @click="removeLogo">Убрать логотип</button>
      <p v-if="error" role="alert" class="branding-error">{{ error }}</p>
    </fieldset>
  </details>
</template>

<style scoped>
.branding-fields { font-size: 12px; margin-top: 16px; } summary { cursor: pointer; color: var(--mv-text-muted, #64748b); } fieldset { margin-top: 12px; } label { display: block; margin: 10px 0; } input { display: block; width: 100%; margin-top: 4px; padding: 8px 10px; border: 1px solid var(--mv-border, #cbd5e1); border-radius: 7px; background: var(--mv-surface, white); color: inherit; } p { color: var(--mv-text-muted, #64748b); margin-top: 8px; } .branding-error { color: #dc2626; }
</style>
