export type ConsumerDocumentTerms = {
  equipment_brand: string | null;
  equipment_model: string | null;
  equipment_serial: string | null;
  goods_warranty_months: number | null;
  goods_warranty_terms: string | null;
  work_warranty_months: number | null;
  work_warranty_terms: string | null;
  route_length_meters: string | null;
  route_liquid_pipe_diameter_mm: string | null;
  route_gas_pipe_diameter_mm: string | null;
  route_drainage: string | null;
  route_power_supply: string | null;
  route_notes: string | null;
  route_photo_fixation_performed: boolean;
  route_pressure_test_performed: boolean;
  route_ends_capped: boolean;
};

export const B2C_NATIVE_DOCUMENT_TYPES = [
  'b2c_supply_installation_act',
  'b2c_customer_equipment_installation_act',
  'b2c_maintenance_repair_act',
  'b2c_route_laying_act',
] as const;

export const isConsumerDocumentType = (documentType: string) => (
  B2C_NATIVE_DOCUMENT_TYPES.includes(documentType as typeof B2C_NATIVE_DOCUMENT_TYPES[number])
);

export const isRouteLayingDocumentType = (documentType: string) => (
  documentType === 'b2c_route_laying_act'
);

export const isSupplyInstallationDocumentType = (documentType: string) => (
  documentType === 'b2c_supply_installation_act'
);

export const createDefaultConsumerDocumentTerms = (
  goodsWarrantyMonths: number | null = 36,
): ConsumerDocumentTerms => ({
  equipment_brand: null,
  equipment_model: null,
  equipment_serial: null,
  goods_warranty_months: goodsWarrantyMonths,
  goods_warranty_terms: null,
  work_warranty_months: null,
  work_warranty_terms: null,
  route_length_meters: null,
  route_liquid_pipe_diameter_mm: null,
  route_gas_pipe_diameter_mm: null,
  route_drainage: null,
  route_power_supply: null,
  route_notes: null,
  route_photo_fixation_performed: false,
  route_pressure_test_performed: false,
  route_ends_capped: false,
});
