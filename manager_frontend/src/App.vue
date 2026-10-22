<script setup lang="ts">
import InvitationAcceptView from './views/InvitationAcceptView.vue';
import { ManagerContextError } from './services/manager-storefront-selection';
import ManagerStorefrontSwitcherHost from './components/manager/ManagerStorefrontSwitcherHost.vue';
import { managerProfileApi, applyOwnProfile } from './services/manager-profile';
import { inboxChangedEvent } from './services/lead-inbox';
import { managerLeadsCounterState } from './services/manager-dashboard-state';
import { computed, defineAsyncComponent, onMounted, onBeforeUnmount, ref, watch } from 'vue';
import { Zap, Loader2, AlertTriangle } from 'lucide-vue-next';
import { api } from './api';
import { getApiErrorMessage } from './utils/api-errors';
import { connectorLoginContinuation, resumeConnectorLogin } from './services/connector-login-continuation';
import UiFeedbackHost from './components/common/UiFeedbackHost.vue';
import ManagerAccountMenu from './components/manager/ManagerAccountMenu.vue';
import ManagerLoginModal from './components/manager/ManagerLoginModal.vue';
import TelegramLoginChallenge from './components/manager/TelegramLoginChallenge.vue';
import ManagerSessionRecoveryModal from './components/manager/ManagerSessionRecoveryModal.vue';
import KitlaneShell from './components/kitlane/KitlaneShell.vue';
import KitlaneNavigation from './components/kitlane/KitlaneNavigation.vue';
import { useKitlaneIdentity } from './composables/useKitlaneIdentity';
import { confirmDialog } from './services/ui-feedback';
import { navigateManager, replaceManagerLocation, startManagerNavigation } from './services/manager-navigation-history';
import { normalizeOrderLocation, readOrderPage } from './services/order-navigation';
import {
  clearManagerSession,
  loginManagerWithPassword,
  bootstrapManagerSession,
  managerSession,
  restoreManagerSession,
} from './services/manager-session';
import { useDemoReadOnly } from './services/manager-demo';
import {
  coreNavItems,
  installerWorkNavItem,
  installerMoneyNavItem,
  installerPayNavItem,
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
  canReadOwnInstallerWorks,
} from './manager-capabilities';
const WorkerPayView = defineAsyncComponent(() => import('./views/WorkerPayView.vue'));
const WorkerMoneyView = defineAsyncComponent(() => import('./views/WorkerMoneyView.vue'));
const InstallerWorksView = defineAsyncComponent(() => import('./views/InstallerWorksView.vue'));
const ProductsView = defineAsyncComponent(() => import('./views/ProductsView.vue'));
const TenantCatalogView = defineAsyncComponent(() => import('./views/TenantCatalogView.vue'));
const CatalogDecisionWorkspaceView = defineAsyncComponent(() => import('./views/CatalogDecisionWorkspaceView.vue'));
const ProductCollectionsView = defineAsyncComponent(() => import('./views/ProductCollectionsView.vue'));
const ProductWorkspaceView = defineAsyncComponent(() => import('./views/ProductWorkspaceView.vue'));
const MediaLibraryView = defineAsyncComponent(() => import('./views/MediaLibraryView.vue'));
const CustomersView = defineAsyncComponent(() => import('./views/CustomersView.vue'));
const CustomerProfileView = defineAsyncComponent(() => import('./views/CustomerProfileView.vue'));
const OrdersKanbanView = defineAsyncComponent(() => import('./views/OrdersKanbanView.vue'));
const OrderDetailView = defineAsyncComponent(() => import('./views/OrderDetailView.vue'));
const LeadsView = defineAsyncComponent(() => import('./views/LeadsView.vue'));
const PersonalTasksView = defineAsyncComponent(() => import('./views/PersonalTasksView.vue'));
const CallRecordingsView = defineAsyncComponent(() => import('./views/CallRecordingsView.vue'));
const CalendarDashboard = defineAsyncComponent(() => import('./views/CalendarDashboard.vue'));
const ManagerHomeView = defineAsyncComponent(() => import('./views/ManagerHome.vue'));
const InstallersView = defineAsyncComponent(() => import('./views/InstallersView.vue'));
const SettingsView = defineAsyncComponent(() => import('./views/SettingsView.vue'));
const PlatformCompaniesView = defineAsyncComponent(() => import('./views/PlatformCompaniesView.vue'));
const CompanySitesView = defineAsyncComponent(() => import('./views/CompanySitesView.vue'));
const PlatformAccessView = defineAsyncComponent(() => import('./views/PlatformAccessView.vue'));
const PlatformSettingsView = defineAsyncComponent(() => import('./views/PlatformSettingsView.vue'));
const SettingsBackupView = defineAsyncComponent(() => import('./views/SettingsBackupView.vue'));
const DocumentsSettingsView = defineAsyncComponent(() => import('./views/DocumentsSettingsView.vue'));
const TariffsView = defineAsyncComponent(() => import('./views/TariffsView.vue'));
const InstallationRatesView = defineAsyncComponent(() => import('./views/InstallationRatesView.vue'));
const InstallationDiscountsView = defineAsyncComponent(() => import('./views/InstallationDiscountsView.vue'));
const ServiceEstimatesView = defineAsyncComponent(() => import('./views/ServiceEstimatesView.vue'));
const BankReceiptsView = defineAsyncComponent(() => import('./views/BankReceiptsView.vue'));
const MailView = defineAsyncComponent(() => import('./views/MailView.vue'));
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
const isInvitationRoute = window.location.pathname.replace(/\/$/, '') === '/manager/invite';
// Keep the secret only in this page's memory, before rendering or making requests.
const invitationToken = isInvitationRoute ? new URLSearchParams(window.location.hash.slice(1)).get('token') || '' : '';
if (isInvitationRoute && window.location.hash) window.history.replaceState(window.history.state, '', window.location.pathname + window.location.search);
const contextError = ref('');
const props = defineProps<{ reloadPage?: () => void }>();
const { isAuthenticated, auth, recoveryRequired } = managerSession;
const demoReadOnly = useDemoReadOnly();
const { name: partnerName, logoUrl: partnerLogoUrl, compactLogoUrl: partnerCompactLogoUrl, contextKey: partnerContextKey } = useKitlaneIdentity();
const showLoginModal = ref(false);
const connectorReturn = connectorLoginContinuation(window.location.search, window.location.origin);
const continueConnection = async () => {
  if (!connectorReturn || !auth.value) return false;
  if (!auth.value.staff_user_id || auth.value.auth_source === 'legacy') {
    loginError.value = 'Для подключения ChatGPT нужен ваш личный логин Kitlane, выданный владельцем компании.';
    showLoginModal.value = true;
    return true;
  }
  let personal;
  try { personal = await managerProfileApi.get(); applyOwnProfile(personal); }
  catch (error) { loginError.value = getApiErrorMessage(error); showLoginModal.value = true; return true; }
  if (personal.must_change_password) {
    showLoginModal.value = false;
    navigate('/manager/profile');
    return true;
  }
  return resumeConnectorLogin(connectorReturn, { ...auth.value, must_change_password: personal.must_change_password, can_change_password: personal.can_change_password });
};
const loginUsername = ref('');
const loginPassword = ref('');
const loginLoading = ref(false);
const loginError = ref('');
const telegramLoginLoading = ref(false);
const rebuildLoading = ref(false);
const webRebuildStatus = ref<WebRebuildStatus | null>(null);
const isMobileNavOpen = ref(false);
const isDesktopNavCollapsed = ref(false);
const theme = ref<'light' | 'dark'>('light');
const leadsCount = computed(() => managerLeadsCounterState.data.value?.count || 0);
const toast = ref('');
const toastType = ref<'success' | 'error'>('success');
const currentLocation = ref(normalizeOrderLocation());
const orderPage = computed(() => readOrderPage(currentLocation.value));
const viewRevision = ref(0);
const THEME_STORAGE_KEY = 'manager_theme';
const NAV_SECTIONS_STORAGE_KEY = 'manager_nav_sections_v1';
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
const expandedNavSections = ref<Record<NavSectionId, boolean>>({ ...defaultExpandedNavSections });
const normalizePath = (path: string) => {
  if (path.length > 1 && path.endsWith('/')) {
    return path.slice(0, -1);
  }
  return path;
};
const currentPath = computed(() => normalizePath(currentLocation.value.split('?')[0] || '/manager'));
const canManagePlatform = computed(() => hasManagerCapability(auth.value, MANAGER_CAPABILITY.platformManage));
const canEditCatalog = computed(() => hasManagerCapability(auth.value, MANAGER_CAPABILITY.catalogMasterEdit));
const canManageInfrastructure = computed(() => hasManagerCapability(auth.value, MANAGER_CAPABILITY.infrastructureManage));
const canManageDocuments = computed(() => hasManagerCapability(auth.value, MANAGER_CAPABILITY.documentsManage));
const canManageSettings = computed(() => hasManagerCapability(auth.value, MANAGER_CAPABILITY.settingsManage));
const canManageCallRecordings = computed(() => hasManagerCapability(auth.value, MANAGER_CAPABILITY.callRecordingsManage));
const isInstallerWorkspace = computed(() => hasManagerCapability(auth.value, MANAGER_CAPABILITY.installerWorksRead));
const visibleCoreNavItems = computed(() => [
  ...coreNavItems.filter(item => (!isInstallerWorkspace.value || item.path !== '/manager')
    && (!item.requiredCapability || hasManagerCapability(auth.value, item.requiredCapability))),
  ...(canReadOwnInstallerWorks(auth.value) ? [installerWorkNavItem, installerMoneyNavItem, installerPayNavItem] : []),
]);
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
const defaultView = computed(() => isInstallerWorkspace.value ? 'installer-works' : hasManagerCapability(auth.value, MANAGER_CAPABILITY.crmManage)
  ? 'home' : canEditCatalog.value ? 'products' : 'profile-security');
