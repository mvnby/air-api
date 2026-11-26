import type { Component } from 'vue';
import {
  Award, BadgePercent, Boxes, Building2, CalendarDays, ChartNoAxesCombined, ClipboardList, Database,
  FileSpreadsheet, FileText, FolderOpen, GalleryVerticalEnd, Image, Inbox, Landmark, Link2, ListTodo,
  Mail, Package, PanelsTopLeft, ReceiptText, SearchCheck, Settings, ShieldCheck, SlidersHorizontal,
  Sparkles, Tags, Truck, UsersRound, Wallet, Wrench,
} from 'lucide-vue-next';
import { MANAGER_CAPABILITY as cap, canReadOwnInstallerWorks, hasManagerCapability, type ManagerCapability } from './manager-capabilities';
import type { ManagerAuthStatusResponse } from './client';

export type NavItem = {
  path: string;
  label: string;
  icon: Component;
  shortLabel?: string;
  aliases?: string;
  requiredCapability?: ManagerCapability;
};
export type NavSection = { id: string; label: string; items: NavItem[] };
type NavigationIdentity = Pick<ManagerAuthStatusResponse, 'capabilities'> & Partial<Pick<ManagerAuthStatusResponse, 'tenant_membership_id' | 'is_system_tenant'>>;

export const coreNavItems: NavItem[] = [
  { path: '/manager/leads', label: 'Входящие', icon: Inbox, aliases: 'заявки лиды обращения', requiredCapability: cap.crmManage },
  { path: '/manager/orders', label: 'Заказы', icon: FolderOpen, aliases: 'сделки канбан', requiredCapability: cap.crmManage },
  { path: '/manager/catalog-decision', label: 'Подбор оборудования', shortLabel: 'Подбор', icon: SlidersHorizontal, aliases: 'модели оборудование сравнение', requiredCapability: cap.crmManage },
  { path: '/manager/customers', label: 'Клиенты', icon: UsersRound, aliases: 'контрагент контрагенты заказчики', requiredCapability: cap.crmManage },
];
const personalWork: NavItem[] = [
  { path: '/manager/tasks', label: 'Поручения', icon: ListTodo, aliases: 'мои задачи напоминания дела', requiredCapability: cap.crmManage },
  { path: '/manager/calendar', label: 'Календарь', icon: CalendarDays, requiredCapability: cap.crmManage },
];
const fieldWork: NavItem[] = [
  { path: '/manager/my-work', label: 'Мои работы', shortLabel: 'Работы', icon: ClipboardList },
  { path: '/manager/my-money', label: 'Мои деньги', shortLabel: 'Деньги', icon: Wallet },
  { path: '/manager/my-pay', label: 'Моё вознаграждение', shortLabel: 'Вознаграждение', icon: ReceiptText },
];
export const selectionItems: NavItem[] = [
  { path: '/manager/personal-offers', label: 'Предложения клиентам', icon: FileText, aliases: 'персональные предложения коммерческое предложение КП ссылка клиенту', requiredCapability: cap.crmManage },
  { path: '/manager/product-collections', label: 'Подборки сайта', icon: GalleryVerticalEnd, aliases: 'подборки витрины', requiredCapability: cap.storefrontCollectionsManage },
];
export const navSections: NavSection[] = [
  { id: 'sales', label: 'Продажи и связь', items: [
    { path: '/manager', label: 'Обзор бизнеса', icon: ChartNoAxesCombined, aliases: 'главная аналитика эффективность', requiredCapability: cap.crmManage },
    { path: '/manager/mail', label: 'Рабочая почта', icon: Mail, aliases: 'письма черновики', requiredCapability: cap.crmManage },
    { path: '/manager/tenders', label: 'Мониторинг тендеров', icon: SearchCheck, aliases: 'тендеры закупки публикации', requiredCapability: cap.tenderMarket },
  ] },
  { id: 'catalog', label: 'Каталог и витрина', items: [
    { path: '/manager/products', label: 'Кондиционеры', icon: Package, aliases: 'каталог моделей', requiredCapability: cap.catalogMasterRead },
    { path: '/manager/brands', label: 'Бренды', icon: Award, requiredCapability: cap.catalogMasterEdit },
    { path: '/manager/features', label: 'Особенности моделей', icon: Sparkles, aliases: 'фичи', requiredCapability: cap.catalogMasterEdit },
    { path: '/manager/tags', label: 'Теги', icon: Tags, requiredCapability: cap.catalogMasterEdit },
    { path: '/manager/media', label: 'Медиатека', icon: Image, requiredCapability: cap.platformManage },
    { path: '/manager/catalog-quality', label: 'Качество каталога', icon: ShieldCheck, requiredCapability: cap.platformManage },
    { path: '/manager/suppliers', label: 'Поставщики', icon: Building2, requiredCapability: cap.platformManage },
    { path: '/manager/suppliers/prices', label: 'Прайсы поставщиков', icon: FileSpreadsheet, requiredCapability: cap.platformManage },
    { path: '/manager/supplier-mapping', label: 'Сопоставление прайсов', icon: Link2, aliases: 'маппинг прайсов', requiredCapability: cap.platformManage },
    { path: '/manager/supply', label: 'Поставки', icon: Truck, requiredCapability: cap.platformManage },
  ] },
  { id: 'services', label: 'Сервис и монтаж', items: [
    { path: '/manager/equipment', label: 'Реестр оборудования', icon: Boxes, aliases: 'оборудование клиентов', requiredCapability: cap.crmManage },
    { path: '/manager/service-estimates', label: 'Сметы услуг', icon: ClipboardList, requiredCapability: cap.servicesManage },
    { path: '/manager/tariffs', label: 'Тарифы смет', icon: ReceiptText, requiredCapability: cap.servicesManage },
    { path: '/manager/installation-rates', label: 'Расценки на монтаж', icon: Wrench, aliases: 'публичный монтаж', requiredCapability: cap.servicesManage },
    { path: '/manager/installation-discounts', label: 'Скидки на монтаж', icon: BadgePercent, requiredCapability: cap.platformManage },
  ] },
  { id: 'finance', label: 'Финансы компании', items: [
    { path: '/manager/payments', label: 'Платежи', icon: Landmark, requiredCapability: cap.platformManage },
    { path: '/manager/worker-money', label: 'Деньги у сотрудников', icon: Wallet, requiredCapability: cap.crmManage },
    { path: '/manager/worker-pay', label: 'Вознаграждения', icon: ReceiptText, requiredCapability: cap.workerPayRead },
  ] },
  { id: 'company', label: 'Компания и настройки', items: [
    { path: '/manager/settings', label: 'Настройки', icon: Settings, aliases: 'модули тендеры настройки поиска компания сайт', requiredCapability: cap.settingsManage },
    { path: '/manager/staff', label: 'Сотрудники', icon: UsersRound, requiredCapability: cap.staffManage },
    { path: '/manager/company/sites', label: 'Сайты компании', icon: PanelsTopLeft, requiredCapability: cap.staffManage },
    { path: '/manager/settings/documents', label: 'Документы CRM', icon: FileText, requiredCapability: cap.documentsManage },
    { path: '/manager/integrations', label: 'Интеграции', icon: Link2, requiredCapability: cap.analyticsManage },
  ] },
  { id: 'platform', label: 'Платформа', items: [
    { path: '/manager/platform/companies', label: 'Компании платформы', icon: Building2, requiredCapability: cap.platformCompaniesManage },
    { path: '/manager/platform/access', label: 'Доступ к каталогу', icon: ShieldCheck, requiredCapability: cap.infrastructureManage },
    { path: '/manager/settings/platform', label: 'Настройки платформы', icon: Settings, requiredCapability: cap.infrastructureManage },
    { path: '/manager/settings/backup', label: 'Резервные копии', icon: Database, aliases: 'DR бэкапы восстановление', requiredCapability: cap.infrastructureManage },
  ] },
];

