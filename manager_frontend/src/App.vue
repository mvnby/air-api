<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onBeforeUnmount, ref } from 'vue';
import { Package, ShoppingCart, Users, UserPlus, Zap, Loader2, Menu, X, Sun, Moon, Calendar, Home, Wrench } from 'lucide-vue-next';
import { api } from './api';

const ProductsView = defineAsyncComponent(() => import('./views/ProductsView.vue'));
const CustomersView = defineAsyncComponent(() => import('./views/CustomersView.vue'));
const CustomerProfileView = defineAsyncComponent(() => import('./views/CustomerProfileView.vue'));
const OrdersKanbanView = defineAsyncComponent(() => import('./views/OrdersKanbanView.vue'));
const LeadsView = defineAsyncComponent(() => import('./views/LeadsView.vue'));
const CalendarDashboard = defineAsyncComponent(() => import('./views/CalendarDashboard.vue'));
const ManagerHomeView = defineAsyncComponent(() => import('./views/ManagerHome.vue'));
const InstallersView = defineAsyncComponent(() => import('./views/InstallersView.vue'));

const isAuthenticated = ref(false);
const showLoginModal = ref(false);
const loginUsername = ref('');
const loginPassword = ref('');
const loginLoading = ref(false);
const loginError = ref('');
const rebuildLoading = ref(false);
const isMobileNavOpen = ref(false);
const theme = ref<'light' | 'dark'>('light');

const currentLocation = ref(`${window.location.pathname}${window.location.search}`);
const THEME_STORAGE_KEY = 'manager_theme';

const navItems = [
  { path: '/manager', label: 'Главная', icon: Home },
  { path: '/manager/leads', label: 'Лиды', icon: UserPlus },
  { path: '/manager/orders/kanban', label: 'Заказы', icon: ShoppingCart },
  { path: '/manager/calendar', label: 'Календарь', icon: Calendar },
  { path: '/manager/products', label: 'Кондиционеры', icon: Package },
  { path: '/manager/customers', label: 'Клиенты', icon: Users },
  { path: '/manager/installers', label: 'Монтажники', icon: Wrench },
];

const currentView = computed(() => {
  const path = currentLocation.value.split('?')[0] || '/manager';
  if (path === '/manager' || path === '/manager/') return 'home';
  if (path.startsWith('/manager/leads')) return 'leads';
  if (path.startsWith('/manager/orders')) return 'orders';
  if (path.startsWith('/manager/calendar')) return 'calendar';
  if (path.startsWith('/manager/customers/profile')) return 'customer-profile';
  if (path.startsWith('/manager/customers')) return 'customers';
  if (path.startsWith('/manager/installers')) return 'installers';
  return 'products';
});

const onPopState = () => {
  currentLocation.value = `${window.location.pathname}${window.location.search}`;
};

const navigate = (path: string) => {
  if (window.location.pathname !== path) {
    window.history.pushState({}, '', path);
    currentLocation.value = `${window.location.pathname}${window.location.search}`;
  }
  isMobileNavOpen.value = false;
};

const toggleMobileNav = () => {
  isMobileNavOpen.value = !isMobileNavOpen.value;
};

const closeMobileNav = () => {
  isMobileNavOpen.value = false;
};

const applyTheme = (value: 'light' | 'dark') => {
  theme.value = value;
  document.documentElement.classList.toggle('dark', value === 'dark');
  window.localStorage.setItem(THEME_STORAGE_KEY, value);
};

const toggleTheme = () => {
  applyTheme(theme.value === 'light' ? 'dark' : 'light');
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
  const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
  if (storedTheme === 'light' || storedTheme === 'dark') {
    applyTheme(storedTheme);
  } else {
    applyTheme('light');
  }
  if (window.location.pathname === '/manager') {
    navigate('/manager');
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

  <div v-if="isAuthenticated" class="manager-root min-h-screen flex">
    <button
      class="fixed left-3 top-3 z-50 inline-flex h-10 w-10 items-center justify-center rounded-lg border border-gray-200 bg-white text-gray-700 shadow md:hidden"
      @click="toggleMobileNav"
    >
      <X v-if="isMobileNavOpen" class="h-5 w-5" />
      <Menu v-else class="h-5 w-5" />
    </button>

    <div
      v-if="isMobileNavOpen"
      class="fixed inset-0 z-40 bg-black/40 md:hidden"
      @click="closeMobileNav"
    />

    <aside
      class="fixed inset-y-0 left-0 z-50 w-72 bg-white border-r border-gray-200 flex flex-col shrink-0 transition-transform duration-200 md:static md:z-auto md:w-60 md:translate-x-0"
      :class="isMobileNavOpen ? 'translate-x-0' : '-translate-x-full'"
    >
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
        <button
          class="mt-3 inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
          @click="toggleTheme"
        >
          <Moon v-if="theme === 'light'" class="h-3.5 w-3.5" />
          <Sun v-else class="h-3.5 w-3.5" />
          {{ theme === 'light' ? 'Тёмная тема' : 'Светлая тема' }}
        </button>
      </div>

      <nav class="flex-1 p-3 space-y-1">
        <button
          v-for="item in navItems"
          :key="item.path"
          class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors text-left"
          :class="currentLocation.split('?')[0] === item.path
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

    <main class="flex-1 overflow-auto md:ml-0">
      <ManagerHomeView v-if="currentView === 'home'" :key="currentLocation" />
      <LeadsView v-else-if="currentView === 'leads'" :key="currentLocation" />
      <OrdersKanbanView v-else-if="currentView === 'orders'" :key="currentLocation" />
      <CalendarDashboard v-else-if="currentView === 'calendar'" :key="currentLocation" />
      <CustomerProfileView v-else-if="currentView === 'customer-profile'" :key="currentLocation" />
      <CustomersView v-else-if="currentView === 'customers'" :key="currentLocation" />
      <InstallersView v-else-if="currentView === 'installers'" :key="currentLocation" />
      <ProductsView v-else :key="currentLocation" />
    </main>
  </div>
</template>
