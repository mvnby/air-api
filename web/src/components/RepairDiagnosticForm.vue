<script setup>
import { computed, onMounted, ref } from 'vue';
import { submitRepairDiagnostic } from '../utils/api';
import { formatPhoneForDisplay, validateRequiredBelarusPhone } from '../utils/validation';
import {
  clientChecks,
  conditionalQuestions,
  photoFields,
  symptoms,
  timings,
} from '../config/repairDiagnostic';

const steps = [
  'Что случилось',
  'Когда проявляется',
  'Что проверяли',
  'Фото',
  'Контакты',
];

const currentStep = ref(0);
const isSubmitting = ref(false);
const isSuccess = ref(false);
const submitError = ref('');
const createdOrderId = ref(null);
const phoneInput = ref(null);
const formRoot = ref(null);

const form = ref({
  symptom: '',
  problemTiming: '',
  symptomDetails: {},
  clientChecks: [],
  name: '',
  phone: '',
  address: '',
  comment: '',
});

const photos = ref(
  photoFields.reduce((acc, item) => {
    acc[item.key] = [];
    return acc;
  }, {})
);

const activeQuestions = computed(() => conditionalQuestions[form.value.symptom] || []);

onMounted(() => {
  if (!phoneInput.value) return;
  phoneInput.value.onfocus = () => {
    if (!form.value.phone.trim()) form.value.phone = '+375 ';
  };
  phoneInput.value.onblur = () => {
    form.value.phone = formatPhoneForDisplay(form.value.phone);
  };
});

function selectSymptom(value) {
  form.value.symptom = value;
  form.value.symptomDetails = {};
}

function setDetail(key, value) {
  form.value.symptomDetails = {
    ...form.value.symptomDetails,
    [key]: value,
  };
}

function toggleCheck(value) {
  const checks = new Set(form.value.clientChecks);
  if (value === 'nothing_checked') {
    form.value.clientChecks = checks.has(value) ? [] : [value];
    return;
  }
  checks.delete('nothing_checked');
  if (checks.has(value)) checks.delete(value);
  else checks.add(value);
  form.value.clientChecks = Array.from(checks);
}

function onFilesChange(key, event) {
  photos.value[key] = Array.from(event.target.files || []).slice(0, 5);
}

function validateStep(index) {
  submitError.value = '';
  if (index === 0 && !form.value.symptom) {
    submitError.value = 'Выберите, что случилось с кондиционером.';
    return false;
  }
  if (index === 1 && !form.value.problemTiming) {
    submitError.value = 'Выберите, когда проявляется проблема.';
    return false;
  }
  if (index === 4) {
    if (!form.value.name.trim()) {
      submitError.value = 'Введите имя.';
      return false;
    }
    form.value.phone = formatPhoneForDisplay(form.value.phone);
    const phoneError = validateRequiredBelarusPhone(form.value.phone, true);
    if (phoneError) {
      submitError.value = phoneError;
      return false;
    }
    if (!form.value.address.trim()) {
      submitError.value = 'Укажите адрес или район.';
      return false;
    }
  }
  return true;
}

