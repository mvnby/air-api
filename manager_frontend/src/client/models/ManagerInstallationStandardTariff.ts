/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerInstallationStandardTariff = {
    code: string;
    title: string;
    description: string;
    price: string;
    product_kind: string;
    indoor_type?: (string | null);
    route_m: string;
    holes_by_type: Record<string, string>;
    capacity_min_kw?: (string | null);
    capacity_max_kw?: (string | null);
    capacity_min_inclusive?: (boolean | null);
    capacity_max_inclusive?: (boolean | null);
};

