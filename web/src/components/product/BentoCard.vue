<template>
  <div :class="['bento-card', `layout-${card.layout}`, `style-${card.style_hint || 'default'}`]">
    
    <!-- Background Watermark Icon (Wide Layout) -->
    <div v-if="isWide && isMaterialIcon" class="watermark-icon">
        <span class="material-icons-round">{{ card.icon }}</span>
    </div>

    <!-- Main Content -->
    <div class="card-content relative z-10 h-full flex flex-col">
      <div class="card-header mb-4">
        <!-- Icon (for normal/small layouts or img icons) -->
        <div v-if="!isWide || !isMaterialIcon" class="card-icon-wrapper mb-3">
             <span v-if="isMaterialIcon" class="material-icons-round card-icon">{{ card.icon }}</span>
             <img v-else :src="card.icon" class="card-img-icon" alt="" />
        </div>

        <h3 class="card-title">{{ card.title }}</h3>
        <p v-if="card.subtitle" class="card-subtitle">{{ card.subtitle }}</p>
      </div>

      <!-- Items Grid (Value/Label pairs) -->
      <div v-if="card.items && card.items.length" class="card-items">
        <div v-for="(item, idx) in card.items" :key="idx" class="card-item">
            <span class="item-label">{{ item.label }}</span>
          <span class="item-value">{{ item.value }}</span>
        </div>
      </div>

       <!-- Badges -->
       <div v-if="card.badges && card.badges.length" class="card-badges">
          <span v-for="(badge, idx) in card.badges" :key="idx" class="bento-badge">
            {{ badge }}
          </span>
       </div>

       <!-- Explanation / Banner (Replacing footer) -->
       <div v-if="card.explain" class="card-explain-banner mt-auto">
          {{ card.explain }}
       </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { BentoCard } from '../../utils/bento-cards';

const props = defineProps<{
  card: BentoCard
}>();

const isMaterialIcon = computed(() => {
    return props.card.icon && !props.card.icon.includes('/') && !props.card.icon.includes('.');
});

const isWide = computed(() => props.card.layout === 'wide');
</script>

