<script setup>
import { ref } from 'vue';
import { submitContactForm } from '../utils/api';

const form = ref({
  name: '',
  phone: '',
  message: ''
});

const isSubmitting = ref(false);
const isSuccess = ref(false);

const submitForm = async () => {
  isSubmitting.value = true;
  
  const success = await submitContactForm(form.value);
  
  isSubmitting.value = false;
  
  if (success) {
    isSuccess.value = true;
    // Reset after 5 seconds
    setTimeout(() => {
        isSuccess.value = false;
        form.value = { name: '', phone: '', message: '' };
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
      <h3>Оставить заявку</h3>
      <p class="subtitle">Перезвоним в течение 15 минут</p>

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
          v-model="form.phone" 
          placeholder="+375 (XX) XXX-XX-XX"
          required
        >
      </div>

      <div class="form-group">
        <label for="message">Комментарий (необязательно)</label>
        <textarea 
          id="message" 
          v-model="form.message" 
          rows="3" 
          placeholder="Меня интересует установка..."
        ></textarea>
      </div>

      <button type="submit" class="btn btn-primary" :disabled="isSubmitting">
        <span v-if="isSubmitting">Отправка...</span>
        <span v-else class="flex-center">
          Отправить
          <span class="material-icons-round ml-2">send</span>
        </span>
      </button>

      <p class="privacy">
        Нажимая кнопку, вы соглашаетесь с политикой обработки персональных данных.
      </p>
    </form>
  </div>
</template>

<style scoped>
.contact-form-container {
  padding: 2.5rem;
  min-height: 480px;
  display: flex;
  flex-direction: column;
  justify-content: center;
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
</style>
