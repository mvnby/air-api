<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue';
import type { Component } from 'vue';
import { Package, ShoppingCart, Users, UserPlus, Zap, Loader2, Menu, X, Sun, Moon, Calendar, Home, Settings, Wallet, ChevronLeft, ChevronRight, ChevronDown, Tags, FileSpreadsheet, Link2, Award, Database, Calculator, ReceiptText, Image as ImageIcon, ShieldCheck, Truck, Mail, AlertTriangle } from 'lucide-vue-next';
import { api } from './api';
import { getApiErrorMessage } from './utils/api-errors';
import type { TelegramLoginPayload } from './api';

const ProductsView = defineAsyncComponent(() => import('./views/ProductsView.vue'));
const MediaLibraryView = defineAsyncComponent(() => import('./views/MediaLibraryView.vue'));
const CustomersView = defineAsyncComponent(() => import('./views/CustomersView.vue'));
const CustomerProfileView = defineAsyncComponent(() => import('./views/CustomerProfileView.vue'));
const OrdersKanbanView = defineAsyncComponent(() => import('./views/OrdersKanbanView.vue'));
const LeadsView = defineAsyncComponent(() => import('./views/LeadsView.vue'));
const CalendarDashboard = defineAsyncComponent(() => import('./views/CalendarDashboard.vue'));
const ManagerHomeView = defineAsyncComponent(() => import('./views/ManagerHome.vue'));
const InstallersView = defineAsyncComponent(() => import('./views/InstallersView.vue'));
const SettingsView = defineAsyncComponent(() => import('./views/SettingsView.vue'));
const SettingsBackupView = defineAsyncComponent(() => import('./views/SettingsBackupView.vue'));
const TariffsView = defineAsyncComponent(() => import('./views/TariffsView.vue'));
const ServiceEstimatesView = defineAsyncComponent(() => import('./views/ServiceEstimatesView.vue'));
const BankReceiptsView = defineAsyncComponent(() => import('./views/BankReceiptsView.vue'));
const OutgoingEmailsView = defineAsyncComponent(() => import('./views/OutgoingEmailsView.vue'));
const TagsView = defineAsyncComponent(() => import('./views/TagsView.vue'));
const BrandsView = defineAsyncComponent(() => import('./views/BrandsView.vue'));
const SupplierFeedsView = defineAsyncComponent(() => import('./views/SupplierFeedsView.vue'));
const SupplierMappingView = defineAsyncComponent(() => import('./views/SupplierMappingView.vue'));
const CatalogQualityView = defineAsyncComponent(() => import('./views/CatalogQualityView.vue'));
const SupplyRequestsView = defineAsyncComponent(() => import('./views/SupplyRequestsView.vue'));

const isAuthenticated = ref(false);
const showLoginModal = ref(false);
const loginUsername = ref('');
const loginPassword = ref('');
const loginLoading = ref(false);
const loginError = ref('');
const telegramLoginLoading = ref(false);
const telegramLoginContainer = ref<HTMLElement | null>(null);
const rebuildLoading = ref(false);
const webRebuildStatus = ref<WebRebuildStatus | null>(null);
const isMobileNavOpen = ref(false);
const isDesktopNavCollapsed = ref(false);
const theme = ref<'light' | 'dark'>('light');
const leadsCount = ref(0);
const toast = ref('');
const toastType = ref<'success' | 'error'>('success');

const currentLocation = ref(`${window.location.pathname}${window.location.search}`);
const THEME_STORAGE_KEY = 'manager_theme';
const NAV_SECTIONS_STORAGE_KEY = 'manager_nav_sections_v1';
const telegramLoginBotUsername = String(import.meta.env.VITE_TELEGRAM_LOGIN_BOT_USERNAME || '').trim();
const telegramCallbackName = 'onTelegramManagerAuth';
let webRebuildStatusInterval: ReturnType<typeof window.setInterval> | null = null;

