<script setup>
import { ref, computed } from 'vue';

const area = ref(25);
const ceilingHeight = ref(2.7);
const isSunny = ref(false);
const people = ref(1);
const computers = ref(1);

// New filters
const isInverter = ref(false);
const hasWifi = ref(false);
const hasWinterHeating = ref(false);

const calculatedPower = computed(() => {
  // Base power: 1 kW per 10 sq.m.
  let power = (area.value * 1.0) / 10;
  
  // Correction for ceiling height > 2.8m
  if (ceilingHeight.value > 2.8) {
    power *= 1.1; // +10%
  }
  
  // Correction for sun exposure
  if (isSunny.value) {
    power *= 1.2; // +20%
  }
  
  // Heat load from people (0.1k kW per person)
  power += people.value * 0.1;
  
  // Heat load from computers/TV (0.2 kW per device)
  power += computers.value * 0.2;
  
  return parseFloat(power.toFixed(2));
});

const recommendedModel = computed(() => {
  const kw = calculatedPower.value;
  if (kw <= 2.1) return { btu: 7, kw: 2.0, name: '07 (до 20 м²)', slug: 'area-20' };
  if (kw <= 2.6) return { btu: 9, kw: 2.5, name: '09 (до 25 м²)', slug: 'area-25' };
  if (kw <= 3.6) return { btu: 12, kw: 3.5, name: '12 (до 35 м²)', slug: 'area-35' };
  if (kw <= 5.4) return { btu: 18, kw: 5.0, name: '18 (до 50 м²)', slug: 'area-50' };
  if (kw <= 7.1) return { btu: 24, kw: 7.0, name: '24 (до 70 м²)', slug: 'area-70' };
  if (kw <= 8.1) return { btu: 28, kw: 8.0, name: '28 (до 80 м²)', slug: 'area-80' };
  return { btu: 30, kw: 9.0, name: 'Требуется консультация', slug: null };
});

const progressPercent = computed(() => {
    // scale from 10 to 100m2
    return ((area.value - 10) / (100 - 10)) * 100;
});

const catalogUrl = computed(() => {
    if (!recommendedModel.value.slug) return '/contacts'; // Redirect to contacts for large areas

    const params = new URLSearchParams();
    const areaMap = {
        'area-20': { area_max: '29' },
        'area-25': { area_max: '29' },
        'area-35': { area_min: '30', area_max: '39' },
        'area-50': { area_min: '40', area_max: '59' },
        'area-70': { area_min: '60', area_max: '70' },
        'area-80': { area_min: '71' },
    };
    const areaPreset = areaMap[recommendedModel.value.slug];
    if (areaPreset?.area_min) params.set('area_min', areaPreset.area_min);
    if (areaPreset?.area_max) params.set('area_max', areaPreset.area_max);

    // Feature tags
    if (isInverter.value) {
        params.set('is_inverter', 'true');
    }
    if (hasWifi.value) {
        params.set('has_wifi', 'true');
    }
    if (hasWinterHeating.value) {
        params.set('heating_min', '-20');
    }

    return `/catalog/?${params.toString()}`;
});
</script>

<template>
  <div class="calculator-card glass">
    <div class="calc-header">
      <div class="icon-wrapper">
        <span class="material-icons-round">calculate</span>
      </div>
      <h2>Расчет мощности</h2>
    </div>

    <div class="calc-body">
        <div class="input-group">
            <label>Площадь помещения: <strong>{{ area }} м²</strong></label>
            <div class="slider-container">
                <input 
                    type="range" 
                    min="10" 
                    max="100" 
                    step="1" 
                    v-model.number="area"
                    class="range-slider"
                    :style="`--progress: ${progressPercent}%`"
                >
            </div>
            <div class="range-labels">
                <span>10 м²</span>
                <span>100 м²</span>
            </div>
        </div>

        <div class="toggles-grid">
            <div 
                class="toggle-btn" 
                :class="{ active: isSunny }"
                @click="isSunny = !isSunny"
            >
                <span class="material-icons-round">wb_sunny</span>
                <span>Солнечная сторона</span>
            </div>
             <div 
                class="toggle-btn" 
                :class="{ active: isInverter }"
                @click="isInverter = !isInverter"
            >
                <span class="material-icons-round">equalizer</span>
                <span>Инвертор</span>
            </div>
             <div 
                class="toggle-btn" 
                :class="{ active: hasWifi }"
                @click="hasWifi = !hasWifi"
            >
                <span class="material-icons-round">wifi</span>
                <span>Wi-Fi</span>
            </div>
             <div 
                class="toggle-btn" 
                :class="{ active: hasWinterHeating }"
                @click="hasWinterHeating = !hasWinterHeating"
            >
                <span class="material-icons-round">ac_unit</span>
                <span>Обогрев зимой</span>
            </div>
        </div>
        
        <div class="extra-params">
             <div class="param-item">
                 <label>Высота потолка, м</label>
                 <input type="number" step="0.1" v-model.number="ceilingHeight">
             </div>
             <div class="param-item">
                 <label>Людей</label>
                 <input type="number" min="0" v-model.number="people">
             </div>
             <div class="param-item">
                 <label>Техники</label>
                 <input type="number" min="0" v-model.number="computers">
             </div>
        </div>

        <div class="divider"></div>

        <div class="result-box">
            <div class="res-row">
                <span>Расчетная мощность:</span>
                <span class="val">{{ calculatedPower }} кВт</span>
             </div>
             <div class="res-row main">
                <span>Подходящий типоразмер:</span>
                <span class="val highlight">{{ recommendedModel.name }}</span>
            </div>
             <div class="res-desc" v-if="recommendedModel.btu">
                *BTU: {{ recommendedModel.btu }}000
            </div>
        </div>

        <div v-if="!recommendedModel.slug" class="warning-box">
            <span class="material-icons-round">warning</span>
            <p>Для такой площади нужно уточнить теплопритоки, тип блоков и трассу. Возможно, вам нужен полупромышленный кондиционер или мульти-сплит система.</p>
        </div>

        <a :href="catalogUrl" class="btn btn-primary full-width">
            {{ !recommendedModel.slug ? 'Заказать консультацию' : 'Подобрать модели' }}
            <span class="material-icons-round">arrow_forward</span>
        </a>
    </div>
  </div>
