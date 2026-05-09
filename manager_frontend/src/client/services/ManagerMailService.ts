/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BankReceiptAttachPayload } from '../models/BankReceiptAttachPayload';
import type { BankReceiptImportResponse } from '../models/BankReceiptImportResponse';
import type { BankReceiptListResponse } from '../models/BankReceiptListResponse';
import type { BankReceiptResponse } from '../models/BankReceiptResponse';
import type { OrderEmailSendPayload } from '../models/OrderEmailSendPayload';
import type { OutgoingEmailResponse } from '../models/OutgoingEmailResponse';
import type { OutgoingEmailSendPayload } from '../models/OutgoingEmailSendPayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerMailService {
    /**
     * Import Manager Bank Receipts
     * @param limit
     * @returns BankReceiptImportResponse Successful Response
     * @throws ApiError
     */
    public static importManagerBankReceipts(
        limit: number = 50,
    ): CancelablePromise<BankReceiptImportResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/mail/bank-receipts/import',
            query: {
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Manager Bank Receipts
     * @param page
     * @param limit
     * @param status
     * @param payerUnp
     * @param orderId
     * @returns BankReceiptListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerBankReceipts(
        page: number = 1,
        limit: number = 50,
        status?: (string | null),
        payerUnp?: (string | null),
        orderId?: (number | null),
    ): CancelablePromise<BankReceiptListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/mail/bank-receipts',
            query: {
                'page': page,
                'limit': limit,
                'status': status,
                'payer_unp': payerUnp,
                'order_id': orderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Attach Manager Bank Receipt
     * @param receiptId
     * @param requestBody
     * @returns BankReceiptResponse Successful Response
     * @throws ApiError
     */
    public static attachManagerBankReceipt(
        receiptId: number,
        requestBody: BankReceiptAttachPayload,
    ): CancelablePromise<BankReceiptResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/mail/bank-receipts/{receipt_id}/attach',
            path: {
                'receipt_id': receiptId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Send Manager Test Email
     * @param requestBody
     * @returns OutgoingEmailResponse Successful Response
     * @throws ApiError
     */
    public static sendManagerTestEmail(
        requestBody: OutgoingEmailSendPayload,
    ): CancelablePromise<OutgoingEmailResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/mail/email/send-test',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Send Manager Order Email
     * @param orderId
     * @param requestBody
     * @returns OutgoingEmailResponse Successful Response
     * @throws ApiError
     */
    public static sendManagerOrderEmail(
        orderId: number,
        requestBody: OrderEmailSendPayload,
    ): CancelablePromise<OutgoingEmailResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/mail/orders/{order_id}/email',
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
}
