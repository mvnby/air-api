/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * B2C-only facts frozen on draft creation, never read from mutable CRM state.
 */
export type ConsumerDocumentTermsPayload = {
    equipment_brand?: (string | null);
    equipment_model?: (string | null);
    equipment_serial?: (string | null);
    goods_warranty_months?: (number | null);
    goods_warranty_terms?: (string | null);
    work_warranty_months?: (number | null);
    work_warranty_terms?: (string | null);
    route_length_meters?: (string | null);
    route_liquid_pipe_diameter_mm?: (string | null);
    route_gas_pipe_diameter_mm?: (string | null);
    route_drainage?: (string | null);
    route_power_supply?: (string | null);
    route_notes?: (string | null);
    route_photo_fixation_performed?: boolean;
    route_pressure_test_performed?: boolean;
    route_ends_capped?: boolean;
};

