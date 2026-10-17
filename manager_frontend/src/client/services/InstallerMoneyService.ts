/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ClientMoneyReceived } from '../models/ClientMoneyReceived';
import type { WorkerCashHandoverAction } from '../models/WorkerCashHandoverAction';
import type { WorkerCashHandoverCreate } from '../models/WorkerCashHandoverCreate';
import type { WorkerMoneyCommandResult } from '../models/WorkerMoneyCommandResult';
import type { WorkerMoneyRecipients } from '../models/WorkerMoneyRecipients';
import type { WorkerMoneyWorkspace } from '../models/WorkerMoneyWorkspace';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class InstallerMoneyService {
    /**
     * Own Money
     * Read only personal cash balances and paginated immutable receipt history in the selected company/site.
     *
     * Active real membership is required; support impersonation is forbidden. Closed or
     * revoked work does not erase financial history or restore order access. No prices,
     * purchases, supplier data or other workers' transactions are exposed. No-store.
     * @param page
     * @param limit
     * @returns WorkerMoneyWorkspace Successful Response
     * @throws ApiError
     */
    public static getInstallerMoney(
        page: number = 1,
        limit: number = 50,
    ): CancelablePromise<WorkerMoneyWorkspace> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/installer/money',
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
     * Recipients
     * List other active actual company members authorized to acknowledge cash receipt.
     *
     * Returns only names/identifiers of owners, administrators and managers explicitly
     * granted worker.money.manage. A platform support identity is never a recipient.
     * Pagination is bounded at 100; this read creates no account or financial entry.
     * @param page
     * @param limit
     * @returns WorkerMoneyRecipients Successful Response
     * @throws ApiError
     */
    public static listInstallerMoneyRecipients(
        page: number = 1,
        limit: number = 50,
    ): CancelablePromise<WorkerMoneyRecipients> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/installer/money/recipients',
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
     * Receive
     * Confirm actual full/partial client cash against a live reviewed collection instruction.
     *
     * Team Origin/header and current designated assignment are required. Exact positive
     * amount/currency cannot exceed the instruction or fresh customer balance. Atomically
     * records one Payment, cash custody, consumed instruction/version and audit. A UUID
     * key replays the committed result; changed payload/key reuse or stale version is409.
     * Foreign/revoked assignments are404. Receiving cash is not installer remuneration.
     * @param assignmentId
     * @param requestBody
     * @returns WorkerMoneyCommandResult Successful Response
     * @throws ApiError
     */
    public static confirmInstallerClientMoney(
        assignmentId: number,
        requestBody: ClientMoneyReceived,
    ): CancelablePromise<WorkerMoneyCommandResult> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/installer/works/{assignment_id}/collections',
            path: {
                'assignment_id': assignmentId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Handover
     * Report cash handed to an eligible company recipient, reserving personal available funds.
     *
     * Requires team Origin/header, fresh account version and UUID replay key. Exact
     * currency-specific funds are allocated to source receipts and reserved atomically.
     * Money remains held until the selected recipient acknowledges it. Overbooking,
     * self-recipient or unavailable recipient is rejected; this never adds client Payment.
     * @param requestBody
     * @returns WorkerMoneyCommandResult Successful Response
     * @throws ApiError
     */
    public static createInstallerCashHandover(
        requestBody: WorkerCashHandoverCreate,
    ): CancelablePromise<WorkerMoneyCommandResult> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/installer/money/handovers',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Cancel Handover
     * Cancel only the actor's pending handover using its row version and a UUID key.
     *
     * Team Origin/header and live identity are required. Releases reservations without
     * changing client payment or erasing history. Already resolved or stale requests
     * return409; foreign company/site/account identifiers return404. Safe identical replay.
     * @param handoverId
     * @param requestBody
     * @returns WorkerMoneyCommandResult Successful Response
     * @throws ApiError
     */
    public static cancelInstallerCashHandover(
        handoverId: number,
        requestBody: WorkerCashHandoverAction,
    ): CancelablePromise<WorkerMoneyCommandResult> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/installer/money/handovers/{handover_id}/cancel',
            path: {
                'handover_id': handoverId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
