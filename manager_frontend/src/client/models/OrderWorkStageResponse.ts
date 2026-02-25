/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerInstallerResponse } from './ManagerInstallerResponse';
export type OrderWorkStageResponse = {
    id: number;
    order_id: number;
    name: string;
    status: string;
    start_time?: (string | null);
    end_time?: (string | null);
    installer_id?: (number | null);
    manager_comment?: (string | null);
    installer_report?: (string | null);
    installer?: (ManagerInstallerResponse | null);
};