function scrollToDiagnosticStart() {
  requestAnimationFrame(() => {
    formRoot.value?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
}

function nextStep() {
  if (!validateStep(currentStep.value)) return;
  currentStep.value = Math.min(currentStep.value + 1, steps.length - 1);
  scrollToDiagnosticStart();
}

function previousStep() {
  submitError.value = '';
  currentStep.value = Math.max(currentStep.value - 1, 0);
  scrollToDiagnosticStart();
}

function buildPayload() {
  return {
    scenario: 'repair',
    symptom: form.value.symptom,
    problem_timing: form.value.problemTiming,
    symptom_details: form.value.symptomDetails,
    client_checks: form.value.clientChecks,
    client_comment: form.value.comment.trim(),
    contact: {
      name: form.value.name.trim(),
      phone: form.value.phone.trim(),
      address: form.value.address.trim(),
    },
  };
}

async function submitForm() {
  for (let index = 0; index < steps.length; index += 1) {
    if (!validateStep(index)) {
      currentStep.value = index;
      scrollToDiagnosticStart();
      return;
    }
  }
  isSubmitting.value = true;
  submitError.value = '';
  const result = await submitRepairDiagnostic(buildPayload(), photos.value);
  isSubmitting.value = false;
  if (!result) {
    submitError.value = 'Не удалось отправить заявку. Попробуйте позже или позвоните нам.';
    return;
  }
  createdOrderId.value = result.order_id;
  isSuccess.value = true;
}
</script>

<template>
  <section ref="formRoot" class="repair-diagnostic" id="repair-diagnostic">
    <div v-if="isSuccess" class="success-panel">
      <span class="material-icons-round success-icon">check_circle</span>
      <h3>Заявка принята.</h3>
      <p>
        Заявка принята. По вашим ответам мастер предварительно оценит возможную причину
        неисправности. Точная причина и стоимость ремонта определяются после диагностики на месте.
      </p>
      <p v-if="createdOrderId" class="order-number">Номер заявки: {{ createdOrderId }}</p>
    </div>

    <div v-else>
      <div class="diagnostic-intro">
        <p class="eyebrow">Предварительная диагностика</p>
        <h3>Поможем мастеру подготовиться до выезда</h3>
        <p>
          Ответьте на несколько вопросов, и мастер заранее поймет, с чем может быть связана
          неисправность. Это не заменяет диагностику на месте, но помогает быстрее оценить
          ситуацию, подготовить инструмент и ориентировочно понять сложность ремонта.
        </p>
      </div>

      <div class="stepper" aria-label="Шаги диагностики">
        <div
          v-for="(step, index) in steps"
          :key="step"
          class="step-dot"
          :class="{ active: currentStep === index, done: currentStep > index }"
          :aria-current="currentStep === index ? 'step' : undefined"
        >
          <span>{{ index + 1 }}</span>
          <b>{{ step }}</b>
        </div>
      </div>

      <form class="diagnostic-form" @submit.prevent="submitForm">
        <div v-if="currentStep === 0" class="step-panel">
          <h4>Что случилось?</h4>
          <div class="option-grid">
            <button
              v-for="item in symptoms"
              :key="item.value"
              type="button"
              class="choice"
              :class="{ selected: form.symptom === item.value }"
              @click="selectSymptom(item.value)"
            >
              {{ item.label }}
            </button>
          </div>
        </div>

        <div v-if="currentStep === 1" class="step-panel">
          <h4>Когда проявляется проблема?</h4>
          <div class="option-grid compact">
            <button
              v-for="item in timings"
              :key="item.value"
              type="button"
              class="choice"
              :class="{ selected: form.problemTiming === item.value }"
              @click="form.problemTiming = item.value"
            >
              {{ item.label }}
            </button>
          </div>

          <div v-if="activeQuestions.length" class="conditional">
            <h5>Уточним по выбранному симптому</h5>
            <div v-for="question in activeQuestions" :key="question.key" class="question-row">
              <label>{{ question.label }}</label>
              <input
                v-if="question.type === 'text'"
                v-model="form.symptomDetails[question.key]"
                type="text"
                :placeholder="question.placeholder"
              />
              <div v-else class="segmented">
                <button
                  v-for="option in question.options"
                  :key="option.value"
                  type="button"
                  class="segment"
                  :class="{ selected: form.symptomDetails[question.key] === option.value }"
                  @click="setDetail(question.key, option.value)"
                >
                  {{ option.label }}
                </button>
              </div>
            </div>
          </div>
        </div>

        <div v-if="currentStep === 2" class="step-panel">
          <h4>Что уже проверяли?</h4>
          <div class="option-grid compact">
            <button
              v-for="item in clientChecks"
              :key="item.value"
              type="button"
              class="choice"
              :class="{ selected: form.clientChecks.includes(item.value) }"
              @click="toggleCheck(item.value)"
            >
              {{ item.label }}
            </button>
          </div>
        </div>

        <div v-if="currentStep === 3" class="step-panel">
          <h4>Фото</h4>
          <p class="step-note">
            Особенно важно фото шильдика: по нему можно определить модель, хладагент и часть
            технических параметров.
          </p>
          <div class="photo-list">
            <label v-for="item in photoFields" :key="item.key" class="photo-field">
              <span>
                <b>{{ item.label }}</b>
                <small v-if="item.hint">{{ item.hint }}</small>
              </span>
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                multiple
                @change="onFilesChange(item.key, $event)"
              />
              <em v-if="photos[item.key].length">{{ photos[item.key].length }} файл(а)</em>
            </label>
          </div>
        </div>

        <div v-if="currentStep === 4" class="step-panel">
          <h4>Контакты</h4>
          <div class="field-grid">
            <label>
              <span>Имя</span>
              <input v-model="form.name" type="text" autocomplete="name" required />
            </label>
            <label>
              <span>Телефон</span>
              <input
                ref="phoneInput"
                v-model="form.phone"
                type="tel"
                autocomplete="tel"
                placeholder="+375 (XX) XXX-XX-XX или +7 XXX XXX-XX-XX"
                required
              />
            </label>
            <label class="wide">
              <span>Адрес или район</span>
              <input v-model="form.address" type="text" autocomplete="street-address" required />
            </label>
            <label class="wide">
              <span>Комментарий</span>
              <textarea
                v-model="form.comment"
                rows="4"
                placeholder="Например: кондиционер висит над окном, наружный блок доступен с балкона"
              ></textarea>
            </label>
          </div>
          <p class="privacy">
            Нажимая кнопку, вы соглашаетесь с
            <a href="/privacy/">политикой обработки персональных данных</a>.
          </p>
        </div>

        <p v-if="submitError" class="form-error">{{ submitError }}</p>

        <div class="actions">
          <button
            v-if="currentStep > 0"
            class="btn btn-outline"
            type="button"
            @click="previousStep"
          >
            Назад
          </button>
          <button
            v-if="currentStep < steps.length - 1"
            class="btn btn-primary"
            type="button"
            @click="nextStep"
          >
            Далее
          </button>
          <button
            v-else
            class="btn btn-primary"
            type="submit"
            :disabled="isSubmitting"
          >
            {{ isSubmitting ? 'Отправка...' : 'Отправить заявку' }}
          </button>
        </div>
      </form>
    </div>
  </section>
</template>

<style scoped>
.repair-diagnostic {
  background: var(--panel-glass-bg);
  border: 1px solid var(--panel-glass-border);
  border-radius: 1rem;
  box-shadow: var(--panel-glass-shadow);
  margin: 2rem 0;
  padding: 1.5rem;
  scroll-margin-top: 6rem;
}

.diagnostic-intro {
  display: grid;
  gap: 0.75rem;
  margin-bottom: 1.5rem;
}

.eyebrow {
  color: var(--primary);
  font-weight: 800;
  margin: 0;
  text-transform: uppercase;
}

h3,
h4,
h5,
p {
  margin: 0;
}

h3 {
  font-size: 1.6rem;
}

h4 {
  font-size: 1.25rem;
  margin-bottom: 1rem;
}

.stepper {
  display: grid;
  gap: 0.5rem;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  margin-bottom: 1.5rem;
}

.step-dot {
  align-items: center;
  background: var(--panel-pill-bg);
  border: 1px solid var(--panel-chip-border);
  border-radius: 0.75rem;
  color: var(--text-muted);
  display: flex;
  gap: 0.5rem;
  min-height: 3rem;
  padding: 0.5rem;
  text-align: left;
}

.step-dot span {
  align-items: center;
  background: var(--secondary);
  border-radius: 999px;
  color: var(--primary);
  display: inline-flex;
  flex: 0 0 1.6rem;
  height: 1.6rem;
  justify-content: center;
  line-height: 1;
}

.step-dot b {
  font-size: 0.8rem;
  line-height: 1.15;
}

.step-dot.active,
.step-dot.done {
  border-color: var(--panel-chip-hover-border);
  color: var(--text);
}

.step-dot.active span,
.step-dot.done span {
  background: var(--panel-active-gradient);
  color: var(--panel-active-text);
}

.diagnostic-form,
.step-panel,
.conditional,
.photo-list {
  display: grid;
  gap: 1rem;
}

.option-grid {
  display: grid;
  gap: 0.75rem;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.option-grid.compact {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.choice,
.segment {
  background: var(--panel-chip-bg);
  border: 1px solid var(--panel-chip-border);
  border-radius: 0.75rem;
  color: var(--text);
  cursor: pointer;
  font: inherit;
  font-weight: 700;
  min-height: 3.25rem;
  padding: 0.8rem 1rem;
  text-align: left;
}

.choice.selected,
.segment.selected {
  background: var(--panel-active-gradient);
  border-color: transparent;
  color: var(--panel-active-text);
}

.conditional {
  border-top: 1px solid var(--border);
  margin-top: 0.5rem;
  padding-top: 1rem;
}

.question-row {
  display: grid;
  gap: 0.5rem;
}

.question-row label,
.field-grid span,
.photo-field b {
  color: var(--text);
  font-weight: 700;
}

.segmented {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.segment {
  min-height: 2.75rem;
  text-align: center;
}

.step-note,
.photo-field small,
.privacy,
.order-number {
  color: var(--text-muted);
}

.photo-field {
  align-items: center;
  border: 1px solid var(--panel-input-border);
  border-radius: 0.75rem;
  display: grid;
  gap: 0.75rem;
  grid-template-columns: minmax(0, 1fr);
  padding: 1rem;
}

.photo-field span {
  display: grid;
  gap: 0.25rem;
}

.photo-field input,
.question-row input,
.field-grid input,
.field-grid textarea {
  background: var(--panel-input-bg);
  border: 1px solid var(--panel-input-border);
  border-radius: 0.75rem;
  color: var(--text);
  font: inherit;
  padding: 0.85rem 1rem;
  width: 100%;
}

.photo-field em {
  color: var(--success-text);
  font-style: normal;
  font-weight: 700;
}

.field-grid {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.field-grid label {
  display: grid;
  gap: 0.4rem;
}

.field-grid .wide {
  grid-column: 1 / -1;
}

.form-error {
  background: var(--error-bg);
  border: 1px solid var(--error-text);
  border-radius: 0.75rem;
  color: var(--error-text);
  padding: 0.85rem 1rem;
}

.actions {
  display: flex;
  gap: 0.75rem;
  justify-content: flex-end;
}

.success-panel {
  display: grid;
  gap: 0.75rem;
  justify-items: start;
}

.success-icon {
  color: var(--success-text);
  font-size: 2.25rem;
}

@media (max-width: 760px) {
  .repair-diagnostic {
    padding: 1rem;
  }

  .stepper,
  .option-grid,
  .option-grid.compact,
  .field-grid {
    grid-template-columns: 1fr;
  }

  .step-dot {
    min-height: 2.75rem;
  }

  .actions {
    flex-direction: column-reverse;
  }

  .actions .btn {
    width: 100%;
  }
}
</style>