type WebRebuildStatus = {
  current_revision: number;
  current_revision_updated_at: string;
  published_revision: number;
  published_at?: string | null;
  requested_revision?: number | null;
  requested_at?: string | null;
  needs_rebuild: boolean;
  state: string;
  last_error?: string | null;
};

type NavItem = {
  path: string;
  label: string;
  icon: Component;
  match?: 'exact' | 'prefix';
};

type NavSectionId = 'catalog' | 'services' | 'team' | 'finance' | 'mail' | 'system';

type NavSection = {
  id: NavSectionId;
  label: string;
  items: NavItem[];
};

declare global {
  interface Window {
    onTelegramManagerAuth?: (user: TelegramLoginPayload) => void;
  }
}

const coreNavItems: NavItem[] = [
  { path: '/manager', label: 'Главная', icon: Home, match: 'exact' },
  { path: '/manager/leads', label: 'Лиды', icon: UserPlus, match: 'prefix' },
  { path: '/manager/orders/kanban', label: 'Заказы', icon: ShoppingCart, match: 'prefix' },
  { path: '/manager/calendar', label: 'Календарь', icon: Calendar, match: 'prefix' },
  { path: '/manager/customers', label: 'Клиенты', icon: Users, match: 'prefix' },
];

const navSections: NavSection[] = [
  {
    id: 'catalog',
    label: 'Каталог',
    items: [
      { path: '/manager/products', label: 'Кондиционеры', icon: Package, match: 'prefix' },
      { path: '/manager/catalog-quality', label: 'Качество каталога', icon: ShieldCheck, match: 'prefix' },
      { path: '/manager/suppliers', label: 'Прайсы поставщиков', icon: FileSpreadsheet, match: 'prefix' },
      { path: '/manager/supply', label: 'Поставки', icon: Truck, match: 'prefix' },
      { path: '/manager/supplier-mapping', label: 'Маппинг прайсов', icon: Link2, match: 'prefix' },
      { path: '/manager/brands', label: 'Бренды', icon: Award, match: 'prefix' },
      { path: '/manager/tags', label: 'Теги', icon: Tags, match: 'prefix' },
      { path: '/manager/media', label: 'Медиатека', icon: ImageIcon, match: 'exact' },
    ],
  },
  {
    id: 'services',
    label: 'Услуги',
    items: [
      { path: '/manager/tariffs', label: 'Тарифы услуг', icon: Wallet, match: 'prefix' },
      { path: '/manager/service-estimates', label: 'Сметы услуг', icon: Calculator, match: 'prefix' },
    ],
  },
  {
    id: 'team',
    label: 'Команда',
    items: [
      { path: '/manager/staff', label: 'Сотрудники', icon: Users, match: 'prefix' },
    ],
  },
  {
    id: 'finance',
    label: 'Финансы',
    items: [
      { path: '/manager/payments', label: 'Платежи', icon: ReceiptText, match: 'prefix' },
    ],
  },
  {
    id: 'mail',
    label: 'Почта',
    items: [
      { path: '/manager/mail/outbox', label: 'Исходящие', icon: Mail, match: 'prefix' },
    ],
  },
  {
    id: 'system',
    label: 'Системное',
    items: [
      { path: '/manager/settings', label: 'Настройки сайта', icon: Settings, match: 'exact' },
      { path: '/manager/settings/backup', label: 'DR / Бэкапы', icon: Database, match: 'prefix' },
    ],
  },
];

const defaultExpandedNavSections: Record<NavSectionId, boolean> = {
  catalog: true,
  services: true,
  team: true,
  finance: true,
  mail: true,
  system: true,
};

const expandedNavSections = ref<Record<NavSectionId, boolean>>({ ...defaultExpandedNavSections });

const normalizePath = (path: string) => {
  if (path.length > 1 && path.endsWith('/')) {
    return path.slice(0, -1);
  }
  return path;
};

const currentPath = computed(() => normalizePath(currentLocation.value.split('?')[0] || '/manager'));

const isNavItemActive = (item: NavItem) => {
  if (item.match === 'exact') return currentPath.value === item.path;
  return currentPath.value === item.path || currentPath.value.startsWith(`${item.path}/`);
};

