export type ToastType = 'success' | 'error';

export type DocumentRoleType = 'seller_buyer' | 'executor_customer' | 'contractor_customer';

export type LogisticsComponentKind = 'indoor' | 'outdoor' | 'accessory' | 'other';

export type BeforeGenerateResult = boolean | void | { proceed?: boolean; mutated?: boolean };

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

export type WaybillProductLine = {
  id?: number | null;
  proposal_id?: number | null;
  product_id?: number | null;
  product_query: string;
  quantity: number;
  price: number;
  cost?: number | null;
  product_country?: string | null;
  product_logistics_components?: ProductLogisticsTemplateComponent[];
  logistics_components?: OrderLogisticsComponent[] | null;
};
