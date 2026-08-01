import type { ServiceDescriptionLine } from './service-description-mode';

export type ProductOption = {
  id: number;
  title: string;
  price: number;
  cost?: number;
  is_inverter: boolean;
  power_cooling: number | null;
  availability_status: string;
  vitebsk_qty: number;
  minsk_qty: number;
  specs?: Record<string, any>;
};

export type LogisticsComponentKind = 'indoor' | 'outdoor' | 'accessory' | 'other';

export type ProductLogisticsTemplateComponent = {
  title: string;
  country?: string | null;
  unit?: string | null;
  quantity_per_parent?: number | null;
  price_weight?: number | null;
  kind?: LogisticsComponentKind | null;
};

export type OrderLogisticsComponent = {
  title: string;
  country?: string | null;
  unit: string;
  quantity_per_parent: number;
  unit_price: number;
  kind?: LogisticsComponentKind | null;
};

export type ProductLine = {
  link_id?: number | null;
  product_id: number;
  product_query: string;
  quantity: number;
  price: number;
  cost: number;
  product_country?: string | null;
  product_logistics_components?: ProductLogisticsTemplateComponent[];
  logistics_components?: OrderLogisticsComponent[] | null;
};

export type ServiceLine = ServiceDescriptionLine;

export type OrderDrawerDraft = {
  productLines: ProductLine[];
  serviceLines: ServiceLine[];
};
