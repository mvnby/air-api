import type { Component } from 'vue';
import { MANAGER_CAPABILITY, type ManagerCapability } from './manager-capabilities';
import {
  Award,
  Boxes,
  Calendar,
  Calculator,
  Database,
  FileSpreadsheet,
  Home,
  Image as ImageIcon,
  Link2,
  Mail,
  Package,
  GalleryVerticalEnd,
  ReceiptText,
  Settings,
  ShieldCheck,
  Sparkles,
  ShoppingCart,
  Tags,
  Truck,
  UserPlus,
  Users,
  Wallet,
} from 'lucide-vue-next';

export type NavItem = {
  path: string;
  label: string;
  icon: Component;
  match?: 'exact' | 'prefix';
  requiredCapability?: ManagerCapability;
};

export type NavSectionId = 'catalog' | 'services' | 'team' | 'finance' | 'mail' | 'system';

export type NavSection = {
  id: NavSectionId;
  label: string;
  items: NavItem[];
};

export const coreNavItems: NavItem[] = [
  { path: '/manager', label: 'Главная', icon: Home, match: 'exact' },
  { path: '/manager/leads', label: 'Лиды', icon: UserPlus, match: 'prefix', requiredCapability: MANAGER_CAPABILITY.crmManage },
  { path: '/manager/orders/kanban', label: 'Заказы', icon: ShoppingCart, match: 'prefix', requiredCapability: MANAGER_CAPABILITY.crmManage },
  { path: '/manager/calendar', label: 'Календарь', icon: Calendar, match: 'prefix', requiredCapability: MANAGER_CAPABILITY.crmManage },
  { path: '/manager/customers', label: 'Клиенты', icon: Users, match: 'prefix', requiredCapability: MANAGER_CAPABILITY.crmManage },
];

export const navSections: NavSection[] = [
  {
    id: 'catalog',
    label: 'Каталог',
    items: [
      { path: '/manager/products', label: 'Кондиционеры', icon: Package, match: 'prefix', requiredCapability: MANAGER_CAPABILITY.catalogMasterRead },
      { path: '/manager/product-collections', label: 'Подборки', icon: GalleryVerticalEnd, match: 'prefix', requiredCapability: MANAGER_CAPABILITY.platformManage },
      { path: '/manager/brands', label: 'Бренды', icon: Award, match: 'prefix', requiredCapability: MANAGER_CAPABILITY.platformManage },
      { path: '/manager/features', label: 'Фичи', icon: Sparkles, match: 'prefix', requiredCapability: MANAGER_CAPABILITY.platformManage },
      { path: '/manager/suppliers', label: 'Прайсы поставщиков', icon: FileSpreadsheet, match: 'prefix', requiredCapability: MANAGER_CAPABILITY.platformManage },
      { path: '/manager/supplier-mapping', label: 'Маппинг прайсов', icon: Link2, match: 'prefix', requiredCapability: MANAGER_CAPABILITY.platformManage },
      { path: '/manager/supply', label: 'Поставки', icon: Truck, match: 'prefix', requiredCapability: MANAGER_CAPABILITY.platformManage },
      { path: '/manager/catalog-quality', label: 'Качество каталога', icon: ShieldCheck, match: 'prefix', requiredCapability: MANAGER_CAPABILITY.platformManage },
      { path: '/manager/media', label: 'Медиатека', icon: ImageIcon, match: 'exact', requiredCapability: MANAGER_CAPABILITY.platformManage },
      { path: '/manager/tags', label: 'Теги', icon: Tags, match: 'prefix', requiredCapability: MANAGER_CAPABILITY.platformManage },
    ],
  },
  {
    id: 'services',
    label: 'Услуги',
    items: [
      { path: '/manager/equipment', label: 'Оборудование', icon: Boxes, match: 'prefix', requiredCapability: MANAGER_CAPABILITY.crmManage },
      { path: '/manager/tariffs', label: 'Тарифы услуг', icon: Wallet, match: 'prefix', requiredCapability: MANAGER_CAPABILITY.platformManage },
      { path: '/manager/service-estimates', label: 'Сметы услуг', icon: Calculator, match: 'prefix', requiredCapability: MANAGER_CAPABILITY.platformManage },
    ],
  },
  {
    id: 'team',
    label: 'Команда',
    items: [
      { path: '/manager/staff', label: 'Сотрудники', icon: Users, match: 'prefix', requiredCapability: MANAGER_CAPABILITY.staffManage },
    ],
  },
  {
    id: 'finance',
    label: 'Финансы',
    items: [
      { path: '/manager/payments', label: 'Платежи', icon: ReceiptText, match: 'prefix', requiredCapability: MANAGER_CAPABILITY.platformManage },
    ],
  },
  {
    id: 'mail',
    label: 'Почта',
    items: [
      { path: '/manager/mail/outbox', label: 'Исходящие', icon: Mail, match: 'prefix', requiredCapability: MANAGER_CAPABILITY.platformManage },
    ],
  },
  {
    id: 'system',
    label: 'Системное',
    items: [
      { path: '/manager/settings', label: 'Настройки сайта', icon: Settings, match: 'exact', requiredCapability: MANAGER_CAPABILITY.infrastructureManage },
      { path: '/manager/settings/backup', label: 'DR / Бэкапы', icon: Database, match: 'prefix', requiredCapability: MANAGER_CAPABILITY.infrastructureManage },
    ],
  },
];

export const defaultExpandedNavSections: Record<NavSectionId, boolean> = {
  catalog: true,
  services: true,
  team: true,
  finance: true,
  mail: true,
  system: true,
};