const currentView = computed(() => {
  const path = currentPath.value;
  if (path === '/manager' || path === '/manager/') return defaultView.value;
  if (path === '/manager/my-pay') return 'installer-pay';
  if (path.startsWith('/manager/worker-pay')) return 'worker-pay';
  if (path === '/manager/my-money') return 'installer-money';
  if (path.startsWith('/manager/worker-money')) return 'worker-money';
  if (path === '/manager/my-work' || path.startsWith('/manager/my-work/')) return 'installer-works';
  if (path === '/manager/profile') return 'profile-security';
  if (path.startsWith('/manager/integrations')) return 'analytics-connections';
  if (path.startsWith('/manager/tasks')) return 'personal-tasks';
  if (path.startsWith('/manager/settings/calls') || path.startsWith('/manager/calls')) return 'call-recordings';
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
  if (path.startsWith('/manager/platform/companies')) return 'platform-companies';
  if (path.startsWith('/manager/company/sites')) return 'company-sites';
  if (path.startsWith('/manager/platform/access')) return 'platform-access';
  if (path.startsWith('/manager/settings/backup')) return 'settings-backup';
  if (path.startsWith('/manager/settings/documents')) return 'settings-documents';
  if (path.startsWith('/manager/settings/platform')) return 'settings-platform';
  if (path.startsWith('/manager/settings')) return 'settings';
  if (path.startsWith('/manager/installation-rates')) return 'installation-rates';
  if (path.startsWith('/manager/installation-discounts')) return 'installation-discounts';
  if (path.startsWith('/manager/tariffs')) return 'tariffs';
  if (path.startsWith('/manager/service-estimates')) return 'service-estimates';
  if (path.startsWith('/manager/mail')) return 'mail';
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
  isManagerPathAllowed(auth.value, currentPath.value) ? currentView.value : defaultView.value
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
const stopNavigation = startManagerNavigation((location) => {
  currentLocation.value = location;
  viewRevision.value += 1;
}, normalizeOrderLocation);
const navigate = async (path: string) => {
  if (window.location.pathname !== path && !await navigateManager(path)) return;
  isMobileNavOpen.value = false;
};
const enforceAuthorizedLocation = () => {
  if (isAuthenticated.value && isInstallerWorkspace.value && currentPath.value === '/manager') {
    navigate('/manager/my-work');
    return true;
  }
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
  if (recoveryRequired.value || loginLoading.value || telegramLoginLoading.value) return;
  loginLoading.value = true;
  loginError.value = '';
  try {
    await loginManagerWithPassword(loginUsername.value, loginPassword.value);
    loginPassword.value = '';
    if (await continueConnection()) return;
    enforceAuthorizedLocation();
    showLoginModal.value = false;
    loginPassword.value = '';
    void fetchLeadsCount();
    void fetchWebRebuildStatus();
  } catch (error) {
    if (error instanceof ManagerContextError) { contextError.value = error.message; showLoginModal.value = false; }
    else loginError.value = 'Неверный логин или пароль';
  } finally {
    loginLoading.value = false;
  }
};
const handleTelegramLogin = async () => {
  if (recoveryRequired.value) return;
  telegramLoginLoading.value = true;
  loginError.value = '';
  try {
    await bootstrapManagerSession();
    if (await continueConnection()) return;
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
let appMounted = false;
const canRefreshCounter = () => appMounted && isAuthenticated.value && document.visibilityState !== 'hidden';
const fetchLeadsCount = (event?: Event) => managerLeadsCounterState.refresh(event ? 0 : 5_000, event ? canRefreshCounter : undefined);
const checkAuth = async () => {
  try {
    await restoreManagerSession();
    if (await continueConnection()) return;
    enforceAuthorizedLocation();
    // Fetch the badge count once authenticated
    void fetchLeadsCount();
    void fetchWebRebuildStatus();
  } catch (error) {
    if (error instanceof ManagerContextError) { contextError.value = error.message; showLoginModal.value = false; }
    else { clearManagerSession(); showLoginModal.value = true; }
  }
};
onMounted(() => {
  appMounted = true;
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
  window.addEventListener(inboxChangedEvent, fetchLeadsCount);
  webRebuildStatusInterval = window.setInterval(() => {
    if (isAuthenticated.value && canManagePlatform.value) void fetchWebRebuildStatus();
  }, 60_000);
  if (!isInvitationRoute) checkAuth();
});
onBeforeUnmount(() => {
  appMounted = false;
  stopNavigation();
  window.removeEventListener(inboxChangedEvent, fetchLeadsCount);
  if (webRebuildStatusInterval) {
    window.clearInterval(webRebuildStatusInterval);
    webRebuildStatusInterval = null;
  }
});
watch(recoveryRequired, (required) => {
  if (!required) return;
  webRebuildStatus.value = null;
  rebuildLoading.value = false;
  showLoginModal.value = false;
  loginError.value = '';
  loginPassword.value = '';
  isMobileNavOpen.value = false;
  toast.value = '';
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
  <InvitationAcceptView v-if="isInvitationRoute" :token="invitationToken" />
  <main v-else-if="contextError" class="min-h-screen bg-slate-50 p-6"><section class="mx-auto max-w-xl space-y-5 rounded-xl border bg-white p-6"><h1 class="text-xl font-bold">Компания или сайт недоступны</h1><p role="alert">{{ contextError }}</p><p class="text-sm text-gray-500">Проверьте ссылку или выберите доступную компанию.</p><ManagerStorefrontSwitcherHost :collapsed="false" /><a class="inline-block text-brand-700 underline" href="/manager/">Открыть доступную компанию</a></section></main>
  <ManagerLoginModal
    v-if="showLoginModal && !recoveryRequired && !isInvitationRoute && !contextError"
    v-model:username="loginUsername"
    v-model:password="loginPassword"
    :loading="loginLoading || telegramLoginLoading"
    :error="loginError"
    :telegram-enabled="true"
    :telegram-loading="telegramLoginLoading"
    :connector-login="Boolean(connectorReturn)"
    @submit="handleLogin"
  >
    <template #telegram>
      <TelegramLoginChallenge :disabled="loginLoading" @authenticated="handleTelegramLogin" @busy="telegramLoginLoading = $event" />
    </template>
  </ManagerLoginModal>

  <ManagerSessionRecoveryModal :reload-page="props.reloadPage" />

  <div
    v-if="isAuthenticated && !recoveryRequired && !isInvitationRoute && !contextError"
    data-testid="manager-root"
    class="manager-root min-h-screen flex"
  >
    <KitlaneShell :name="partnerName" :logo-url="partnerLogoUrl" :compact-logo-url="partnerCompactLogoUrl" :context-key="partnerContextKey" v-model:collapsed="isDesktopNavCollapsed" v-model:mobile-open="isMobileNavOpen" :theme="theme" @toggle-theme="toggleTheme" @home="navigate('/manager')">
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

      <div v-if="demoReadOnly" class="mx-4 mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100" role="status">
        Демонстрационная компания: рабочие данные доступны только для просмотра.
      </div>

      <InstallerWorksView v-if="authorizedView === 'installer-works'" :key="currentLocation" />
      <WorkerPayView v-else-if="authorizedView === 'installer-pay'" :key="currentLocation" />
      <WorkerPayView v-else-if="authorizedView === 'worker-pay'" :key="currentLocation" management />
      <WorkerMoneyView v-else-if="authorizedView === 'installer-money'" :key="currentLocation" />
      <WorkerMoneyView v-else-if="authorizedView === 'worker-money'" :key="currentLocation" management />
      <ManagerHomeView v-else-if="authorizedView === 'home'" :key="currentLocation" />
      <ProfileSecurityView v-else-if="authorizedView === 'profile-security'" :key="currentLocation" @password-changed="handleLogoutSuccess" />
      <AnalyticsConnectionsView v-else-if="authorizedView === 'analytics-connections'" :key="currentLocation" />
      <PersonalTasksView v-else-if="authorizedView === 'personal-tasks'" :key="currentLocation" />
      <CallRecordingsView v-else-if="authorizedView === 'call-recordings'" :key="currentLocation" />
      <LeadsView v-else-if="authorizedView === 'leads'" :key="currentLocation" />
      <OrderDetailView v-else-if="authorizedView === 'orders' && orderPage" :key="currentLocation" :order-id="orderPage.orderId" :return-to="orderPage.returnTo" />
      <OrdersKanbanView v-else-if="authorizedView === 'orders'" :key="currentLocation" />
      <CalendarDashboard v-else-if="authorizedView === 'calendar'" :key="currentLocation" />
      <EquipmentRegistryView v-else-if="authorizedView === 'equipment'" :key="currentLocation" />
      <MediaLibraryView v-else-if="authorizedView === 'media-library'" :key="currentLocation" />
      <CatalogQualityView v-else-if="authorizedView === 'catalog-quality'" :key="currentLocation" />
      <CatalogDecisionWorkspaceView v-else-if="authorizedView === 'catalog-decision'" :key="currentLocation" />
      <ProductCollectionsView v-else-if="authorizedView === 'product-collections'" :key="`${currentLocation}:${viewRevision}`" @location-change="replaceManagerLocation" />
      <CustomerProfileView v-else-if="authorizedView === 'customer-profile'" :key="currentLocation" />
      <CustomersView v-else-if="authorizedView === 'customers'" :key="currentLocation" />
      <InstallersView v-else-if="authorizedView === 'installers'" :key="currentLocation" />
      <SettingsBackupView v-else-if="authorizedView === 'settings-backup' && canManageInfrastructure" :key="currentLocation" />
      <DocumentsSettingsView v-else-if="authorizedView === 'settings-documents' && canManageDocuments" :key="currentLocation" />
      <CompanySitesView v-else-if="authorizedView === 'company-sites'" :key="currentLocation" />
      <PlatformCompaniesView v-else-if="authorizedView === 'platform-companies'" :key="currentLocation" />
      <PlatformAccessView v-else-if="authorizedView === 'platform-access' && canManageInfrastructure" :key="currentLocation" />
      <PlatformSettingsView v-else-if="authorizedView === 'settings-platform' && canManageInfrastructure" :key="currentLocation" />
      <SettingsView v-else-if="authorizedView === 'settings' && canManageSettings" :key="currentLocation" :can-manage-call-recordings="canManageCallRecordings" />
      <InstallationRatesView v-else-if="authorizedView === 'installation-rates'" :key="currentLocation" />
      <InstallationDiscountsView v-else-if="authorizedView === 'installation-discounts'" :key="currentLocation" />
      <TariffsView v-else-if="authorizedView === 'tariffs'" :key="currentLocation" />
      <ServiceEstimatesView v-else-if="authorizedView === 'service-estimates'" :key="currentLocation" />
      <MailView v-else-if="authorizedView === 'mail'" :key="currentLocation" />
      <BankReceiptsView v-else-if="authorizedView === 'payments'" :key="currentLocation" />
      <TagsView v-else-if="authorizedView === 'tags'" :key="currentLocation" />
      <BrandsView v-else-if="authorizedView === 'brands'" :key="currentLocation" />
      <FeatureSeriesMigrationView v-else-if="authorizedView === 'feature-series-migration'" :key="currentLocation" />
      <FeaturesView v-else-if="authorizedView === 'features'" :key="currentLocation" />
      <SupplyRequestsView v-else-if="authorizedView === 'supply'" :key="currentLocation" />
      <SupplierFeedsView v-else-if="authorizedView === 'suppliers'" :key="currentLocation" :initial-tab="currentPath.startsWith('/manager/suppliers/prices') ? 'prices' : 'profile'" />
      <SupplierMappingView v-else-if="authorizedView === 'supplier-mapping'" :key="currentLocation" />
      <ProductWorkspaceView v-else-if="authorizedView === 'product-workspace' && canEditCatalog" :key="currentLocation" />
      <ProductsView v-else-if="canEditCatalog" :key="currentLocation" />
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
