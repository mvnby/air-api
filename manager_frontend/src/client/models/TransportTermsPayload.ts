/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TransportOperation } from './TransportOperation';
/**
 * Optional transport facts for printable TN-2/TTN-1 forms.
 */
export type TransportTermsPayload = {
    car_model?: (string | null);
    car_number?: (string | null);
    driver_name?: (string | null);
    carrier?: (string | null);
    trip_sheet_number?: (string | null);
    freight_payer?: (string | null);
    loading_point?: (string | null);
    unloading_point?: (string | null);
    loading?: (TransportOperation | null);
    unloading?: (TransportOperation | null);
};

