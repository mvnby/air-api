/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CalendarEventResponse } from '../models/CalendarEventResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerCalendarService {
    /**
     * Get Manager Calendar Events
     * Read assessment, installation and work-stage events for orders accessible in the current
     * Manager tenant/storefront, plus tenant-scoped equipment-maintenance reminders without a
     * storefront filter (type=equipment_maintenance, order_id=null). Overdue maintenance is
     * displayed today in start while date retains the original due date; the requested range
     * filters its display start. start and end are required ISO datetimes; boundaries are
     * inclusive and the response is an unpaginated list. Current implementation strips timezone
     * offsets without converting wall-clock values, so send dates in the stored scheduling time
     * convention. start greater than end returns 400. This does not include personal tasks or
     * modify schedules.
     * @param start Start date (ISO format)
     * @param end End date (ISO format)
     * @returns CalendarEventResponse Successful Response
     * @throws ApiError
     */
    public static getManagerCalendarEvents(
        start: string,
        end: string,
    ): CancelablePromise<Array<CalendarEventResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/calendar/events',
            query: {
                'start': start,
                'end': end,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