<style scoped>
.bento-card {
  --glare-opacity: 0.12;
  --card-bg: var(--panel-glass-bg);
  --card-text: var(--text, #0f172a);
  --glass-border: var(--panel-glass-border);
  
  background: var(--card-bg);
  backdrop-filter: blur(16px) saturate(180%);
  -webkit-backdrop-filter: blur(16px) saturate(180%);
  border-radius: 2.25rem;
  padding: 1.75rem;
  border: 1px solid var(--glass-border);
  box-shadow: 
    0 4px 6px -1px rgba(0, 0, 0, 0.05),
    0 10px 15px -3px rgba(0, 0, 0, 0.03),
    inset 0 0 20px rgba(var(--surface-rgb), 0.2);
  display: flex;
  flex-direction: column;
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
  color: var(--card-text);
}

/* Glass Inner Glare */
.bento-card::before {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(circle at top left, rgba(var(--surface-rgb), var(--glare-opacity)) 0%, transparent 60%);
    pointer-events: none;
    z-index: 1;
}

/* Dark Mode base card */
:global(.dark) .bento-card {
    --glare-opacity: 0.08;
    --card-bg: var(--panel-glass-bg);
    --card-text: #f1f5f9;
    --glass-border: var(--panel-glass-border);
    box-shadow: 
        0 10px 30px -10px rgba(0, 0, 0, 0.5),
        inset 0 0 10px rgba(var(--surface-rgb), 0.02);
}

/* Type-Specific Styling (Updates variables) */
.style-orange {
    --card-bg: linear-gradient(135deg, color-mix(in srgb, #fb923c 14%, var(--surface)) 0%, rgba(var(--surface-rgb), 0.5) 100%);
    --card-text: #c2410c; 
    --glass-border: rgba(251, 146, 60, 0.4);
}
:global(.dark) .bento-card.style-orange {
    --card-bg: linear-gradient(135deg, color-mix(in srgb, #fb923c 22%, var(--bg)) 0%, rgba(var(--surface-rgb), 0.6) 100%) !important;
    --card-text: #fdba74 !important; /* orange-300 */
    --glass-border: rgba(251, 146, 60, 0.2);
}

.style-teal {
    --card-bg: linear-gradient(135deg, color-mix(in srgb, #14b8a6 14%, var(--surface)) 0%, rgba(var(--surface-rgb), 0.5) 100%);
    --card-text: #0f766e;
    --glass-border: rgba(20, 184, 166, 0.4);
}
:global(.dark) .bento-card.style-teal {
    --card-bg: linear-gradient(135deg, color-mix(in srgb, #14b8a6 22%, var(--bg)) 0%, rgba(var(--surface-rgb), 0.6) 100%) !important;
    --card-text: #99f6e4 !important; /* teal-200 */
    --glass-border: rgba(20, 184, 166, 0.2);
}

.style-blue {
    --card-bg: linear-gradient(135deg, color-mix(in srgb, #3b82f6 12%, var(--surface)) 0%, rgba(var(--surface-rgb), 0.5) 100%);
    --card-text: #1d4ed8;
    --glass-border: rgba(59, 130, 246, 0.4);
}
:global(.dark) .bento-card.style-blue {
    --card-bg: linear-gradient(135deg, color-mix(in srgb, #3b82f6 22%, var(--bg)) 0%, rgba(var(--surface-rgb), 0.6) 100%) !important;
    --card-text: #bfdbfe !important; /* blue-200 */
    --glass-border: rgba(59, 130, 246, 0.2);
}

.bento-card:hover {
    transform: translateY(-8px) scale(1.02);
    box-shadow: 
        0 25px 35px -10px rgba(0, 0, 0, 0.12),
        0 15px 15px -10px rgba(0, 0, 0, 0.05);
    --glare-opacity: 0.18;
}

/* Watermark Icon */
.watermark-icon {
    position: absolute;
    right: -10%;
    bottom: -15%;
    opacity: 0.12;
    pointer-events: none;
    z-index: 0;
    color: currentColor;
}

.watermark-icon .material-icons-round {
    font-size: 16rem;
    line-height: 1;
}

/* Layouts */
.layout-wide {
  grid-column: span 1;
}
@media (min-width: 768px) {
    .layout-wide {
        grid-column: span 2;
    }
}

.layout-small {
    padding: 1.25rem;
}
.layout-small .card-title {
    font-size: 1rem;
}

/* Icon (Normal) */
.card-icon-wrapper {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 100%;
}
:global(.dark) .card-icon-wrapper {
    background: rgba(var(--surface-rgb), 0.12);
    color: var(--panel-active-text);
    border-color: rgba(var(--surface-rgb), 0.05);
}
.card-content {
    container-type: inline-size;
    justify-content: center;
}
.card-icon {
    font-size: 2.75rem;
    color: var(--card-text);
}
.card-img-icon {
    width: 2rem;
    height: 2rem;
    object-fit: contain;
}

/* Typography */
.card-title {
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 700;
    text-align: center;
    text-transform: uppercase;
    font-size: clamp(1rem, 5vw, 1.5rem);
  white-space: nowrap;
  overflow: hidden;      /* На всякий случай обрезаем, если не влезло */
  text-overflow: ellipsis; /* Добавляем троеточие (...) */
    overflow: hidden;      /* На всякий случай обрезаем, если не влезло */
    text-overflow: ellipsis; /* Добавляем троеточие (...) */
    color: inherit;
    margin-bottom: 0.25rem;
    line-height: 1.2;
}

.card-subtitle {
    font-size: 0.95rem;
    text-align: center;
    color: inherit;
    opacity: 0.8;
    line-height: 1.4;
    max-width: 90%;
}

/* Items */
.card-items {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-evenly;
    gap: 1.5rem;
    margin-top: 0.75rem;
    margin-bottom: 1.25rem;
}
.card-item {
    display: flex;
    align-items: center;
    flex-direction: column;
}
.item-value {
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 700;
    font-size: clamp(1rem, 7cqw, 2.5rem);
    white-space: nowrap;
    color: inherit;
    line-height: 1.1;
}

.item-label {
    font-size: 0.75rem;
    font-size: clamp(1rem, 4cqw, 1.5rem);
    white-space: nowrap;
    color: inherit;
    opacity: 0.7;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-weight: 600;
    margin-top: 0.25rem;
}

/* Badges */
.card-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
}
.bento-badge {
    font-size: 0.75rem;
    padding: 0.35rem 0.65rem;
    background: rgba(0,0,0,0.08);
    color: inherit;
    border-radius: 0.75rem;
    font-weight: 700;
    backdrop-filter: blur(4px);
    opacity: 0.95;
    border: 1px solid rgba(0,0,0,0.03);
}
:global(.dark) .bento-badge {
    background: rgba(var(--surface-rgb), 0.15);
    border-color: rgba(var(--surface-rgb), 0.08);
}

/* Explain Banner */
.card-explain-banner {
    margin-top: 1.5rem;
    padding: 1rem 1.5rem;
    background: rgba(var(--surface-rgb, 255, 255, 255), 0.3);
    border-radius: 1.25rem;
    font-size: 1rem;
    font-weight: 600;
    color: inherit;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    line-height: 1.4;
    backdrop-filter: blur(8px);
    border: 1px solid var(--glass-border);
}
:global(.dark) .card-explain-banner {
    background: rgba(0, 0, 0, 0.3);
    border-color: var(--panel-glass-border);
}
</style>
