/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotStaffNotificationPayload = {
    event_kind: 'assigned' | 'rescheduled' | 'canceled' | 'departure_reminder';
    staff_user_id: number;
    stage_id: number;
    order_id: number;
    stage_name: string;
    status: string;
    start_time?: (string | null);
    end_time?: (string | null);
    timezone?: string;
    address?: (string | null);
    customer_name?: (string | null);
    customer_phone?: (string | null);
    manager_url: string;
    change_fields?: Array<'assignee' | 'start_time' | 'end_time' | 'address'>;
    reminder_offset_minutes?: (number | null);
};

