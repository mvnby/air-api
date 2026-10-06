/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type PersonalTaskResponse = {
    id: number;
    text: string;
    description?: (string | null);
    status: 'active' | 'completed' | 'cancelled';
    version: number;
    author_staff_user_id: number;
    author_name: string;
    assignee_staff_user_id?: (number | null);
    assignee_name?: (string | null);
    due_at?: (string | null);
    reminder_at?: (string | null);
    reminder_due?: boolean;
    lead_id?: (number | null);
    customer_id?: (number | null);
    order_id?: (number | null);
    equipment_id?: (number | null);
    completed_at?: (string | null);
    cancelled_at?: (string | null);
    created_at: string;
    updated_at: string;
};

