/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AdminScheduleService {
    /**
     * Search Installers
     * Search installers for Select2.
     * @param q
     * @returns any Successful Response
     * @throws ApiError
     */
    public static searchInstallersAdminApiAdminInstallersSearchGet(
        q: string = '',
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/admin/api/admin/installers/search',
            query: {
                'q': q,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Calendar Events
     * Get events for FullCalendar (Orders with Installation or Assessment dates).
     * @param start
     * @param end
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getCalendarEventsAdminCalendarEventsGet(
        start?: (string | null),
        end?: (string | null),
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/admin/calendar/events',
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