</template>

<style scoped>
.glass {
  background: var(--surface);
  border: 1px solid var(--border);
  backdrop-filter: blur(12px);
  border-radius: 2rem;
  padding: 2rem;
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
}

.calc-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 2rem;
}

.icon-wrapper {
    width: 48px;
    height: 48px;
    background: #e0f2fe;
    color: #0369a1;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
}

h2 {
    font-size: 1.5rem;
    font-weight: 700;
}

.input-group label {
    display: flex;
    justify-content: space-between;
    margin-bottom: 1rem;
    font-weight: 600;
}

.slider-container {
    height: 30px;
    display: flex;
    align-items: center;
}

.range-slider {
    -webkit-appearance: none;
    width: 100%;
    height: 8px;
    border-radius: 5px;
    background: linear-gradient(to right, var(--primary) var(--progress), #e2e8f0 var(--progress));
    outline: none;
    transition: background 0.2s;
}

.range-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: var(--primary);
    cursor: pointer;
    border: 2px solid white;
    box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    transition: transform 0.2s;
}

.range-slider::-webkit-slider-thumb:hover {
    transform: scale(1.1);
}

.range-labels {
    display: flex;
    justify-content: space-between;
    font-size: 0.8rem;
    color: var(--text-muted);
    margin-top: 0.5rem;
}

.toggles-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
    margin-top: 1.5rem;
}

.toggle-btn {
    display: flex;
    align-items: center;
    justify-content: center; /* Center content */
    gap: 0.5rem;
    padding: 0.75rem;
    border: 1px solid var(--border);
    border-radius: 12px;
    cursor: pointer;
    font-weight: 500;
    font-size: 0.9rem;
    transition: all 0.2s;
    background: var(--bg); /* Ensure background is set */
}

/* Specific active states for different toggles */
.toggle-btn.active {
    border-color: var(--primary);
    background: rgba(0, 127, 128, 0.1);
    color: var(--primary);
}

/* Sunny toggle specific style override if needed, or keep uniform */
/* Original sunny style was yellow/orange, let's keep it for Sunny only? 
   Or make everything primary for consistency? 
   Let's keep Sunny warm, others primary.
*/
.toggle-btn:first-child.active { /* Sunny is first */
    background: #fef3c7;
    border-color: #f59e0b;
    color: #92400e;
}

.extra-params {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 1rem;
    margin-top: 1.5rem;
}

.param-item {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.param-item label {
    font-size: 0.8rem;
    color: var(--text-muted);
}

.param-item input {
    width: 100%;
    padding: 0.5rem;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--bg);
    color: var(--text);
    text-align: center;
}

.divider {
    height: 1px;
    background: var(--border);
    margin: 2rem 0;
}

.result-box {
    background: var(--bg);
    border-radius: 1rem;
    padding: 1.5rem;
    margin-bottom: 2rem;
}

.res-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
    font-size: 0.95rem;
}

.res-row.main {
    margin-top: 1rem;
    font-size: 1.1rem;
    font-weight: 700;
}

.val {
    font-weight: 600;
}

.val.highlight {
    color: var(--primary);
}

.res-desc {
    font-size: 0.8rem;
    color: var(--text-muted);
    text-align: right;
    margin-top: 0.2rem;
}

.warning-box {
    background: #fff1f2;
    border: 1px solid #fda4af;
    color: #9f1239;
    padding: 1rem;
    border-radius: 0.75rem;
    margin-bottom: 1.5rem;
    display: flex;
    gap: 0.75rem;
    align-items: flex-start;
    font-size: 0.9rem;
    line-height: 1.4;
}

.warning-box .material-icons-round {
    color: #e11d48;
}

.full-width {
    width: 100%;
    justify-content: center;
    font-size: 1.1rem;
    padding: 1rem;
    text-decoration: none;
}
</style>
