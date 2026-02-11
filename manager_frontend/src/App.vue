<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { RouterView, RouterLink, useRoute } from 'vue-router';
import { Package, ShoppingCart, Users } from 'lucide-vue-next';
import { api } from './api';

const route = useRoute();

// Auth state (shared across all views)
const isAuthenticated = ref(false);
const showLoginModal = ref(false);
const loginUsername = ref('');
const loginPassword = ref('');
const loginLoading = ref(false);
const loginError = ref('');

const handleLogin = async () => {
    loginLoading.value = true;
    loginError.value = '';
    try {
        await api.login(loginUsername.value, loginPassword.value);
        isAuthenticated.value = true;
        showLoginModal.value = false;
    } catch (e) {
        loginError.value = 'Invalid credentials';
    } finally {
        loginLoading.value = false;
    }
};

const checkAuth = async () => {
    try {
        await api.checkAuth();
        isAuthenticated.value = true;
    } catch (e) {
        isAuthenticated.value = false;
        showLoginModal.value = true;
    }
};

const navItems = [
    { to: '/products', label: 'Товары', icon: Package },
    { to: '/orders', label: 'Заказы', icon: ShoppingCart },
    { to: '/customers', label: 'Клиенты', icon: Users },
];

onMounted(() => {
    checkAuth();
});
</script>

<template>
  <!-- Login Modal -->
  <div v-if="showLoginModal" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
    <div class="bg-white rounded-xl p-8 max-w-md w-full mx-4 shadow-2xl">
      <div class="flex justify-center mb-6">
        <div class="w-12 h-12 bg-teal-600 rounded-xl flex items-center justify-center">
          <Package class="w-6 h-6 text-white" />
        </div>
      </div>
      <h2 class="text-2xl font-bold mb-6 text-center text-gray-900">Manager Login</h2>
      <form @submit.prevent="handleLogin" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Username</label>
          <input 
            v-model="loginUsername" 
            type="text" 
            required
            class="w-full border border-gray-300 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent"
            placeholder="Enter username"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Password</label>
          <input 
            v-model="loginPassword" 
            type="password" 
            required
            class="w-full border border-gray-300 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent"
            placeholder="Enter password"
          />
        </div>
        <div v-if="loginError" class="text-red-600 text-sm">{{ loginError }}</div>
        <button 
          type="submit" 
          :disabled="loginLoading"
          class="w-full bg-teal-600 text-white py-2.5 rounded-lg hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium transition-colors"
        >
          {{ loginLoading ? 'Logging in...' : 'Login' }}
        </button>
      </form>
    </div>
  </div>

  <!-- Main Layout -->
  <div v-if="isAuthenticated" class="min-h-screen bg-gray-50 flex">
    <!-- Sidebar -->
    <aside class="w-60 bg-white border-r border-gray-200 flex flex-col shrink-0">
      <!-- Logo -->
      <div class="p-5 border-b border-gray-100">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 bg-teal-600 rounded-lg flex items-center justify-center">
            <Package class="w-5 h-5 text-white" />
          </div>
          <div>
            <div class="font-bold text-gray-900 text-sm leading-tight">Мастер Воздуха</div>
            <div class="text-[11px] text-gray-400">Manager Panel</div>
          </div>
        </div>
      </div>

      <!-- Navigation -->
      <nav class="flex-1 p-3 space-y-1">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors"
          :class="route.path === item.to 
            ? 'bg-teal-50 text-teal-700' 
            : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'"
        >
          <component :is="item.icon" class="w-5 h-5" />
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>

    <!-- Content -->
    <main class="flex-1 overflow-auto">
      <RouterView />
    </main>
  </div>
</template>
