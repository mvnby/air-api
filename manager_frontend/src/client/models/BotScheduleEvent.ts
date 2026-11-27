/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotScheduleEvent = {
    id: string;
    /**
     * Display day in Europe/Minsk.
     */
    date: string;
    /**
     * Local HH:MM for an appointment, null for a reminder.
     */
    time: (string | null);
    type: 'measurement' | 'installation' | 'work_stage' | 'equipment_maintenance';
    title: string;
    status: string;
    customer_name: (string | null);
    customer_phone: (string | null);
    address: (string | null);
    order_id: (number | null);
    order_url: (string | null);
    /**
     * Original due date of a maintenance reminder, including when overdue.
     */
    due_date: (string | null);
};

