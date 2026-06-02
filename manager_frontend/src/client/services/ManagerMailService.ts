/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BankReceiptAttachPayload } from '../models/BankReceiptAttachPayload';
import type { BankReceiptImportResponse } from '../models/BankReceiptImportResponse';
import type { BankReceiptListResponse } from '../models/BankReceiptListResponse';
import type { BankReceiptResponse } from '../models/BankReceiptResponse';
import type { BankReceiptStatusPayload } from '../models/BankReceiptStatusPayload';
import type { BankStatementImportResponse } from '../models/BankStatementImportResponse';
import type { Body_import_manager_bank_statement } from '../models/Body_import_manager_bank_statement';
import type { EmailLeadImportResponse } from '../models/EmailLeadImportResponse';
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
     * Import Manager Email Leads
     * @param dryRun
     * @param lookbackDays
     * @returns EmailLeadImportResponse Successful Response
     * @throws ApiError
     */
    public static importManagerEmailLeads(
        dryRun: boolean = false,
        lookbackDays?: (number | null),
    ): CancelablePromise<EmailLeadImportResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/mail/leads/import',
            query: {
                'dry_run': dryRun,
                'lookback_days': lookbackDays,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Import Manager Bank Statement
     * @param formData
     * @returns BankStatementImportResponse Successful Response
     * @throws ApiError
     */
    public static importManagerBankStatement(
        formData: Body_import_manager_bank_statement,
    ): CancelablePromise<BankStatementImportResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/mail/bank-receipts/import-statement',
            formData: formData,
            mediaType: 'multipart/form-data',
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
     * Patch Manager Bank Receipt Status
     * @param receiptId
     * @param requestBody
     * @returns BankReceiptResponse Successful Response
     * @throws ApiError
     */
    public static patchManagerBankReceiptStatus(
        receiptId: number,
        requestBody: BankReceiptStatusPayload,
    ): CancelablePromise<BankReceiptResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/mail/bank-receipts/{receipt_id}/status',
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
     * Delete Manager Bank Receipt
     * @param receiptId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static deleteManagerBankReceipt(
        receiptId: number,
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/mail/bank-receipts/{receipt_id}',
            path: {
                'receipt_id': receiptId,
            },
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