const isNavSectionActive = (section: NavSection) => section.items.some(isNavItemActive);

const loadExpandedNavSections = () => {
  try {
    const storedValue = window.localStorage.getItem(NAV_SECTIONS_STORAGE_KEY);
    if (!storedValue) return;
    const parsed = JSON.parse(storedValue) as Partial<Record<NavSectionId, boolean>>;
    expandedNavSections.value = {
      ...defaultExpandedNavSections,
      ...Object.fromEntries(
        Object.entries(parsed).filter(([, value]) => typeof value === 'boolean'),
      ),
    } as Record<NavSectionId, boolean>;
  } catch {
    expandedNavSections.value = { ...defaultExpandedNavSections };
  }
};

const expandActiveNavSection = () => {
  const activeSection = navSections.find(isNavSectionActive);
  if (activeSection && !expandedNavSections.value[activeSection.id]) {
    expandedNavSections.value = {
      ...expandedNavSections.value,
      [activeSection.id]: true,
    };
  }
};

const toggleNavSection = (sectionId: NavSectionId) => {
  expandedNavSections.value = {
    ...expandedNavSections.value,
    [sectionId]: !expandedNavSections.value[sectionId],
  };
};

const currentView = computed(() => {
  const path = currentPath.value;
  if (path === '/manager' || path === '/manager/') return 'home';
  if (path.startsWith('/manager/leads')) return 'leads';
  if (path.startsWith('/manager/orders')) return 'orders';
  if (path.startsWith('/manager/calendar')) return 'calendar';
  if (path.startsWith('/manager/media')) return 'media-library';
  if (path.startsWith('/manager/catalog-quality')) return 'catalog-quality';
  if (path.startsWith('/manager/customers/profile')) return 'customer-profile';
  if (path.startsWith('/manager/customers')) return 'customers';
  if (path.startsWith('/manager/staff') || path.startsWith('/manager/users') || path.startsWith('/manager/installers')) return 'installers';
  if (path.startsWith('/manager/settings/backup')) return 'settings-backup';
  if (path.startsWith('/manager/settings')) return 'settings';
  if (path.startsWith('/manager/tariffs')) return 'tariffs';
  if (path.startsWith('/manager/service-estimates')) return 'service-estimates';
  if (path.startsWith('/manager/mail/outbox')) return 'outgoing-emails';
  if (path.startsWith('/manager/payments')) return 'payments';
  if (path.startsWith('/manager/tags')) return 'tags';
  if (path.startsWith('/manager/brands')) return 'brands';
  if (path.startsWith('/manager/supply')) return 'supply';
  if (path.startsWith('/manager/suppliers')) return 'suppliers';
  if (path.startsWith('/manager/supplier-mapping')) return 'supplier-mapping';
  return 'products';
});

const webRebuildNeedsAttention = computed(() => Boolean(webRebuildStatus.value?.needs_rebuild));
const webRebuildQueued = computed(() => webRebuildStatus.value?.state === 'queued');
const webRebuildNoticeVisible = computed(() => (
  webRebuildNeedsAttention.value || Boolean(webRebuildStatus.value?.last_error)
));

const webRebuildNoticeClass = computed(() => {
  if (webRebuildQueued.value) return 'border-blue-200 bg-blue-50 text-blue-900';
  if (webRebuildNeedsAttention.value || webRebuildStatus.value?.last_error) {
    return 'border-amber-200 bg-amber-50 text-amber-900';
  }
  return 'border-gray-200 bg-gray-50 text-gray-700';
});

const webRebuildNoticeTitle = computed(() => {
  if (webRebuildQueued.value) return 'Сборка запущена';
  if (webRebuildNeedsAttention.value) return 'Сайт устарел';
  return 'Статика актуальна';
});

