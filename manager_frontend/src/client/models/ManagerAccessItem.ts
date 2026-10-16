/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerAccessItem = {
    membership_id: number;
    staff_user_id: number;
    display_name: string;
    tenant_id: number;
    tenant_name: string;
    role: string;
    status: string;
    permissions: Array<'catalog.master.edit' | 'catalog.master.delete'>;
    updated_at: string;
};

