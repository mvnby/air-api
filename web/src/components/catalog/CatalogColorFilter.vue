<script setup>
defineProps({
  value: {
    type: String,
    default: null,
  },
});

defineEmits(['toggle']);
</script>

<template>
  <div class="advanced-row">
    <div class="control-label">Цвет корпуса</div>
    <div class="quick-chip-row">
      <button
        class="quick-chip color-chip"
        :class="{ active: value === 'black' }"
        :aria-pressed="value === 'black'"
        @click="$emit('toggle', 'black')"
      >
        <span class="color-swatch" aria-hidden="true" />
        Черный
      </button>
    </div>
  </div>
</template>

<style scoped>
.advanced-row {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
  margin-top: 0.9rem;
}

.control-label {
  color: var(--text-muted);
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.quick-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}

.quick-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.48rem;
  padding: 0.48rem 0.9rem;
  border: 1px solid var(--panel-chip-border);
  border-radius: 999px;
  background: var(--panel-chip-bg);
  color: var(--text);
  font-size: 0.88rem;
  font-weight: 700;
  cursor: pointer;
  transition: transform 0.18s ease, border-color 0.2s ease, background 0.2s ease;
}

.quick-chip:hover {
  border-color: var(--panel-chip-hover-border);
  transform: translateY(-1px);
}

.quick-chip.active {
  border-color: transparent;
  background: var(--panel-active-gradient-alt);
  color: var(--panel-active-text);
}

.color-swatch {
  flex: 0 0 16px;
  width: 16px;
  height: 16px;
  border: 1px solid var(--panel-chip-border);
  border-radius: 50%;
  background: #111318;
  box-shadow: 0 0 0 2px var(--panel-chip-bg);
}

.quick-chip.active .color-swatch {
  border-color: var(--panel-active-text);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--panel-active-text) 22%, transparent);
}

@media (prefers-reduced-motion: reduce) {
  .quick-chip {
    transition: none;
  }

  .quick-chip:hover {
    transform: none;
  }
}
</style>
