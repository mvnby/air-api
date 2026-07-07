<script setup>
import { ref, onBeforeUnmount, onMounted, watch } from 'vue';
import { getAddressSuggestions, submitContactForm } from '../utils/api';
import { formatPhoneForDisplay, validateRequiredBelarusPhone } from '../utils/validation';

const props = defineProps({
  title: {
    type: String,
    default: 'Оставить заявку'
  },
  subtitle: {
    type: String,
    default: 'Свяжемся в рабочее время и уточним детали'
  },
  buttonText: {
    type: String,
    default: 'Отправить'
  },
  subject: {
    type: String,
    default: '' // e.g. 'Заказ монтажа', 'Сервис'
  },
  showAddress: {
    type: Boolean,
    default: false
  },
  addressLabel: {
    type: String,
    default: 'Адрес или район'
  },
  addressPlaceholder: {
    type: String,
    default: 'Начните вводить адрес'
  },
  showPreferredTime: {
    type: Boolean,
    default: false
  },
  preferredTimeLabel: {
    type: String,
    default: 'Когда удобнее принять мастера'
  },
  preferredTimeHint: {
    type: String,
    default: 'Точное время согласуем после заявки.'
  },
  commentLabel: {
    type: String,
    default: 'Комментарий (необязательно)'
  },
  commentPlaceholder: {
    type: String,
    default: 'Меня интересует...'
  }
});

const form = ref({
  name: '',
  phone: '',
  address: '',
  preferredTime: '',
  message: ''
});

const phoneInput = ref(null);
const isSubmitting = ref(false);
const isSuccess = ref(false);
const addressSuggestions = ref([]);
const isAddressSuggestLoading = ref(false);
const showAddressSuggestions = ref(false);
const skipNextAddressSuggestLookup = ref(false);
let addressSuggestTimer = null;

const preferredTimeOptions = [
  'Первая половина дня',
  'Вторая половина дня',
  'После 17:00',
  'Выходной день',
  'Не важно'
];

onMounted(() => {
    if (!phoneInput.value) return;
    phoneInput.value.onfocus = () => {
        if (!form.value.phone.trim()) form.value.phone = '+375 ';
    };
    phoneInput.value.onblur = () => {
        form.value.phone = formatPhoneForDisplay(form.value.phone);
    };
});

watch(
    () => form.value.address,
    (value) => {
        if (!props.showAddress) return;
        if (addressSuggestTimer) {
            clearTimeout(addressSuggestTimer);
            addressSuggestTimer = null;
        }

        const query = String(value || '').trim();
        if (skipNextAddressSuggestLookup.value) {
            skipNextAddressSuggestLookup.value = false;
            return;
        }

        if (query.length < 2) {
            addressSuggestions.value = [];
            showAddressSuggestions.value = false;
            isAddressSuggestLoading.value = false;
            return;
        }

        addressSuggestTimer = setTimeout(async () => {
            isAddressSuggestLoading.value = true;
            const lookupValue = query;

            try {
                const response = await getAddressSuggestions(lookupValue);
                if (String(form.value.address || '').trim() !== lookupValue) return;

                addressSuggestions.value = Array.isArray(response?.items) ? response.items : [];
                showAddressSuggestions.value = addressSuggestions.value.length > 0;
            } catch (e) {
                console.warn('Failed to fetch address suggestions', e);
                if (String(form.value.address || '').trim() === lookupValue) {
                    addressSuggestions.value = [];
                    showAddressSuggestions.value = false;
                }
            } finally {
                if (String(form.value.address || '').trim() === lookupValue) {
                    isAddressSuggestLoading.value = false;
                }
            }
        }, 300);
    }
);

onBeforeUnmount(() => {
    if (addressSuggestTimer) clearTimeout(addressSuggestTimer);
});

const onAddressFocus = () => {
    if (addressSuggestions.value.length > 0) {
        showAddressSuggestions.value = true;
    }
};

const onAddressBlur = () => {
    setTimeout(() => {
        showAddressSuggestions.value = false;
    }, 150);
};

const applyAddressSuggestion = (suggestion) => {
    skipNextAddressSuggestLookup.value = true;
    form.value.address = suggestion.value;
    addressSuggestions.value = [];
    showAddressSuggestions.value = false;
};

