/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerCollectionBalance } from './ManagerCollectionBalance';
import type { ManagerCollectionInstruction } from './ManagerCollectionInstruction';
import type { ManagerWorkerAssignment } from './ManagerWorkerAssignment';
import type { ManagerWorkerMaterial } from './ManagerWorkerMaterial';
export type ManagerInstallerWorkspace = {
    order_id: number;
    assignments: Array<ManagerWorkerAssignment>;
    materials: Array<ManagerWorkerMaterial>;
    collection: ManagerCollectionInstruction;
    balances: Array<ManagerCollectionBalance>;
    financial_fingerprint: string;
};

