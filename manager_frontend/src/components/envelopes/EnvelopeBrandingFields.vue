<script setup lang="ts">
import { ref } from 'vue';
import type { EnvelopeBranding } from '../../client';

const props = defineProps<{ modelValue: EnvelopeBranding; disabled: boolean }>();
const emit = defineEmits<{ 'update:modelValue': [value: EnvelopeBranding] }>();
const error = ref('');
let selection = 0;
async function chooseLogo(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  const current = ++selection;
  input.value = '';
  error.value = '';
  if (!file) return;
  if (!['image/png', 'image/jpeg'].includes(file.type) || file.size > 256 * 1024) {
    error.value = 'Выберите PNG или JPEG не больше 256 КБ.'; return;
  }
  try {
    const data = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsDataURL(file);
    });
    const image = new Image(); image.src = data; await image.decode();
    if (current !== selection) return;
    if (Math.max(image.naturalWidth, image.naturalHeight) > 2000) { error.value = 'Размер логотипа — до 2000 × 2000 пикселей.'; return; }
    emit('update:modelValue', { ...props.modelValue, logo_data_url: data });
  } catch { if (current === selection) error.value = 'Не удалось прочитать изображение.'; }
}
function removeLogo() { selection++; emit('update:modelValue', { ...props.modelValue, logo_data_url: null }); }
</script>

<template>
  <details class="branding-fields"><summary>Логотип и название внизу слева</summary>
    <fieldset :disabled="disabled">
      <label for="envelope-brand-name">Название организации (необязательно)<input id="envelope-brand-name" :value="modelValue.name" maxlength="100" @input="emit('update:modelValue', { ...modelValue, name: ($event.target as HTMLInputElement).value })" /></label>
      <label for="envelope-brand-logo">Логотип · PNG или JPEG до 256 КБ<input id="envelope-brand-logo" type="file" accept="image/png,image/jpeg" @change="chooseLogo" /></label>
      <button v-if="modelValue.logo_data_url" type="button" class="btn-mini-outline" @click="removeLogo">Убрать логотип</button>
      <p v-if="error" role="alert">{{ error }}</p>
    </fieldset>
  </details>
</template>

<style scoped>
.branding-fields { font-size: 12px; margin-top: 16px; } summary { cursor: pointer; color: var(--mv-text-muted, #64748b); } fieldset { margin-top: 12px; } label { display: block; margin: 10px 0; } input { display: block; width: 100%; margin-top: 4px; padding: 8px 10px; border: 1px solid var(--mv-border, #cbd5e1); border-radius: 7px; background: var(--mv-surface, white); color: inherit; } p { color: #dc2626; margin-top: 8px; }
</style>
