<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue';
import { Zap, Loader2, AlertTriangle } from 'lucide-vue-next';
import { api } from './api';
import { getApiErrorMessage } from './utils/api-errors';
import type { TelegramLoginPayload } from './client';
import UiFeedbackHost from './components/common/UiFeedbackHost.vue';
import ManagerAccountMenu from './components/manager/ManagerAccountMenu.vue';
import ManagerLoginModal from './components/manager/ManagerLoginModal.vue';
import ManagerSessionRecoveryModal from './components/manager/ManagerSessionRecoveryModal.vue';
import KitlaneShell from './components/kitlane/KitlaneShell.vue';
import KitlaneNavigation from './components/kitlane/KitlaneNavigation.vue';
import { useKitlaneIdentity } from './composables/useKitlaneIdentity';
import { confirmDialog } from './services/ui-feedback';
import {
  clearManagerSession,
  loginManagerWithPassword,
  loginManagerWithTelegram,
  managerSession,
  restoreManagerSession,
} from './services/manager-session';
import {
  coreNavItems,
  defaultExpandedNavSections,
  navSections,
  type NavItem,
  type NavSection,
  type NavSectionId,
} from './manager-navigation';
import {
  MANAGER_CAPABILITY,
  hasManagerCapability,
  isManagerPathAllowed,
} from './manager-capabilities';
const ProductsView = defineAsyncComponent(() => import('./views/ProductsView.vue'));
const TenantCatalogView = defineAsyncComponent(() => import('./views/TenantCatalogView.vue'));
const CatalogDecisionWorkspaceView = defineAsyncComponent(() => import('./views/CatalogDecisionWorkspaceView.vue'));
const ProductCollectionsView = defineAsyncComponent(() => import('./views/ProductCollectionsView.vue'));
const ProductWorkspaceView = defineAsyncComponent(() => import('./views/ProductWorkspaceView.vue'));
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
const DocumentsSettingsView = defineAsyncComponent(() => import('./views/DocumentsSettingsView.vue'));
const TariffsView = defineAsyncComponent(() => import('./views/TariffsView.vue'));
const InstallationRatesView = defineAsyncComponent(() => import('./views/InstallationRatesView.vue'));
const InstallationDiscountsView = defineAsyncComponent(() => import('./views/InstallationDiscountsView.vue'));
const ServiceEstimatesView = defineAsyncComponent(() => import('./views/ServiceEstimatesView.vue'));
const BankReceiptsView = defineAsyncComponent(() => import('./views/BankReceiptsView.vue'));
const OutgoingEmailsView = defineAsyncComponent(() => import('./views/OutgoingEmailsView.vue'));
const TagsView = defineAsyncComponent(() => import('./views/TagsView.vue'));
const BrandsView = defineAsyncComponent(() => import('./views/BrandsView.vue'));
const FeaturesView = defineAsyncComponent(() => import('./views/FeaturesView.vue'));
const FeatureSeriesMigrationView = defineAsyncComponent(() => import('./views/FeatureSeriesMigrationView.vue'));
const SupplierFeedsView = defineAsyncComponent(() => import('./views/SupplierFeedsView.vue'));
const SupplierMappingView = defineAsyncComponent(() => import('./views/SupplierMappingView.vue'));
const CatalogQualityView = defineAsyncComponent(() => import('./views/CatalogQualityView.vue'));
const SupplyRequestsView = defineAsyncComponent(() => import('./views/SupplyRequestsView.vue'));
const EquipmentRegistryView = defineAsyncComponent(() => import('./views/EquipmentRegistryView.vue'));
const ProfileSecurityView = defineAsyncComponent(() => import('./views/ProfileSecurityView.vue'));
const AnalyticsConnectionsView = defineAsyncComponent(() => import('./views/AnalyticsConnectionsView.vue'));
const props = defineProps<{ reloadPage?: () => void }>();
const { isAuthenticated, auth, recoveryRequired } = managerSession;
const { name: partnerName, contextKey: partnerContextKey } = useKitlaneIdentity();
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
declare global {
  interface Window {
    onTelegramManagerAuth?: (user: TelegramLoginPayload) => void;
  }
}
const expandedNavSections = ref<Record<NavSectionId, boolean>>({ ...defaultExpandedNavSections });
const normalizePath = (path: string) => {
  if (path.length > 1 && path.endsWith('/')) {
    return path.slice(0, -1);
  }
  return path;
};
const currentPath = computed(() => normalizePath(currentLocation.value.split('?')[0] || '/manager'));
const canManagePlatform = computed(() => hasManagerCapability(auth.value, MANAGER_CAPABILITY.platformManage));
const canManageInfrastructure = computed(() => hasManagerCapability(auth.value, MANAGER_CAPABILITY.infrastructureManage));
const canManageDocuments = computed(() => hasManagerCapability(auth.value, MANAGER_CAPABILITY.documentsManage));
const visibleCoreNavItems = computed(() => coreNavItems.filter(
  item => !item.requiredCapability || hasManagerCapability(auth.value, item.requiredCapability),
));
const visibleNavSections = computed<NavSection[]>(() => navSections
  .map(section => ({
    ...section,
    items: section.items.filter(
      item => !item.requiredCapability || hasManagerCapability(auth.value, item.requiredCapability),
    ),
  }))
  .filter(section => section.items.length > 0));
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
  const activeSection = visibleNavSections.value.find(isNavSectionActive);
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
  if (path === '/manager/profile') return 'profile-security';
  if (path.startsWith('/manager/integrations')) return 'analytics-connections';
  if (path.startsWith('/manager/leads')) return 'leads';
  if (path.startsWith('/manager/orders')) return 'orders';
  if (path.startsWith('/manager/calendar')) return 'calendar';
  if (path.startsWith('/manager/equipment')) return 'equipment';
  if (path.startsWith('/manager/media')) return 'media-library';
  if (path.startsWith('/manager/catalog-quality')) return 'catalog-quality';
  if (path.startsWith('/manager/catalog-decision')) return 'catalog-decision';
  if (path.startsWith('/manager/product-collections')) return 'product-collections';
  if (path.startsWith('/manager/customers/profile')) return 'customer-profile';
  if (path.startsWith('/manager/customers')) return 'customers';
  if (path.startsWith('/manager/staff') || path.startsWith('/manager/users') || path.startsWith('/manager/installers')) return 'installers';
  if (path.startsWith('/manager/settings/backup')) return 'settings-backup';
  if (path.startsWith('/manager/settings/documents')) return 'settings-documents';
  if (path.startsWith('/manager/settings')) return 'settings';
  if (path.startsWith('/manager/installation-rates')) return 'installation-rates';
  if (path.startsWith('/manager/installation-discounts')) return 'installation-discounts';
  if (path.startsWith('/manager/tariffs')) return 'tariffs';
  if (path.startsWith('/manager/service-estimates')) return 'service-estimates';
  if (path.startsWith('/manager/mail/outbox')) return 'outgoing-emails';
  if (path.startsWith('/manager/payments')) return 'payments';
  if (path.startsWith('/manager/tags')) return 'tags';
  if (path.startsWith('/manager/brands')) return 'brands';
  if (path.startsWith('/manager/features/series-migration')) return 'feature-series-migration';
  if (path.startsWith('/manager/features')) return 'features';
  if (path.startsWith('/manager/supply')) return 'supply';
  if (path.startsWith('/manager/suppliers')) return 'suppliers';
  if (path.startsWith('/manager/supplier-mapping')) return 'supplier-mapping';
  if (/^\/manager\/products\/\d+(?:\/|$)/.test(path)) return 'product-workspace';
  return 'products';
});
const authorizedView = computed(() => (
  isManagerPathAllowed(auth.value, currentPath.value) ? currentView.value : 'home'
));
const webRebuildNeedsAttention = computed(() => Boolean(webRebuildStatus.value?.needs_rebuild));
const webRebuildQueued = computed(() => webRebuildStatus.value?.state === 'queued');
const webRebuildNoticeVisible = computed(() => webRebuildNeedsAttention.value || Boolean(webRebuildStatus.value?.last_error));
const webRebuildNoticeClass = computed(() => {
  if (webRebuildQueued.value) return 'border-brand-200 bg-brand-50 text-brand-900 dark:border-brand-500/40 dark:bg-brand-950/50 dark:text-brand-200';
  if (webRebuildNeedsAttention.value || webRebuildStatus.value?.last_error) {
    return 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-500/40 dark:bg-amber-950/50 dark:text-amber-200';
  }
  return 'border-gray-200 bg-gray-50 text-gray-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200';
});
const webRebuildNoticeTitle = computed(() => {
  if (webRebuildQueued.value) return 'Проверка каталога запущена';
  if (webRebuildNeedsAttention.value) return 'Каталог требует синхронизации';
  return 'Каталог актуален';
});
const webRebuildNoticeText = computed(() => {
  if (webRebuildQueued.value) {
    return 'Проверяем, соответствует ли каталог сайта текущей ревизии.';
  }
  if (webRebuildNeedsAttention.value) {
    return 'Каталог сайта не соответствует текущей ревизии. Нужна синхронизация.';
  }
  return 'Каталог сайта соответствует текущей ревизии.';
});
const rebuildButtonLabel = computed(() => {
  if (rebuildLoading.value) return 'Проверка...';
  if (webRebuildNeedsAttention.value) return 'Обновить сайт';
  return 'Проверить сайт';
});
const rebuildButtonTitle = computed(() => {
  if (!isDesktopNavCollapsed.value) return '';
  return rebuildButtonLabel.value;
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
const enforceAuthorizedLocation = () => {
  if (
    isAuthenticated.value
    && !isManagerPathAllowed(auth.value, currentPath.value)
  ) {
    navigate('/manager');
    return true;
  }
  return false;
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
  if (!canManagePlatform.value) return;
  try {
    webRebuildStatus.value = await api.getWebRebuildStatus() as WebRebuildStatus;
  } catch {
    // Non-critical status widget; the rebuild button reports its own errors.
  }
};
const handleLogin = async () => {
  if (recoveryRequired.value) return;
  loginLoading.value = true;
  loginError.value = '';
  try {
    await loginManagerWithPassword(loginUsername.value, loginPassword.value);
    enforceAuthorizedLocation();
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
  if (recoveryRequired.value) return;
  telegramLoginLoading.value = true;
  loginError.value = '';
  try {
    await loginManagerWithTelegram(payload);
    enforceAuthorizedLocation();
    showLoginModal.value = false;
    void fetchLeadsCount();
    void fetchWebRebuildStatus();
  } catch (err) {
    loginError.value = getApiErrorMessage(err) || 'Не удалось войти через Telegram';
  } finally {
    telegramLoginLoading.value = false;
  }
};
const handleLogoutSuccess = () => {
  leadsCount.value = 0;
  webRebuildStatus.value = null;
  rebuildLoading.value = false;
  isMobileNavOpen.value = false;
  loginUsername.value = '';
  loginPassword.value = '';
  loginError.value = '';
  showLoginModal.value = true;
};
const handleLogoutError = (message: string) => {
  setToast(`Не удалось завершить сессию: ${message}`, 'error');
};
const renderTelegramLogin = async () => {
  if (!telegramLoginBotUsername || !showLoginModal.value || recoveryRequired.value) return;
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
  if (!canManagePlatform.value) return;
  const confirmed = await confirmDialog({
    title: 'Проверить сайт?',
    description: 'Проверим, соответствует ли каталог сайта текущей ревизии.',
    confirmText: 'Проверить сайт',
    variant: 'warning',
  });
  if (!confirmed) return;
  rebuildLoading.value = true;
  try {
    const result = await api.rebuildWeb();
    webRebuildStatus.value = result as WebRebuildStatus;
    setToast('Проверка запущена. Результат появится через пару минут.');
    void fetchWebRebuildStatus();
  } catch (err) {
    setToast(`Ошибка при запуске проверки: ${getApiErrorMessage(err)}`, 'error');
  } finally {
    rebuildLoading.value = false;
  }
};
const fetchLeadsCount = async () => {
  if (!hasManagerCapability(auth.value, MANAGER_CAPABILITY.crmManage)) return;
  try {
    const counter = await api.getLeadsCounter();
    leadsCount.value = counter.count;
  } catch {
    // Badge is non-critical — silence errors
  }
};
const checkAuth = async () => {
  try {
    await restoreManagerSession();
    enforceAuthorizedLocation();
    // Fetch the badge count once authenticated
    void fetchLeadsCount();
    void fetchWebRebuildStatus();
  } catch {
    clearManagerSession();
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
    if (isAuthenticated.value && canManagePlatform.value) void fetchWebRebuildStatus();
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
  if (visible && !recoveryRequired.value) {
    void renderTelegramLogin();
  }
});
watch(recoveryRequired, (required) => {
  if (!required) return;
  leadsCount.value = 0;
  webRebuildStatus.value = null;
  rebuildLoading.value = false;
  showLoginModal.value = false;
  loginError.value = '';
  loginPassword.value = '';
  isMobileNavOpen.value = false;
  toast.value = '';
  if (telegramLoginContainer.value) telegramLoginContainer.value.innerHTML = '';
  delete window[telegramCallbackName];
}, { flush: 'sync' });
watch(expandedNavSections, (value) => {
  window.localStorage.setItem(NAV_SECTIONS_STORAGE_KEY, JSON.stringify(value));
}, { deep: true });
watch(currentPath, () => {
  if (enforceAuthorizedLocation()) return;
  expandActiveNavSection();
});
</script>

<template>
  <ManagerLoginModal
    v-if="showLoginModal && !recoveryRequired"
    v-model:username="loginUsername"
    v-model:password="loginPassword"
    :loading="loginLoading"
    :error="loginError"
    :telegram-enabled="Boolean(telegramLoginBotUsername)"
    :telegram-loading="telegramLoginLoading"
    @submit="handleLogin"
  >
    <template #telegram>
      <div ref="telegramLoginContainer" />
    </template>
  </ManagerLoginModal>

  <ManagerSessionRecoveryModal :reload-page="props.reloadPage" />

  <div
    v-if="isAuthenticated && !recoveryRequired"
    data-testid="manager-root"
    class="manager-root min-h-screen flex"
  >
    <KitlaneShell :name="partnerName" :context-key="partnerContextKey" v-model:collapsed="isDesktopNavCollapsed" v-model:mobile-open="isMobileNavOpen" :theme="theme" @toggle-theme="toggleTheme" @home="navigate('/manager')">
      <template #navigation>
        <KitlaneNavigation :items="visibleCoreNavItems" :sections="visibleNavSections" :collapsed="isDesktopNavCollapsed" :leads-count="leadsCount" :expanded="expandedNavSections" :is-nav-item-active="isNavItemActive" :is-nav-section-active="isNavSectionActive" @navigate="navigate" @toggle-section="toggleNavSection" />
      </template>
      <template #footer>
      <div v-if="canManagePlatform" class="p-3 border-t border-[var(--kitlane-sidebar-border)] mt-auto">
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
          <p v-if="webRebuildStatus?.last_error" class="mt-1 text-red-700 dark:text-red-300">
            Последняя проверка завершилась ошибкой.
          </p>
        </div>
        <button
          class="relative w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all"
          :class="[
            rebuildLoading
              ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
              : webRebuildNeedsAttention
                ? 'bg-amber-500 text-white hover:bg-amber-600 shadow-sm hover:shadow-md'
                : 'bg-[var(--kitlane-accent)] text-white hover:bg-[var(--kitlane-accent-hover)]',
            isDesktopNavCollapsed ? 'justify-center' : ''
          ]"
          :disabled="rebuildLoading"
          @click="handleRebuild"
          :title="rebuildButtonTitle" :aria-label="rebuildButtonLabel"
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
      </template>
      <template #account>
        <ManagerAccountMenu
          v-if="auth"
          :auth="auth"
          @navigate="navigate"
          @logged-out="handleLogoutSuccess"
          @error="handleLogoutError"
        />
      </template>

      <ManagerHomeView v-if="authorizedView === 'home'" :key="currentLocation" />
      <ProfileSecurityView v-else-if="authorizedView === 'profile-security'" :key="currentLocation" @password-changed="handleLogoutSuccess" />
      <AnalyticsConnectionsView v-else-if="authorizedView === 'analytics-connections'" :key="currentLocation" />
      <LeadsView v-else-if="authorizedView === 'leads'" :key="currentLocation" />
      <OrdersKanbanView v-else-if="authorizedView === 'orders'" :key="currentLocation" />
      <CalendarDashboard v-else-if="authorizedView === 'calendar'" :key="currentLocation" />
      <EquipmentRegistryView v-else-if="authorizedView === 'equipment'" :key="currentLocation" />
      <MediaLibraryView v-else-if="authorizedView === 'media-library'" :key="currentLocation" />
      <CatalogQualityView v-else-if="authorizedView === 'catalog-quality'" :key="currentLocation" />
      <CatalogDecisionWorkspaceView v-else-if="authorizedView === 'catalog-decision' && canManagePlatform" :key="currentLocation" />
      <ProductCollectionsView v-else-if="authorizedView === 'product-collections'" :key="currentLocation" />
      <CustomerProfileView v-else-if="authorizedView === 'customer-profile'" :key="currentLocation" />
      <CustomersView v-else-if="authorizedView === 'customers'" :key="currentLocation" />
      <InstallersView v-else-if="authorizedView === 'installers'" :key="currentLocation" />
      <SettingsBackupView v-else-if="authorizedView === 'settings-backup' && canManageInfrastructure" :key="currentLocation" />
      <DocumentsSettingsView v-else-if="authorizedView === 'settings-documents' && canManageDocuments" :key="currentLocation" />
      <SettingsView v-else-if="authorizedView === 'settings' && canManageInfrastructure" :key="currentLocation" />
      <InstallationRatesView v-else-if="authorizedView === 'installation-rates'" :key="currentLocation" />
      <InstallationDiscountsView v-else-if="authorizedView === 'installation-discounts'" :key="currentLocation" />
      <TariffsView v-else-if="authorizedView === 'tariffs'" :key="currentLocation" />
      <ServiceEstimatesView v-else-if="authorizedView === 'service-estimates'" :key="currentLocation" />
      <OutgoingEmailsView v-else-if="authorizedView === 'outgoing-emails'" :key="currentLocation" />
      <BankReceiptsView v-else-if="authorizedView === 'payments'" :key="currentLocation" />
      <TagsView v-else-if="authorizedView === 'tags'" :key="currentLocation" />
      <BrandsView v-else-if="authorizedView === 'brands'" :key="currentLocation" />
      <FeatureSeriesMigrationView v-else-if="authorizedView === 'feature-series-migration'" :key="currentLocation" />
      <FeaturesView v-else-if="authorizedView === 'features'" :key="currentLocation" />
      <SupplyRequestsView v-else-if="authorizedView === 'supply'" :key="currentLocation" />
      <SupplierFeedsView v-else-if="authorizedView === 'suppliers'" :key="currentLocation" />
      <SupplierMappingView v-else-if="authorizedView === 'supplier-mapping'" :key="currentLocation" />
      <ProductWorkspaceView v-else-if="authorizedView === 'product-workspace' && canManagePlatform" :key="currentLocation" />
      <ProductsView v-else-if="canManagePlatform" :key="currentLocation" />
      <TenantCatalogView v-else :key="currentLocation" />
    </KitlaneShell>

    <Transition name="fade">
      <div
        v-if="toast"
        class="fixed top-6 right-6 z-[100] rounded-xl px-6 py-3 font-medium text-white shadow-2xl"
        :class="toastType === 'success' ? 'bg-emerald-600' : 'bg-red-600'"
      >
        {{ toast }}
      </div>
    </Transition>
    <UiFeedbackHost />
  </div>
</template>
