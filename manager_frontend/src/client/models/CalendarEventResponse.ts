/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CalendarEventType } from './CalendarEventType';
export type CalendarEventResponse = {
    id: string;
    order_id?: (number | null);
    equipment_id?: (number | null);
    type: CalendarEventType;
    date: string;
    status: string;
    customer_name?: (string | null);
    customer_phone?: (string | null);
    address?: (string | null);
    title: string;
    start: string;
    allDay?: boolean;
    color: string;
};