export function workspaceNavigation(auth: NavigationIdentity) {
  const allowed = (item: NavItem) => !item.requiredCapability || hasManagerCapability(auth, item.requiredCapability);
  const installer = hasManagerCapability(auth, cap.installerWorksRead);
  const primary = installer ? fieldWork : coreNavItems.filter(allowed);
  const personal = installer ? [] : [...personalWork.filter(allowed), ...(canReadOwnInstallerWorks(auth) ? fieldWork : [])];
  const groups = [
    { id: 'daily', label: 'Ежедневная работа', items: primary },
    { id: 'personal', label: 'Моя работа', items: personal },
    { id: 'selection', label: 'Подбор оборудования', items: selectionItems },
    ...navSections,
  ].map(group => ({ ...group, items: group.items.filter(allowed) })).filter(group => group.items.length);
  return { primary, personal, groups };
}

const normalize = (value: string) => value.toLocaleLowerCase('ru').replace(/ё/g, 'е');
export function searchNavSections(groups: NavSection[], query: string) {
  const words = normalize(query).trim().split(/\s+/);
  return groups.map(group => ({ ...group, items: group.items.filter(item => {
    const text = normalize([group.label, item.label, item.aliases || ''].join(' '));
    return words.every(word => text.includes(word));
  }) })).filter(group => group.items.length);
}

export function activeNavPath(path: string, groups: NavSection[]) {
  const items = groups.flatMap(group => group.items);
  return items.filter(item => path === item.path || (item.path !== '/manager' && path.startsWith(item.path + '/')))
    .sort((a, b) => b.path.length - a.path.length)[0]?.path;
}
