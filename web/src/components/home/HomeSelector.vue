<script setup lang="ts">
import { computed, ref } from "vue";
import {
  buildHomeSelectionResult,
  type HomeSelectionAnswers,
  type HomeSelectionPriority,
  type HomeSelectionRooms,
} from "../../config/home-selection";
import { HOMEPAGE_ANALYTICS_EVENTS } from "../../config/homepage";

type StepKey = "rooms" | "area" | "priority" | "inverter";

const steps: Array<{ key: StepKey; label: string; title: string; hint: string }> = [
  {
    key: "rooms",
    label: "Помещения",
    title: "Сколько комнат нужно охлаждать?",
    hint: "Для нескольких отдельных комнат обычно нужна отдельная схема оборудования.",
  },
  {
    key: "area",
    label: "Площадь",
    title: "Какая площадь помещения?",
    hint: "Выберите ближайшее значение с небольшим запасом.",
  },
  {
    key: "priority",
    label: "Задача",
    title: "Что важнее в первую очередь?",
    hint: "Остальные параметры можно будет уточнить в каталоге.",
  },
  {
    key: "inverter",
    label: "Компрессор",
    title: "Нужен инвертор?",
    hint: "Инвертор плавно регулирует мощность. Если не уверены, оставьте любой тип.",
  },
];
const areaOptions: HomeSelectionAnswers["area"][] = [20, 25, 35, 50, 70];

const currentStep = ref(0);
const resultVisible = ref(false);
const answers = ref<Partial<HomeSelectionAnswers>>({});

const activeStep = computed(() => steps[currentStep.value]);
const progress = computed(() => ((currentStep.value + 1) / steps.length) * 100);
const canContinue = computed(() => answers.value[activeStep.value.key] !== undefined);
const result = computed(() => {
  if (
    answers.value.rooms === undefined ||
    answers.value.area === undefined ||
    answers.value.priority === undefined ||
    answers.value.inverter === undefined
  ) {
    return null;
  }
  return buildHomeSelectionResult(answers.value as HomeSelectionAnswers);
});

const selectRooms = (value: HomeSelectionRooms) => {
  answers.value.rooms = value;
};

const selectArea = (value: HomeSelectionAnswers["area"]) => {
  answers.value.area = value;
};

const selectPriority = (value: HomeSelectionPriority) => {
  answers.value.priority = value;
};

const selectInverter = (value: boolean) => {
  answers.value.inverter = value;
};

const next = () => {
  if (!canContinue.value) return;
  if (currentStep.value === steps.length - 1) {
    resultVisible.value = true;
    return;
  }
  currentStep.value += 1;
};

const back = () => {
  if (resultVisible.value) {
    resultVisible.value = false;
    return;
  }
  if (currentStep.value > 0) currentStep.value -= 1;
};

const reset = () => {
  answers.value = {};
  currentStep.value = 0;
  resultVisible.value = false;
};

const trackResult = () => {
  if (!result.value) return;
  const analyticsWindow = window as Window & {
    dataLayer?: Array<Record<string, string>>;
  };
  analyticsWindow.dataLayer = analyticsWindow.dataLayer || [];
  analyticsWindow.dataLayer.push({
    event: HOMEPAGE_ANALYTICS_EVENTS.selectorComplete,
    rooms: String(answers.value.rooms || ""),
    area: String(answers.value.area || ""),
    priority: String(answers.value.priority || ""),
    inverter: String(answers.value.inverter ?? ""),
    destination: result.value.href,
  });
};
</script>