const buildMessage = () => {
  const lines = [];
  const message = String(form.value.message || '').trim();

  if (props.subject) lines.push(`[${props.subject}]`);
  if (props.showPreferredTime && form.value.preferredTime) {
      lines.push(`Удобное время: ${form.value.preferredTime}. Точное время согласовать отдельно.`);
  }
  if (message) lines.push(message);

  return lines.join('\n');
};

const submitForm = async () => {
  form.value.phone = formatPhoneForDisplay(form.value.phone);
  const phoneError = validateRequiredBelarusPhone(form.value.phone, true);
  if (phoneError) {
      alert(phoneError);
      return;
  }

  isSubmitting.value = true;
  
  const payload = {
      ...form.value,
      address: props.showAddress ? String(form.value.address || '').trim() : '',
      message: buildMessage()
  };
  
  const success = await submitContactForm(payload);
  
  isSubmitting.value = false;
  
  if (success) {
    isSuccess.value = true;
    // Reset after 5 seconds
    setTimeout(() => {
        isSuccess.value = false;
        form.value = { name: '', phone: '', address: '', preferredTime: '', message: '' };
        addressSuggestions.value = [];
        showAddressSuggestions.value = false;
    }, 5000);
  } else {
    alert('Ошибка отправки. Попробуйте позже.');
  }
};
</script>

<template>
  <div class="contact-form-container glass">
    <div v-if="isSuccess" class="success-message">
      <div class="icon-box">
        <span class="material-icons-round">check_circle</span>
      </div>
      <h3>Заявка отправлена!</h3>
      <p>Мы свяжемся с вами в ближайшее время.</p>
    </div>

    <form v-else @submit.prevent="submitForm" class="contact-form">
      <h3>{{ title }}</h3>
      <p class="subtitle" v-if="subtitle">{{ subtitle }}</p>

      <div class="form-group">
        <label for="name">Ваше имя</label>
        <input 
          type="text" 
          id="name" 
          v-model="form.name" 
          placeholder="Иван Иванов"
          required
        >
      </div>

      <div class="form-group">
        <label for="phone">Телефон</label>
        <input 
          type="tel" 
          id="phone" 
          ref="phoneInput"
          v-model="form.phone" 
          placeholder="+375 (XX) XXX-XX-XX или +7 XXX XXX-XX-XX"
          required
        >
      </div>

      <div v-if="showAddress" class="form-group">
        <label for="contact-address">{{ addressLabel }}</label>
        <div class="address-suggest">
          <div class="input-with-loader">
            <input
              type="text"
              id="contact-address"
              v-model="form.address"
              @focus="onAddressFocus"
              @blur="onAddressBlur"
              autocomplete="street-address"
              :placeholder="addressPlaceholder"
              required
            >
            <span v-if="isAddressSuggestLoading" class="loader-icon material-icons-round">sync</span>
          </div>
          <div v-if="showAddressSuggestions" class="suggest-dropdown">
            <button
              v-for="suggestion in addressSuggestions"
              :key="suggestion.value"
              type="button"
              class="suggest-option"
              @mousedown.prevent="applyAddressSuggestion(suggestion)"
            >
              <span class="suggest-title">{{ suggestion.title }}</span>
              <span v-if="suggestion.subtitle" class="suggest-subtitle">{{ suggestion.subtitle }}</span>
            </button>
          </div>
        </div>
      </div>

      <div v-if="showPreferredTime" class="form-group">
        <label>{{ preferredTimeLabel }}</label>
        <div class="time-options" role="radiogroup" :aria-label="preferredTimeLabel">
          <button
            v-for="option in preferredTimeOptions"
            :key="option"
            type="button"
            class="time-option"
            :class="{ active: form.preferredTime === option }"
            :aria-pressed="form.preferredTime === option"
            @click="form.preferredTime = option"
          >
            {{ option }}
          </button>
        </div>
        <p class="field-hint">{{ preferredTimeHint }}</p>
      </div>

      <div class="form-group">
        <label for="message">{{ commentLabel }}</label>
        <textarea 
          id="message" 
          v-model="form.message" 
          rows="3" 
          :placeholder="commentPlaceholder"
        ></textarea>
      </div>

      <button type="submit" class="btn btn-primary" :disabled="isSubmitting">
        <span v-if="isSubmitting">Отправка...</span>
        <span v-else class="flex-center">
          {{ buttonText }}
          <span class="material-icons-round ml-2">send</span>
        </span>
      </button>

      <p class="privacy">
        Нажимая кнопку, вы соглашаетесь с
        <a href="/privacy/">политикой обработки персональных данных</a>.
      </p>
    </form>
  </div>
