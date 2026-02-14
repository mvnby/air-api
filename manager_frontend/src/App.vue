<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue';
import { Package, ShoppingCart, Users, UserPlus, Zap, Loader2 } from 'lucide-vue-next';
import { api } from './api';
import ProductsView from './views/ProductsView.vue';
import CustomersView from './views/CustomersView.vue';
import OrdersKanbanView from './views/OrdersKanbanView.vue';
import LeadsView from './views/LeadsView.vue';

const isAuthenticated = ref(false);
const showLoginModal = ref(false);
const loginUsername = ref('');
const loginPassword = ref('');
const loginLoading = ref(false);
const loginError = ref('');
const rebuildLoading = ref(false);

const currentPath = ref(window.location.pathname);

const navItems = [
  { path: '/manager/leads', label: 'Лиды', icon: UserPlus },
  { path: '/manager/orders/kanban', label: 'Заказы', icon: ShoppingCart },
  { path: '/manager/products', label: 'Кондиционеры', icon: Package },
  { path: '/manager/customers', label: 'Клиенты', icon: Users },
];

const currentView = computed(() => {
  if (currentPath.value.startsWith('/manager/leads')) return 'leads';
  if (currentPath.value.startsWith('/manager/orders')) return 'orders';
  if (currentPath.value.startsWith('/manager/customers')) return 'customers';
  return 'products';
});

const onPopState = () => {
  currentPath.value = window.location.pathname;
};

const navigate = (path: string) => {
  if (window.location.pathname !== path) {
    window.history.pushState({}, '', path);
    currentPath.value = path;
  }
};

const handleLogin = async () => {
  loginLoading.value = true;
  loginError.value = '';
  try {
    await api.login(loginUsername.value, loginPassword.value);
    isAuthenticated.value = true;
    showLoginModal.value = false;
  } catch {
    loginError.value = 'Invalid credentials';
  } finally {
    loginLoading.value = false;
  }
};

const handleRebuild = async () => {
  if (!confirm('Вы уверены, что хотите обновить сайт? Это займет около 2 минут.')) return;
  rebuildLoading.value = true;
  try {
    const result = await api.rebuildWeb();
    alert(result.message || 'Сборка запущена! Сайт обновится через пару минут.');
  } catch (err: any) {
    alert('Ошибка при запуске сборки: ' + err.message);
  } finally {
    rebuildLoading.value = false;
  }
};

const checkAuth = async () => {
  try {
    await api.checkAuth();
    isAuthenticated.value = true;
  } catch {
    isAuthenticated.value = false;
    showLoginModal.value = true;
  }
};

onMounted(() => {
  if (window.location.pathname === '/manager') {
    navigate('/manager/leads');
  }
  window.addEventListener('popstate', onPopState);
  checkAuth();
});

onBeforeUnmount(() => {
  window.removeEventListener('popstate', onPopState);
});
</script>

<template>
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

  <div v-if="isAuthenticated" class="min-h-screen bg-gray-50 flex">
    <aside class="w-60 bg-white border-r border-gray-200 flex flex-col shrink-0">
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

      <nav class="flex-1 p-3 space-y-1">
        <button
          v-for="item in navItems"
          :key="item.path"
          class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors text-left"
          :class="currentPath === item.path
            ? 'bg-teal-50 text-teal-700'
            : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'"
          @click="navigate(item.path)"
        >
          <component :is="item.icon" class="w-5 h-5" />
          {{ item.label }}
        </button>
      </nav>

      <div class="p-3 border-t border-gray-100 mt-auto">
        <button
          class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all"
          :class="rebuildLoading
            ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
            : 'bg-teal-600 text-white hover:bg-teal-700 shadow-sm hover:shadow-md'"
          :disabled="rebuildLoading"
          @click="handleRebuild"
        >
          <Loader2 v-if="rebuildLoading" class="w-5 h-5 animate-spin" />
          <Zap v-else class="w-5 h-5" />
          {{ rebuildLoading ? 'Сборка...' : 'Обновить сайт' }}
        </button>
      </div>
    </aside>

    <main class="flex-1 overflow-auto">
      <LeadsView v-if="currentView === 'leads'" />
      <OrdersKanbanView v-else-if="currentView === 'orders'" />
      <CustomersView v-else-if="currentView === 'customers'" />
      <ProductsView v-else />
    </main>
  </div>
</template>
