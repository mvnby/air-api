<script setup lang="ts">
import { computed } from 'vue';
import type { ManagerCatalogCustomerItemResponse } from '../../client';
import { customerCompleteness, type SavedContacts } from './customer-completeness';
const props = defineProps<{ customer: ManagerCatalogCustomerItemResponse; contacts?: SavedContacts | null }>();
const groups = computed(() => customerCompleteness(props.customer, props.contacts));
</script>
<template>
  <section class="customer-completeness" aria-label="Заполненность досье">
    <h2>Заполненность досье</h2>
    <p class="explanation">Подсказка по сохранённым данным досье. Неполную карточку можно сохранять. Наличие полей не подтверждает достоверность. Требования документа определяются действием и шаблоном.</p>
    <dl>
      <div v-for="group in groups" :key="group.id" :data-completeness="group.id">
        <dt>{{ group.label }}</dt>
        <dd>{{ !group.applicable ? 'Не требуется для физлица' : group.missing.length ? `Не указаны: ${group.missing.join(', ')}` : group.note && group.id === 'contacts' ? 'Сведения о контактах ещё не загружены' : 'Поля заполнены' }}<small v-if="group.applicable && group.note">{{ group.note }}</small></dd>
      </div>
    </dl>
  </section>
</template>
<style scoped>
.customer-completeness { margin: 12px 0; padding: 12px 16px; border: 1px solid var(--mv-border); border-radius: 10px; background: var(--mv-surface); }
h2 { font-size: 13px; font-weight: 600; }
.explanation { margin-top: 4px; font-size: 12px; color: var(--mv-text-muted); }
dl { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px 18px; margin-top: 10px; }
dl > div { min-width: 0; overflow-wrap: anywhere; }
dt { font-size: 12px; font-weight: 600; }
dd { margin-top: 2px; font-size: 12px; color: var(--mv-text-muted); }
small { display: block; margin-top: 3px; font-size: 11px; }
@media (max-width: 1000px) { dl { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 600px) { dl { grid-template-columns: minmax(0, 1fr); gap: 8px; }.customer-completeness { padding: 12px; } }
</style>
