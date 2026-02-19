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
     * Get calendar events (assessments and installations) within a date range.
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
