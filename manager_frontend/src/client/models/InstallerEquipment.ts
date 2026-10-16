/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InstallerTechnicalSpec } from './InstallerTechnicalSpec';
export type InstallerEquipment = {
    key: string;
    name: string;
    brand?: (string | null);
    model?: (string | null);
    serial?: (string | null);
    quantity: number;
    technical_specs?: Array<InstallerTechnicalSpec>;
};