const webRebuildNoticeText = computed(() => {
  if (webRebuildQueued.value) {
    return 'GitHub Actions собирает Astro. После deploy предупреждение снимется.';
  }
  if (webRebuildNeedsAttention.value) {
    return 'Каталог изменился после последней публикации. Нужна пересборка сайта.';
  }
  return 'Опубликована текущая ревизия каталога.';
});

const rebuildButtonLabel = computed(() => {
  if (rebuildLoading.value) return 'Сборка...';
  if (webRebuildNeedsAttention.value) return 'Пересобрать сайт';
  return 'Обновить сайт';
});

const rebuildButtonTitle = computed(() => {
  if (!isDesktopNavCollapsed.value) return '';
  if (webRebuildNeedsAttention.value) return 'Статика устарела - пересобрать сайт';
  return 'Обновить сайт';
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

const setToast = (message: string, type: 'success' | 'error' = 'success') => {
  toast.value = message;
  toastType.value = type;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 3000);
};

const fetchWebRebuildStatus = async () => {
  try {
    webRebuildStatus.value = await api.getWebRebuildStatus() as WebRebuildStatus;
  } catch {
    // Non-critical status widget; the rebuild button reports its own errors.
  }
};

const handleLogin = async () => {
  loginLoading.value = true;
  loginError.value = '';
  try {
    await api.login(loginUsername.value, loginPassword.value);
    isAuthenticated.value = true;
    showLoginModal.value = false;
    loginPassword.value = '';
    void fetchLeadsCount();
    void fetchWebRebuildStatus();
  } catch {
    loginError.value = 'Неверный логин или пароль';
  } finally {
    loginLoading.value = false;
  }
};

const handleTelegramLogin = async (payload: TelegramLoginPayload) => {
  telegramLoginLoading.value = true;
  loginError.value = '';
  try {
    await api.loginTelegram(payload);
    isAuthenticated.value = true;
    showLoginModal.value = false;
    void fetchLeadsCount();
    void fetchWebRebuildStatus();
  } catch (err) {
    loginError.value = getApiErrorMessage(err) || 'Не удалось войти через Telegram';
  } finally {
    telegramLoginLoading.value = false;
  }
};

const renderTelegramLogin = async () => {
  if (!telegramLoginBotUsername || !showLoginModal.value) return;
  await nextTick();
  const container = telegramLoginContainer.value;
  if (!container) return;
  container.innerHTML = '';
  window[telegramCallbackName] = (user: TelegramLoginPayload) => {
    void handleTelegramLogin(user);
  };

  const script = document.createElement('script');
  script.src = 'https://telegram.org/js/telegram-widget.js?22';
  script.async = true;
  script.setAttribute('data-telegram-login', telegramLoginBotUsername);
  script.setAttribute('data-size', 'large');
  script.setAttribute('data-userpic', 'false');
  script.setAttribute('data-request-access', 'write');
  script.setAttribute('data-onauth', `${telegramCallbackName}(user)`);
  container.appendChild(script);
};

const handleRebuild = async () => {
  if (!confirm('Вы уверены, что хотите обновить сайт? Это займет около 2 минут.')) return;
  rebuildLoading.value = true;
  try {
    const result = await api.rebuildWeb();
    webRebuildStatus.value = result as WebRebuildStatus;
    setToast(String(result.message || 'Сборка запущена. Сайт обновится через пару минут.'));
    void fetchWebRebuildStatus();
  } catch (err) {
    setToast(`Ошибка при запуске сборки: ${getApiErrorMessage(err)}`, 'error');
  } finally {
    rebuildLoading.value = false;
  }
};

const fetchLeadsCount = async () => {
  try {
    const counter = await api.getLeadsCounter();
    leadsCount.value = counter.count;
  } catch {
    // Badge is non-critical — silence errors
  }
};

const checkAuth = async () => {
  try {
    await api.checkAuth();
    isAuthenticated.value = true;
    // Fetch the badge count once authenticated
    void fetchLeadsCount();
    void fetchWebRebuildStatus();
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
  loadExpandedNavSections();
  expandActiveNavSection();
  if (window.location.pathname === '/manager') {
    navigate('/manager');
  }
  window.addEventListener('popstate', onPopState);
  webRebuildStatusInterval = window.setInterval(() => {
    if (isAuthenticated.value) void fetchWebRebuildStatus();
  }, 60_000);
  checkAuth();
});

onBeforeUnmount(() => {
  window.removeEventListener('popstate', onPopState);
  if (webRebuildStatusInterval) {
    window.clearInterval(webRebuildStatusInterval);
    webRebuildStatusInterval = null;
  }
  delete window[telegramCallbackName];
});

watch(showLoginModal, (visible) => {
  if (visible) {
    void renderTelegramLogin();
  }
});

watch(expandedNavSections, (value) => {
  window.localStorage.setItem(NAV_SECTIONS_STORAGE_KEY, JSON.stringify(value));
}, { deep: true });

watch(currentPath, () => {
  expandActiveNavSection();
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
      <h2 class="text-2xl font-bold mb-6 text-center text-gray-900">Вход в менеджер</h2>
      <form @submit.prevent="handleLogin" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Логин</label>
          <input
            v-model="loginUsername"
            type="text"
            required
            class="w-full border border-gray-300 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent"
            placeholder="Введите логин"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Пароль</label>
          <input
            v-model="loginPassword"
            type="password"
            required
            class="w-full border border-gray-300 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent"
            placeholder="Введите пароль"
          />
        </div>
        <div v-if="loginError" class="text-red-600 text-sm">{{ loginError }}</div>
        <button
          type="submit"
          :disabled="loginLoading"
          class="w-full bg-teal-600 text-white py-2.5 rounded-lg hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium transition-colors"
        >
          {{ loginLoading ? 'Входим...' : 'Войти' }}
        </button>
        <div v-if="telegramLoginBotUsername" class="pt-2">
          <div class="mb-3 flex items-center gap-3 text-xs uppercase tracking-[0.18em] text-gray-400">
            <span class="h-px flex-1 bg-gray-200" />
            <span>или</span>
            <span class="h-px flex-1 bg-gray-200" />
          </div>
          <div
            ref="telegramLoginContainer"
            class="flex min-h-[44px] justify-center"
            :class="telegramLoginLoading ? 'pointer-events-none opacity-60' : ''"
          />
        </div>
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
      class="fixed inset-y-0 left-0 z-50 bg-white border-r border-gray-200 flex flex-col shrink-0 transition-all duration-300 md:static md:z-auto md:translate-x-0"
      :class="[
        isMobileNavOpen ? 'translate-x-0 w-72' : '-translate-x-full w-72',
        isDesktopNavCollapsed ? 'md:w-20' : 'md:w-60'
      ]"
    >
      <div class="p-5 border-b border-gray-100 relative min-h-[76px] flex flex-col justify-center">
        <div class="flex items-center gap-3" :class="isDesktopNavCollapsed ? 'md:justify-center' : ''">
          <div class="w-9 h-9 shrink-0 bg-teal-600 rounded-lg flex items-center justify-center cursor-pointer" @click="navigate('/manager')">
            <Package class="w-5 h-5 text-white" />
          </div>
          <div :class="isDesktopNavCollapsed ? 'md:hidden' : ''">
            <div class="font-bold text-gray-900 text-sm leading-tight">Мастер Воздуха</div>
            <div class="text-[11px] text-gray-400">Manager Panel</div>
          </div>
        </div>

        <!-- Desktop Toggle -->
        <button
          class="hidden md:flex absolute -right-3 top-6 w-6 h-6 bg-white border border-gray-200 rounded-full items-center justify-center text-gray-400 hover:text-teal-600 transition-colors shadow-sm z-10"
          @click="isDesktopNavCollapsed = !isDesktopNavCollapsed"
        >
          <ChevronRight v-if="isDesktopNavCollapsed" class="w-4 h-4" />
          <ChevronLeft v-else class="w-4 h-4" />
        </button>

        <button
          v-if="!isDesktopNavCollapsed"
          class="mt-3 inline-flex items-center justify-center gap-2 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
          @click="toggleTheme"
        >
          <Moon v-if="theme === 'light'" class="h-3.5 w-3.5" />
          <Sun v-else class="h-3.5 w-3.5" />
          {{ theme === 'light' ? 'Тёмная тема' : 'Светлая тема' }}
        </button>
      </div>

      <nav class="flex-1 overflow-y-auto p-3 space-y-2">
        <div class="space-y-1">
          <button
            v-for="item in coreNavItems"
            :key="item.path"
            class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors text-left relative"
            :class="[
              isNavItemActive(item)
                ? 'bg-teal-50 text-teal-700'
                : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900',
              isDesktopNavCollapsed ? 'md:justify-center md:px-0' : ''
            ]"
            @click="navigate(item.path)"
            :title="isDesktopNavCollapsed ? item.label : ''"
          >
            <component :is="item.icon" class="w-5 h-5 shrink-0" />
            <span class="flex-1 truncate" :class="isDesktopNavCollapsed ? 'md:hidden' : ''">{{ item.label }}</span>
            <span
              v-if="item.path === '/manager/leads' && leadsCount > 0"
              class="inline-flex items-center justify-center font-bold bg-red-500 text-white shrink-0"
              :class="isDesktopNavCollapsed ? 'md:absolute md:top-1 md:right-1 h-3 w-3 rounded-full text-[0px]' : 'min-w-[20px] h-5 px-1 rounded-full text-[11px]'"
            >
              {{ isDesktopNavCollapsed ? '' : leadsCount }}
            </span>
          </button>
        </div>

        <div
          v-for="section in navSections"
          :key="section.id"
          class="border-t border-gray-100 pt-2"
        >
          <button
            class="mb-1 flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-left text-[11px] font-bold uppercase tracking-[0.16em] transition-colors"
            :class="[
              isNavSectionActive(section)
                ? 'text-teal-700'
                : 'text-gray-400 hover:bg-gray-50 hover:text-gray-600',
              isDesktopNavCollapsed ? 'md:justify-center md:px-0' : ''
            ]"
            @click="toggleNavSection(section.id)"
            :title="isDesktopNavCollapsed ? section.label : ''"
            :aria-expanded="expandedNavSections[section.id]"
          >
            <span class="min-w-0 flex-1 truncate" :class="isDesktopNavCollapsed ? 'md:hidden' : ''">{{ section.label }}</span>
            <ChevronDown
              class="h-3.5 w-3.5 shrink-0 transition-transform"
              :class="[
                expandedNavSections[section.id] ? 'rotate-0' : '-rotate-90',
                isDesktopNavCollapsed ? 'md:h-4 md:w-4' : ''
              ]"
            />
          </button>

          <div
            v-show="expandedNavSections[section.id]"
            class="space-y-1 border-l border-gray-100 pl-3 ml-3 md:transition-all"
            :class="isDesktopNavCollapsed ? 'md:ml-0 md:border-l-0 md:pl-0' : ''"
          >
            <button
              v-for="item in section.items"
              :key="item.path"
              class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors text-left relative"
              :class="[
                isNavItemActive(item)
                  ? 'bg-teal-50 text-teal-700'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900',
                isDesktopNavCollapsed ? 'md:justify-center md:px-0' : ''
              ]"
              @click="navigate(item.path)"
              :title="isDesktopNavCollapsed ? item.label : ''"
            >
              <component :is="item.icon" class="w-5 h-5 shrink-0" />
              <span class="flex-1 truncate" :class="isDesktopNavCollapsed ? 'md:hidden' : ''">{{ item.label }}</span>
            </button>
          </div>
        </div>
      </nav>

      <div class="p-3 border-t border-gray-100 mt-auto">
        <div
          v-if="webRebuildNoticeVisible && !isDesktopNavCollapsed"
          class="mb-2 rounded-lg border px-3 py-2 text-xs leading-snug"
          :class="webRebuildNoticeClass"
        >
          <div class="flex items-center gap-2 font-semibold">
            <Loader2 v-if="webRebuildQueued" class="h-4 w-4 animate-spin shrink-0" />
            <AlertTriangle v-else class="h-4 w-4 shrink-0" />
            <span>{{ webRebuildNoticeTitle }}</span>
          </div>
          <p class="mt-1">{{ webRebuildNoticeText }}</p>
          <p v-if="webRebuildStatus?.last_error" class="mt-1 break-words text-red-700">
            {{ webRebuildStatus.last_error }}
          </p>
        </div>
        <button
          class="relative w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all"
          :class="[
            rebuildLoading
              ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
              : webRebuildNeedsAttention
                ? 'bg-amber-500 text-white hover:bg-amber-600 shadow-sm hover:shadow-md'
                : 'bg-teal-600 text-white hover:bg-teal-700 shadow-sm hover:shadow-md',
            isDesktopNavCollapsed ? 'justify-center' : ''
          ]"
          :disabled="rebuildLoading"
          @click="handleRebuild"
          :title="rebuildButtonTitle"
        >
          <span
            v-if="isDesktopNavCollapsed && webRebuildNeedsAttention"
            class="absolute right-1 top-1 h-2.5 w-2.5 rounded-full bg-amber-300 ring-2 ring-white"
          />
          <Loader2 v-if="rebuildLoading" class="w-5 h-5 animate-spin shrink-0" />
          <Zap v-else class="w-5 h-5 shrink-0" />
          <span v-if="!isDesktopNavCollapsed">{{ rebuildButtonLabel }}</span>
        </button>
      </div>
    </aside>

    <main class="flex-1 overflow-auto md:ml-0">
      <ManagerHomeView v-if="currentView === 'home'" :key="currentLocation" />
      <LeadsView v-else-if="currentView === 'leads'" :key="currentLocation" />
      <OrdersKanbanView v-else-if="currentView === 'orders'" :key="currentLocation" />
      <CalendarDashboard v-else-if="currentView === 'calendar'" :key="currentLocation" />
      <MediaLibraryView v-else-if="currentView === 'media-library'" :key="currentLocation" />
      <CatalogQualityView v-else-if="currentView === 'catalog-quality'" :key="currentLocation" />
      <CustomerProfileView v-else-if="currentView === 'customer-profile'" :key="currentLocation" />
      <CustomersView v-else-if="currentView === 'customers'" :key="currentLocation" />
      <InstallersView v-else-if="currentView === 'installers'" :key="currentLocation" />
      <SettingsBackupView v-else-if="currentView === 'settings-backup'" :key="currentLocation" />
      <SettingsView v-else-if="currentView === 'settings'" :key="currentLocation" />
      <TariffsView v-else-if="currentView === 'tariffs'" :key="currentLocation" />
      <ServiceEstimatesView v-else-if="currentView === 'service-estimates'" :key="currentLocation" />
      <OutgoingEmailsView v-else-if="currentView === 'outgoing-emails'" :key="currentLocation" />
      <BankReceiptsView v-else-if="currentView === 'payments'" :key="currentLocation" />
      <TagsView v-else-if="currentView === 'tags'" :key="currentLocation" />
      <BrandsView v-else-if="currentView === 'brands'" :key="currentLocation" />
      <SupplyRequestsView v-else-if="currentView === 'supply'" :key="currentLocation" />
      <SupplierFeedsView v-else-if="currentView === 'suppliers'" :key="currentLocation" />
      <SupplierMappingView v-else-if="currentView === 'supplier-mapping'" :key="currentLocation" />
      <ProductsView v-else :key="currentLocation" />
    </main>

    <Transition name="fade">
      <div
        v-if="toast"
        class="fixed top-6 right-6 z-[100] rounded-xl px-6 py-3 font-medium text-white shadow-2xl"
        :class="toastType === 'success' ? 'bg-teal-600' : 'bg-red-600'"
      >
        {{ toast }}
      </div>
    </Transition>
  </div>
</template>