</template>

<style scoped>
.contact-form-container {
  padding: 1.5rem;
  min-height: 480px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  box-sizing: border-box;
  max-width: 100%;
}

@media (min-width: 768px) {
  .contact-form-container {
    padding: 2.5rem;
  }
}

.contact-form {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

h3 {
  font-size: 1.5rem;
  font-weight: 700;
  margin: 0;
  line-height: 1.2;
}

.subtitle {
  color: var(--text-muted);
  font-size: 0.9rem;
  margin-top: -0.5rem;
  margin-bottom: 0.5rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

label {
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--text-muted);
}

input, textarea {
  padding: 0.75rem 1rem;
  border-radius: 0.75rem;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text);
  font-family: inherit;
  font-size: 1rem;
  transition: all 0.2s;
}

input:focus, textarea:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(0, 127, 128, 0.1);
}

.input-with-loader {
  position: relative;
}

.input-with-loader input {
  padding-right: 2.75rem;
}

.address-suggest {
  position: relative;
}

.suggest-dropdown {
  position: absolute;
  top: calc(100% + 0.4rem);
  left: 0;
  right: 0;
  z-index: 20;
  background: var(--panel-glass-bg);
  border: 1px solid var(--panel-glass-border);
  border-radius: 0.875rem;
  box-shadow: var(--panel-glass-shadow);
  overflow: hidden;
  backdrop-filter: blur(18px);
}

.suggest-option {
  width: 100%;
  border: 0;
  background: transparent;
  color: inherit;
  padding: 0.8rem 1rem;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.suggest-option + .suggest-option {
  border-top: 1px solid var(--panel-chip-border);
}

.suggest-option:hover {
  background: var(--panel-chip-bg);
}

.suggest-title {
  font-weight: 600;
  color: var(--text);
}

.suggest-subtitle {
  color: var(--text-muted);
  font-size: 0.86rem;
}

.loader-icon {
  position: absolute;
  right: 1rem;
  top: 50%;
  color: var(--primary);
  transform: translateY(-50%);
  animation: spin 1s linear infinite;
  font-size: 1.2rem;
}

.time-options {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.time-option {
  border: 1px solid var(--panel-chip-border);
  background: var(--panel-chip-bg);
  color: var(--text);
  border-radius: 999px;
  padding: 0.55rem 0.75rem;
  font: inherit;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.2s ease, transform 0.2s ease;
}

.time-option:hover {
  border-color: var(--panel-chip-hover-border);
}

.time-option.active {
  background: var(--panel-active-gradient);
  border-color: transparent;
  color: var(--panel-active-text);
}

.field-hint {
  color: var(--text-muted);
  font-size: 0.82rem;
  line-height: 1.4;
  margin: 0;
}

.btn {
  margin-top: 0.5rem;
  justify-content: center;
  font-size: 1rem;
  padding: 0.875rem;
}

.flex-center {
  display: flex;
  align-items: center;
  justify-content: center;
}

.ml-2 {
  margin-left: 0.5rem;
}

.privacy {
  font-size: 0.75rem;
  color: var(--text-muted);
  text-align: center;
  line-height: 1.4;
  opacity: 0.8;
}

.privacy a {
  color: var(--primary);
  font-weight: 600;
}

.privacy a:hover {
  color: var(--primary-dark);
}

.success-message {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  animation: fadeIn 0.5s ease;
}

.icon-box {
  width: 64px;
  height: 64px;
  background: #dcfce7;
  color: #166534;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.icon-box .material-icons-round {
  font-size: 2rem;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes spin {
  to { transform: translateY(-50%) rotate(360deg); }
}
</style>
