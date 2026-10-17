/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WorkerCashHandoverAction } from '../models/WorkerCashHandoverAction';
import type { WorkerMoneyCommandResult } from '../models/WorkerMoneyCommandResult';
import type { WorkerMoneyCorrection } from '../models/WorkerMoneyCorrection';
import type { WorkerMoneyOverview } from '../models/WorkerMoneyOverview';
import type { WorkerMoneyWorkspace } from '../models/WorkerMoneyWorkspace';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerWorkerMoneyService {
    /**
     * Overview
     * Read company/site worker cash balances with bounded pagination and live CRM authority.
     *
     * Includes historical accounts of disabled workers so liabilities do not disappear.
     * can_manage independently describes cash-command authority; CRM alone cannot
     * acknowledge transfers or reverse receipts. Reads do not provision accounts.
     * @param page
     * @param limit
     * @returns WorkerMoneyOverview Successful Response
     * @throws ApiError
     */
    public static listManagerWorkerMoney(
        page: number = 1,
        limit: number = 50,
    ): CancelablePromise<WorkerMoneyOverview> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/worker-money',
            query: {
                'page': page,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Worker Money
     * Read selected company/site worker cash history without granting access to other tenants.
     *
     * Requires fresh CRM authority; a foreign worker returns404. History survives work
     * closure/revocation. Exact balances distinguish held, pending and available funds;
     * can_reverse applies only to fully unallocated receipts. Responses are no-store.
     * @param workerProfileId
     * @param page
     * @param limit
     * @returns WorkerMoneyWorkspace Successful Response
     * @throws ApiError
     */
    public static getManagerWorkerMoney(
        workerProfileId: number,
        page: number = 1,
        limit: number = 50,
    ): CancelablePromise<WorkerMoneyWorkspace> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/worker-money/{worker_profile_id}',
            path: {
                'worker_profile_id': workerProfileId,
            },
            query: {
                'page': page,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Confirm Handover
     * Acknowledge actual cash receipt as the selected recipient with live cash-management authority.
     *
     * Actual owner/admin or explicit worker.money.manage membership, team Origin/header,
     * handover version and UUID key are required. Another recipient/support cannot confirm.
     * Pending reservations become confirmed cash handed over atomically; no second client
     * Payment is created. Conflicts are409; identical committed commands replay safely.
     * @param workerProfileId
     * @param handoverId
     * @param requestBody
     * @returns WorkerMoneyCommandResult Successful Response
     * @throws ApiError
     */
    public static confirmManagerCashHandover(
        workerProfileId: number,
        handoverId: number,
        requestBody: WorkerCashHandoverAction,
    ): CancelablePromise<WorkerMoneyCommandResult> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/worker-money/{worker_profile_id}/handovers/{handover_id}/confirm',
            path: {
                'worker_profile_id': workerProfileId,
                'handover_id': handoverId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Reject Handover
     * Reject a pending scoped handover with live owner/admin or delegated cash authority.
     *
     * Team Origin/header, current handover version and UUID key are required. Releases
     * reserved cash, preserves the request/audit and changes no client payments. Foreign
     * identifiers are404, stale/resolved operations409, identical replay is safe.
     * @param workerProfileId
     * @param handoverId
     * @param requestBody
     * @returns WorkerMoneyCommandResult Successful Response
     * @throws ApiError
     */
    public static rejectManagerCashHandover(
        workerProfileId: number,
        handoverId: number,
        requestBody: WorkerCashHandoverAction,
    ): CancelablePromise<WorkerMoneyCommandResult> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/worker-money/{worker_profile_id}/handovers/{handover_id}/reject',
            path: {
                'worker_profile_id': workerProfileId,
                'handover_id': handoverId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Reverse Receipt
     * Correct an entirely unallocated erroneous receipt with an explicit reason and counter-payment.
     *
     * Live cash-management authority, team Origin/header, account version and UUID key
     * are required. Original receipt/Payment remain immutable. Confirmed/pending handover
     * funds cannot be reversed; cancel pending handovers first. The corrective negative
     * Payment, audit and cash reversal are atomic; collection requires Manager review.
     * @param workerProfileId
     * @param receiptId
     * @param requestBody
     * @returns WorkerMoneyCommandResult Successful Response
     * @throws ApiError
     */
    public static reverseManagerWorkerReceipt(
        workerProfileId: number,
        receiptId: number,
        requestBody: WorkerMoneyCorrection,
    ): CancelablePromise<WorkerMoneyCommandResult> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/worker-money/{worker_profile_id}/receipts/{receipt_id}/reverse',
            path: {
                'worker_profile_id': workerProfileId,
                'receipt_id': receiptId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
