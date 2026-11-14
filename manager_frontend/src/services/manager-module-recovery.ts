import type { InjectionKey } from 'vue';

export const managerModuleReloadKey: InjectionKey<() => void> = Symbol('manager-module-reload');
export const MODULE_DIAGNOSTICS_KEY = 'manager_module_failures_v1';
export const MODULE_DIAGNOSTICS_LIMIT = 20;
// Build-time identifiers only: never derive these from a location, exception or API data.
const modules = [
  'WorkerPayView',
  'WorkerMoneyView',
  'InstallerWorksView',
  'ProductsView',
  'TenantCatalogView',
  'CatalogDecisionWorkspaceView',
  'ProductCollectionsView',
  'ProductWorkspaceView',
  'MediaLibraryView',
  'CustomersView',
  'CustomerProfileView',
  'OrdersKanbanView',
  'OrderDetailView',
  'LeadsView',
  'PersonalTasksView',
  'CallRecordingsView',
  'CalendarDashboard',
  'ManagerHomeView',
  'InstallersView',
  'SettingsView',
  'PlatformCompaniesView',
  'CompanySitesView',
  'PlatformAccessView',
  'PlatformSettingsView',
  'SettingsBackupView',
  'DocumentsSettingsView',
  'TariffsView',
  'InstallationRatesView',
  'InstallationDiscountsView',
  'ServiceEstimatesView',
  'BankReceiptsView',
  'MailView',
  'TagsView',
  'BrandsView',
  'FeaturesView',
  'FeatureSeriesMigrationView',
  'SupplierFeedsView',
  'SupplierMappingView',
  'CatalogQualityView',
  'SupplyRequestsView',
  'EquipmentRegistryView',
  'ProfileSecurityView',
  'AnalyticsConnectionsView',
  'CustomerContractsPanel',
  'CustomerDocumentsPanel',
  'CustomerEquipmentPanel',
  'CustomerReconciliationPanel',
  'EnvelopePrintDialog',
  'OrderTemplateEditor',
  'OrderWorkspacePanel',
  'unknown',
] as const;
export type ManagerModule = typeof modules[number];
export type ModuleCategory = 'route' | 'panel';
const codes = ['import-failed', 'timeout', 'preload-failed', 'reload-blocked', 'reload-requested', 'reload-failed'] as const;
type FailureCode = typeof codes[number];

export const recordModuleFailure = (module: ManagerModule, category: ModuleCategory, code: FailureCode) => {
  try {
    // Filter existing storage as well: keep only known values and reconstruct exact fields.
    let stored: unknown;
    try { stored = JSON.parse(window.sessionStorage.getItem(MODULE_DIAGNOSTICS_KEY) || '[]'); }
    catch { stored = []; }
    const entries = (Array.isArray(stored) ? stored : []).filter(item => item &&
      modules.includes(item.module) && ['route', 'panel'].includes(item.category) && codes.includes(item.code) &&
      typeof item.time === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(item.time))
      .map(({ module, category, code, time }) => ({ module, category, code, time }));
    entries.push({ module: modules.includes(module) ? module : 'unknown', category: category === 'route' ? 'route' : 'panel', code, time: new Date().toISOString() });
    window.sessionStorage.setItem(MODULE_DIAGNOSTICS_KEY, JSON.stringify(entries.slice(-MODULE_DIAGNOSTICS_LIMIT)));
  } catch {
    // Recovery must work with unavailable, full or malformed browser storage.
  }
};
