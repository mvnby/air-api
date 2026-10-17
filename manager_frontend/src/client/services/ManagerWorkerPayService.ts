/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerWorkerPayWorkspace } from '../models/ManagerWorkerPayWorkspace';
import type { WorkerMoneyCommandResult } from '../models/WorkerMoneyCommandResult';
import type { WorkerMoneyCorrection } from '../models/WorkerMoneyCorrection';
import type { WorkerPayAgreementAction } from '../models/WorkerPayAgreementAction';
import type { WorkerPayAgreementCancel } from '../models/WorkerPayAgreementCancel';
import type { WorkerPayAgreementCreate } from '../models/WorkerPayAgreementCreate';
import type { WorkerPayAgreementRevise } from '../models/WorkerPayAgreementRevise';
import type { WorkerPayOffsetCreate } from '../models/WorkerPayOffsetCreate';
import type { WorkerPayOrderWorkspace } from '../models/WorkerPayOrderWorkspace';
import type { WorkerPayOverview } from '../models/WorkerPayOverview';
import type { WorkerPayPayoutCreate } from '../models/WorkerPayPayoutCreate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerWorkerPayService {
    /**
     * Overview
     * Read scoped worker obligations with live pay authority or verified support access.
     *
     * Former worker liabilities remain visible. Pay and cash authorities are separate;
     * offset needs both. A finance grant does not grant access to order commercial data.
     * @param page
     * @param limit
     * @returns WorkerPayOverview Successful Response
     * @throws ApiError
     */
    public static listManagerWorkerPay(
        page: number = 1,
        limit: number = 50,
    ): CancelablePromise<WorkerPayOverview> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/worker-pay',
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
     * Worker Pay
     * Read one scoped worker's frozen agreements, obligations and settlement history.
     *
     * A foreign profile is404. Safe own projection omits BYN expense equivalents;
     * this Manager projection exposes reviewed frozen costs. No-store, bounded pagination.
     * @param workerProfileId
     * @param page
     * @param limit
     * @returns ManagerWorkerPayWorkspace Successful Response
     * @throws ApiError
     */
    public static getManagerWorkerPay(
        workerProfileId: number,
        page: number = 1,
        limit: number = 50,
    ): CancelablePromise<ManagerWorkerPayWorkspace> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/worker-pay/{worker_profile_id}',
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
     * Order Pay
     * Read eligible explicit assigned works and existing immutable order pay agreements.
     *
     * Requires live pay authority plus scoped CRM access. Candidate reads never create
     * accounts; version0 is returned before first command. Foreign orders return404.
     * @param orderId
     * @returns WorkerPayOrderWorkspace Successful Response
     * @throws ApiError
     */
    public static getManagerOrderWorkerPay(
        orderId: number,
    ): CancelablePromise<WorkerPayOrderWorkspace> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}/worker-pay',
            path: {
                'order_id': orderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Agree
     * Agree fixed positive pay for a live assigned work, freezing its reviewed BYN cost.
     *
     * Live pay authority, Origin/header, shared account version and UUID key are required.
     * Foreign pay needs explicit BYN cost; BYN cost equals amount. Cost enters the order
     * once at agreement, active work cannot be duplicated and legacy positive pay conflicts.
     * @param orderId
     * @param requestBody
     * @returns WorkerMoneyCommandResult Successful Response
     * @throws ApiError
     */
    public static createManagerWorkerPayAgreement(
        orderId: number,
        requestBody: WorkerPayAgreementCreate,
    ): CancelablePromise<WorkerMoneyCommandResult> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/worker-pay/agreements',
            path: {
                'order_id': orderId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Revise
     * Revise agreed, unaccrued pay with fresh account/agreement versions and frozen cost.
     *
     * Requires live pay management, Origin/header and durable UUID. Accrued/cancelled
     * rows cannot be edited. Updates the order cost atomically without creating Payment.
     * @param workerProfileId
     * @param agreementId
     * @param requestBody
     * @returns WorkerMoneyCommandResult Successful Response
     * @throws ApiError
     */
    public static reviseManagerWorkerPayAgreement(
        workerProfileId: number,
        agreementId: number,
        requestBody: WorkerPayAgreementRevise,
    ): CancelablePromise<WorkerMoneyCommandResult> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/worker-pay/{worker_profile_id}/agreements/{agreement_id}/revise',
            path: {
                'worker_profile_id': workerProfileId,
                'agreement_id': agreementId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Accrue
     * Accrue agreed pay into a payable liability without charging order cost again.
     *
     * Live pay management, Origin/header, account/agreement versions and UUID required.
     * Completed/revoked work retains its valid agreement; history stays independent of ACL.
     * @param workerProfileId
     * @param agreementId
     * @param requestBody
     * @returns WorkerMoneyCommandResult Successful Response
     * @throws ApiError
     */
    public static accrueManagerWorkerPayAgreement(
        workerProfileId: number,
        agreementId: number,
        requestBody: WorkerPayAgreementAction,
    ): CancelablePromise<WorkerMoneyCommandResult> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/worker-pay/{worker_profile_id}/agreements/{agreement_id}/accrue',
            path: {
                'worker_profile_id': workerProfileId,
                'agreement_id': agreementId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Cancel
     * Cancel only entirely unpaid pay with a reason and preserve the original agreement.
     *
     * Requires fresh pay authority, Origin/header and both versions/UUID. Existing payouts
     * must first be reversed. Cost removal and cancellation are atomic; no history deleted.
     * @param workerProfileId
     * @param agreementId
     * @param requestBody
     * @returns WorkerMoneyCommandResult Successful Response
     * @throws ApiError
     */
    public static cancelManagerWorkerPayAgreement(
        workerProfileId: number,
        agreementId: number,
        requestBody: WorkerPayAgreementCancel,
    ): CancelablePromise<WorkerMoneyCommandResult> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/worker-pay/{worker_profile_id}/agreements/{agreement_id}/cancel',
            path: {
                'worker_profile_id': workerProfileId,
                'agreement_id': agreementId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Payout
     * Record an external cash/bank remuneration payout allocated FIFO to accrued same-currency pay.
     *
     * Requires live pay authority, Origin/header, account version and UUID. No advances or
     * overpayment; custody of customer money and customer Payments remain independent.
     * @param workerProfileId
     * @param requestBody
     * @returns WorkerMoneyCommandResult Successful Response
     * @throws ApiError
     */
    public static createManagerWorkerPayPayout(
        workerProfileId: number,
        requestBody: WorkerPayPayoutCreate,
    ): CancelablePromise<WorkerMoneyCommandResult> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/worker-pay/{worker_profile_id}/payouts',
            path: {
                'worker_profile_id': workerProfileId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Offset
     * Explicitly offset accrued unpaid remuneration against free customer cash in the same currency.
     *
     * Requires both live pay/cash grants, Origin/header, shared account version and UUID.
     * Pending reservations and other currencies cannot fund an offset. Both FIFO allocations
     * and balances change atomically; no client Payment or second order cost is created.
     * @param workerProfileId
     * @param requestBody
     * @returns WorkerMoneyCommandResult Successful Response
     * @throws ApiError
     */
    public static createManagerWorkerPayOffset(
        workerProfileId: number,
        requestBody: WorkerPayOffsetCreate,
    ): CancelablePromise<WorkerMoneyCommandResult> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/worker-pay/{worker_profile_id}/offsets',
            path: {
                'worker_profile_id': workerProfileId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Reverse
     * Reverse a payout or offset with a reason, restoring the original obligations.
     *
     * Requires fresh pay authority, account version, Origin/header and UUID; offset reversal
     * additionally needs cash authority and restores custody. Original rows/allocations stay
     * immutable, customer Payments and frozen order cost are unchanged. Identical replay safe.
     * @param workerProfileId
     * @param payoutId
     * @param requestBody
     * @returns WorkerMoneyCommandResult Successful Response
     * @throws ApiError
     */
    public static reverseManagerWorkerPayPayout(
        workerProfileId: number,
        payoutId: number,
        requestBody: WorkerMoneyCorrection,
    ): CancelablePromise<WorkerMoneyCommandResult> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/worker-pay/{worker_profile_id}/payouts/{payout_id}/reverse',
            path: {
                'worker_profile_id': workerProfileId,
                'payout_id': payoutId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
