/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotReserveRequest = {
    id: number;
    request_id: number;
    supplier_name: string;
    quantity: number;
    status: string;
    intent: 'reserve' | 'order';
    reserved_until: (string | null);
    supplier_message: (string | null);
    can_mark_sent: boolean;
    can_confirm: boolean;
};

