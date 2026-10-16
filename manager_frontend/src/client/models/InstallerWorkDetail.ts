/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InstallerCollection } from './InstallerCollection';
import type { InstallerEquipment } from './InstallerEquipment';
import type { InstallerMaterial } from './InstallerMaterial';
export type InstallerWorkDetail = {
    id: number;
    order_id: number;
    work_stage_id: (number | null);
    version: number;
    title: string;
    status: string;
    start_time: (string | null);
    end_time?: (string | null);
    customer_name: string;
    customer_phone?: (string | null);
    address?: (string | null);
    collection: InstallerCollection;
    instructions: string;
    equipment: Array<InstallerEquipment>;
    materials: Array<InstallerMaterial>;
};

