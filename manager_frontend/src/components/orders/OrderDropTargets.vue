<script setup lang="ts">
import type { OrderBoardDrag } from '../../composables/useOrderBoardDrag';
const props = defineProps<{ drag: OrderBoardDrag }>();
const emit = defineEmits<{ move: [payload: { orderId: number; oldStatus: string; newStatus: string }] }>();
const targets = [{ key: 'closed_lost', label: 'Отказ' }, { key: 'closed_won', label: 'Завершить' }];
const drop = (target: string) => { const payload = props.drag.drop(target); if (payload) emit('move', payload); };
</script>

<template>
  <div v-if="drag.source.value" class="order-drop-targets" aria-label="Завершение заказа">
    <div v-for="target in targets" :key="target.key" :data-drop-status="target.key" :data-drop-active="drag.hover.value === target.key" :aria-disabled="!drag.allowed(target.key)" class="order-drop-target" :class="target.key === 'closed_lost' ? 'is-refusal' : 'is-success'"
      @dragenter="drag.enter($event, target.key)" @dragover="drag.over($event, target.key)" @dragleave="drag.leave($event, target.key)" @drop.stop.prevent="drop(target.key)">
      <span v-if="drag.hover.value === target.key" aria-hidden="true">↓ </span>{{ drag.hover.value === target.key ? `Отпустить: ${target.label.toLowerCase()}` : target.label }}
    </div>
  </div>
</template>

<style scoped>
.order-drop-targets { display:flex; min-width:0; gap:0.375rem; flex:1; }
.order-drop-target { display:flex; align-items:center; justify-content:center; flex:1; min-width:0; min-height:36px; padding:0.25rem 0.5rem; border:2px dashed; border-radius:0.5rem; font-size:0.8125rem; font-weight:700; text-align:center; }
.is-refusal { color:#9f1239; border-color:#fda4af; background:#fff1f2; }
.is-success { color:#065f46; border-color:#6ee7b7; background:#ecfdf5; }
.order-drop-target[data-drop-active="true"] { border-style:solid; outline:3px solid currentColor; outline-offset:1px; }
.is-refusal[data-drop-active="true"] { color:#fff; background:#be123c; border-color:#9f1239; outline-color:#fb7185; }
.is-success[data-drop-active="true"] { color:#fff; background:#047857; border-color:#065f46; outline-color:#34d399; }
.order-drop-target[aria-disabled="true"] { opacity:0.45; }
</style>
