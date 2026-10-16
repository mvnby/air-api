/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotStaffContextResponse = {
    telegram_id: number;
    is_staff?: boolean;
    display_name?: string;
    primary_role?: string;
    roles?: Array<string>;
    legacy_installer_id?: (number | null);
    is_manager?: boolean;
    is_executor?: boolean;
    staff_user_id?: (number | null);
    tenant_id?: (number | null);
    tenant_slug?: (string | null);
    tenant_name?: (string | null);
    storefront_id?: (number | null);
    storefront_slug?: (string | null);
    storefront_name?: (string | null);
    context_version?: (number | null);
    can_switch_context?: boolean;
};

