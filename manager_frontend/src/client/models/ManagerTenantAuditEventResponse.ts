/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerTenantAuditEventResponse = {
    id: number;
    storefront_id: number;
    actor_staff_user_id?: (number | null);
    actor_username: string;
    action: string;
    entity_type: string;
    entity_id: number;
    request_id: string;
    change_set?: Record<string, any>;
    created_at: string;
};