<template>
  <section id="home-selector" class="home-selector container" aria-labelledby="home-selector-title">
    <div class="home-selector__intro">
      <p class="home-selector__eyebrow">Быстрый подбор</p>
      <h2 id="home-selector-title">С чего начать выбор</h2>
      <p>Ответьте на четыре вопроса — откроем каталог с подходящими фильтрами.</p>
    </div>

    <div class="home-selector__panel">
      <template v-if="!resultVisible">
        <div class="home-selector__progress-head">
          <span>Шаг {{ currentStep + 1 }} из {{ steps.length }}</span>
          <strong>{{ activeStep.label }}</strong>
        </div>
        <div class="home-selector__progress" aria-hidden="true">
          <span :style="{ width: `${progress}%` }" />
        </div>

        <fieldset class="home-selector__question">
          <legend>{{ activeStep.title }}</legend>
          <p>{{ activeStep.hint }}</p>

          <div v-if="activeStep.key === 'rooms'" class="home-selector__options two-columns">
            <button type="button" :aria-pressed="answers.rooms === 'single'" @click="selectRooms('single')">
              <span class="material-icons-round" aria-hidden="true">meeting_room</span>
              <strong>Одна комната</strong>
              <small>Один внутренний и один наружный блок</small>
            </button>
            <button type="button" :aria-pressed="answers.rooms === 'multiple'" @click="selectRooms('multiple')">
              <span class="material-icons-round" aria-hidden="true">account_tree</span>
              <strong>Несколько комнат</strong>
              <small>Нужна схема для двух и более помещений</small>
            </button>
          </div>

          <div v-else-if="activeStep.key === 'area'" class="home-selector__options area-options">
            <button v-for="area in areaOptions" :key="area" type="button" :aria-pressed="answers.area === area" @click="selectArea(area)">
              <strong>до {{ area }} м²</strong>
            </button>
          </div>

          <div v-else-if="activeStep.key === 'priority'" class="home-selector__options priority-options">
            <button type="button" :aria-pressed="answers.priority === 'price'" @click="selectPriority('price')">
              <span class="material-icons-round" aria-hidden="true">payments</span><strong>Доступная цена</strong>
            </button>
            <button type="button" :aria-pressed="answers.priority === 'silent'" @click="selectPriority('silent')">
              <span class="material-icons-round" aria-hidden="true">volume_off</span><strong>Тихая работа</strong>
            </button>
            <button type="button" :aria-pressed="answers.priority === 'heating'" @click="selectPriority('heating')">
              <span class="material-icons-round" aria-hidden="true">mode_heat</span><strong>Обогрев зимой</strong>
            </button>
            <button type="button" :aria-pressed="answers.priority === 'wifi'" @click="selectPriority('wifi')">
              <span class="material-icons-round" aria-hidden="true">wifi</span><strong>Управление по Wi-Fi</strong>
            </button>
          </div>

          <div v-else class="home-selector__options two-columns">
            <button type="button" :aria-pressed="answers.inverter === true" @click="selectInverter(true)">
              <span class="material-icons-round" aria-hidden="true">speed</span>
              <strong>Да, инвертор</strong>
              <small>Плавная регулировка мощности</small>
            </button>
            <button type="button" :aria-pressed="answers.inverter === false" @click="selectInverter(false)">
              <span class="material-icons-round" aria-hidden="true">tune</span>
              <strong>Не принципиально</strong>
              <small>Покажем оба типа компрессора</small>
            </button>
          </div>
        </fieldset>

        <div class="home-selector__actions">
          <button v-if="currentStep > 0" type="button" class="selector-back" @click="back">
            <span class="material-icons-round" aria-hidden="true">arrow_back</span>Назад
          </button>
          <span v-else />
          <button type="button" class="selector-next" :disabled="!canContinue" @click="next">
            {{ currentStep === steps.length - 1 ? 'Показать результат' : 'Дальше' }}
            <span class="material-icons-round" aria-hidden="true">arrow_forward</span>
          </button>
        </div>
      </template>

      <div v-else-if="result" class="home-selector__result" aria-live="polite">
        <span class="material-icons-round result-icon" aria-hidden="true">task_alt</span>
        <p class="home-selector__eyebrow">Предварительный результат</p>
        <h3>{{ result.title }}</h3>
        <p>{{ result.summary }}</p>
        <ul>
          <li v-for="criterion in result.criteria" :key="criterion">{{ criterion }}</li>
        </ul>
        <div class="home-selector__result-actions">
          <a class="selector-next" :href="result.href" @click="trackResult">
            Показать подходящие модели
            <span class="material-icons-round" aria-hidden="true">arrow_forward</span>
          </a>
          <button type="button" class="selector-reset" @click="reset">Начать заново</button>
        </div>
        <p class="home-selector__note">Окончательную мощность проверяем с учетом солнца, высоты потолка, техники и места монтажа.</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.home-selector {
  display: grid;
  grid-template-columns: minmax(240px, 0.72fr) minmax(0, 1.28fr);
  gap: clamp(1.5rem, 4vw, 4rem);
  align-items: start;
  padding-right: 1.5rem;
  padding-left: 1.5rem;
  padding-top: clamp(2.5rem, 6vw, 5rem);
  padding-bottom: clamp(2.5rem, 6vw, 5rem);
  scroll-margin-top: 4.75rem;
}

.home-selector__intro {
  position: sticky;
  top: 7rem;
}

.home-selector__eyebrow {
  margin: 0 0 0.55rem;
  color: var(--primary);
  font-size: 0.78rem;
  font-weight: 800;
  text-transform: uppercase;
}

.home-selector__intro h2 {
  margin: 0;
  font-size: clamp(1.85rem, 3vw, 2.8rem);
  line-height: 1.08;
}

