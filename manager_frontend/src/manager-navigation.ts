import type { Component } from 'vue';
import {
  Award,
  Calendar,
  Calculator,
  Database,
  FileSpreadsheet,
  Home,
  Image as ImageIcon,
  Link2,
  Mail,
  Package,
  ReceiptText,
  Settings,
  ShieldCheck,
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
  ownerOnly?: boolean;
};

export type NavSectionId = 'catalog' | 'services' | 'team' | 'finance' | 'mail' | 'system';

export type NavSection = {
  id: NavSectionId;
  label: string;
  items: NavItem[];
};

export const coreNavItems: NavItem[] = [
  { path: '/manager', label: 'Главная', icon: Home, match: 'exact' },
  { path: '/manager/leads', label: 'Лиды', icon: UserPlus, match: 'prefix' },
  { path: '/manager/orders/kanban', label: 'Заказы', icon: ShoppingCart, match: 'prefix' },
  { path: '/manager/calendar', label: 'Календарь', icon: Calendar, match: 'prefix' },
  { path: '/manager/customers', label: 'Клиенты', icon: Users, match: 'prefix' },
];

export const navSections: NavSection[] = [
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
      { path: '/manager/staff', label: 'Сотрудники', icon: Users, match: 'prefix', ownerOnly: true },
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
      { path: '/manager/settings', label: 'Настройки сайта', icon: Settings, match: 'exact', ownerOnly: true },
      { path: '/manager/settings/backup', label: 'DR / Бэкапы', icon: Database, match: 'prefix', ownerOnly: true },
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