.home-selector__intro > p:last-child {
  margin: 1rem 0 0;
  color: var(--text-muted);
  line-height: 1.65;
}

.home-selector__panel {
  min-height: 390px;
  padding: clamp(1.25rem, 3vw, 2rem);
  border: 1px solid var(--panel-glass-border);
  border-radius: 8px;
  background: var(--panel-glass-bg);
  box-shadow: var(--panel-glass-shadow);
}

.home-selector__progress-head {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  color: var(--text-muted);
  font-size: 0.82rem;
}

.home-selector__progress-head strong { color: var(--text); }

.home-selector__progress {
  height: 4px;
  margin: 0.75rem 0 1.75rem;
  overflow: hidden;
  border-radius: 4px;
  background: var(--panel-chip-bg);
}

.home-selector__progress span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--primary);
  transition: width 0.2s ease;
}

.home-selector__question {
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}

.home-selector__question legend {
  padding: 0;
  font-size: clamp(1.35rem, 2.5vw, 1.8rem);
  font-weight: 800;
  line-height: 1.2;
}

.home-selector__question > p {
  margin: 0.55rem 0 1.35rem;
  color: var(--text-muted);
  font-size: 0.9rem;
}

.home-selector__options {
  display: grid;
  gap: 0.75rem;
}

.home-selector__options.two-columns,
.home-selector__options.priority-options { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.home-selector__options.area-options { grid-template-columns: repeat(5, minmax(0, 1fr)); }

.home-selector__options button {
  min-width: 0;
  min-height: 68px;
  padding: 0.85rem;
  border: 1px solid var(--panel-chip-border);
  border-radius: 8px;
  background: var(--panel-chip-bg);
  color: var(--text);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.18s ease, background 0.18s ease, transform 0.18s ease;
}

.home-selector__options button:hover { border-color: var(--panel-chip-hover-border); transform: translateY(-1px); }
.home-selector__options button[aria-pressed="true"] { border-color: var(--primary); background: var(--panel-active-gradient); color: var(--panel-active-text); }
.home-selector__options button[aria-pressed="true"] .material-icons-round,
.home-selector__options button[aria-pressed="true"] small { color: inherit; }
.home-selector__options button:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
.home-selector__options button .material-icons-round { display: block; margin-bottom: 0.35rem; color: var(--primary); font-size: 1.2rem; }
.home-selector__options button strong { display: block; font-size: 0.92rem; }
.home-selector__options button small { display: block; margin-top: 0.25rem; color: var(--text-muted); font-size: 0.72rem; line-height: 1.35; }

.home-selector__actions,
.home-selector__result-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-top: 1.5rem;
}

.selector-back,
.selector-reset {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  min-height: 44px;
  padding: 0.5rem;
  border: 0;
  background: transparent;
  color: var(--text-muted);
  font-weight: 700;
  cursor: pointer;
}

.selector-next {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  min-height: 46px;
  padding: 0.7rem 1rem;
  border: 1px solid transparent;
  border-radius: 8px;
  background: var(--primary);
  color: var(--panel-active-text);
  font-weight: 800;
  text-decoration: none;
  cursor: pointer;
}

.selector-next:disabled { opacity: 0.45; cursor: not-allowed; }
.selector-next:focus-visible,
.selector-back:focus-visible,
.selector-reset:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }

.home-selector__result { min-height: 330px; }
.home-selector__result .result-icon { color: var(--primary); font-size: 2rem; }
.home-selector__result h3 { margin: 0.25rem 0 0.7rem; font-size: clamp(1.4rem, 2.5vw, 2rem); }
.home-selector__result > p { color: var(--text-muted); line-height: 1.55; }
.home-selector__result ul { display: grid; gap: 0.55rem; margin: 1rem 0 0; padding: 0; list-style: none; }
.home-selector__result li::before { content: "✓"; margin-right: 0.5rem; color: var(--primary); font-weight: 900; }
.home-selector__result-actions { justify-content: flex-start; flex-wrap: wrap; }
.home-selector__note { margin: 1rem 0 0; font-size: 0.78rem; }

@media (max-width: 900px) {
  .home-selector { grid-template-columns: 1fr; gap: 1.25rem; }
  .home-selector__intro { position: static; }
}

@media (max-width: 620px) {
  .home-selector { padding: 2.5rem 1rem; }
  .home-selector__panel { min-height: 420px; }
  .home-selector__options.area-options { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .home-selector__options.priority-options { grid-template-columns: 1fr; }
  .home-selector__actions { align-items: stretch; }
  .selector-next { flex: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .home-selector__progress span,
  .home-selector__options button { transition: none; }
}
</style>
