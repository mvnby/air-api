/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BankReceiptAllocationDetailResponse } from '../models/BankReceiptAllocationDetailResponse';
import type { BankReceiptAllocationsReplacePayload } from '../models/BankReceiptAllocationsReplacePayload';
import type { BankReceiptAttachPayload } from '../models/BankReceiptAttachPayload';
import type { BankReceiptGroupAttachPayload } from '../models/BankReceiptGroupAttachPayload';
import type { BankReceiptImportResponse } from '../models/BankReceiptImportResponse';
import type { BankReceiptListResponse } from '../models/BankReceiptListResponse';
import type { BankReceiptResponse } from '../models/BankReceiptResponse';
import type { BankReceiptStatusPayload } from '../models/BankReceiptStatusPayload';
import type { BankStatementImportResponse } from '../models/BankStatementImportResponse';
import type { Body_import_manager_bank_statement } from '../models/Body_import_manager_bank_statement';
import type { EmailLeadImportJobResponse } from '../models/EmailLeadImportJobResponse';
import type { OrderEmailComposePayload } from '../models/OrderEmailComposePayload';
import type { OrderEmailComposeResponse } from '../models/OrderEmailComposeResponse';
import type { OrderEmailSendPayload } from '../models/OrderEmailSendPayload';
import type { OutgoingEmailDetailResponse } from '../models/OutgoingEmailDetailResponse';
import type { OutgoingEmailListResponse } from '../models/OutgoingEmailListResponse';
import type { OutgoingEmailResponse } from '../models/OutgoingEmailResponse';
import type { OutgoingEmailSendPayload } from '../models/OutgoingEmailSendPayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerMailService {
    /**
     * Import Manager Bank Receipts
     * Synchronously import up to 100 bank-notification messages from the configured IMAP
     * source, deduplicate known receipts and run matching that can create linked order
     * payments. New receipt notifications are attempted separately; notification failure does
     * not undo import. Configured processed-folder handling can move successfully imported
     * messages out of the source mailbox; invalid configuration/input returns 400. No caller
     * replay receipt is supplied; inspect import counters/current receipts after uncertain
     * results. Requires system-tenant Manager access. These are platform mail/receipt records,
     * not a current-storefront-only journal.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Start the shared process-local email-lead import in the background for the resolved
     * system tenant/storefront. Requires system-tenant Manager access. Returns job state
     * rather than completed counts; poll import/status. dry_run evaluates decisions without
     * creating leads; lookback_days is 1–30 when supplied. A running import returns
     * already_running rather than another concurrent task in this process; setup failure
     * returns 400. This is not a durable or actor-specific job receipt.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param dryRun
     * @param lookbackDays
     * @returns EmailLeadImportJobResponse Successful Response
     * @throws ApiError
     */
    public static importManagerEmailLeads(
        dryRun: boolean = false,
        lookbackDays?: (number | null),
    ): CancelablePromise<EmailLeadImportJobResponse> {
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
     * Get Manager Email Lead Import Status
     * Read the latest shared process-local manual/scheduled email-lead import snapshot.
     * Requires system-tenant Manager access. idle/running/completed/failed and optional
     * result/error describe the worker seen by this process; restart or another process can
     * show a different snapshot. This read does not start or repeat an import.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @returns EmailLeadImportJobResponse Successful Response
     * @throws ApiError
     */
    public static getManagerEmailLeadImportStatus(): CancelablePromise<EmailLeadImportJobResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/mail/leads/import/status',
        });
    }
    /**
     * Import Manager Bank Statement
     * Import a supported bank CSV statement into platform receipts, match existing credits
     * using reconciliation keys and mark duplicate/missing-in-period candidates for review.
     * New matches can create order payments. Parsing/provider/service failures return 400.
     * Reads the uploaded file without a route-specific size cap; no caller idempotency receipt
     * is supplied, and repeat imports can update reconciliation flags. Requires system-tenant
     * Manager access. These are platform mail/receipt records, not a current-storefront-only
     * journal.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Page platform bank receipts with optional status/payer/order filters and
     * allocated/unallocated totals, newest first. limit is at most 100. Reading does not
     * allocate funds or mark a receipt resolved. Requires system-tenant Manager access. These
     * are platform mail/receipt records, not a current-storefront-only journal.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Allocate an unattached platform receipt to one selected open order up to its outstanding
     * debt, create a payment and refresh finances; excess remains unallocated. This explicit
     * manual action allows payer-UNP mismatch and records that override. Missing/already
     * attached/invalid receipt or closed/missing/unpaid-balance-free order returns 400.
     * Repeated attach is rejected, not receipt replay. Requires system-tenant Manager access.
     * These are platform mail/receipt records, not a current-storefront-only journal.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Attach Manager Bank Receipt Group
     * Allocate an unattached platform receipt across at least two open orders with outstanding
     * balances and the same payer UNP. Uses supplied IDs or the saved group suggestion; total
     * group debt must match receipt amount within service money tolerance. Creates linked
     * payments and refreshes all finances. Missing/invalid/already attached/mismatched context
     * returns 400; repeated attach is not replayed. Requires system-tenant Manager access.
     * These are platform mail/receipt records, not a current-storefront-only journal.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param receiptId
     * @param requestBody
     * @returns BankReceiptResponse Successful Response
     * @throws ApiError
     */
    public static attachManagerBankReceiptGroup(
        receiptId: number,
        requestBody: BankReceiptGroupAttachPayload,
    ): CancelablePromise<BankReceiptResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/mail/bank-receipts/{receipt_id}/attach-group',
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
     * Get Manager Bank Receipt Allocation
     * Read a platform receipt’s current allocations and candidate-order balances for review.
     * Existing linked closed orders can appear; other candidates must be open and match payer
     * UNP. Missing receipt or service failure returns 400. Does not replace payments or
     * reserve allocation amounts. Requires system-tenant Manager access. These are platform
     * mail/receipt records, not a current-storefront-only journal.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param receiptId
     * @returns BankReceiptAllocationDetailResponse Successful Response
     * @throws ApiError
     */
    public static getManagerBankReceiptAllocation(
        receiptId: number,
    ): CancelablePromise<BankReceiptAllocationDetailResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/mail/bank-receipts/{receipt_id}/allocation',
            path: {
                'receipt_id': receiptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Replace Manager Bank Receipt Allocations
     * Replace all platform payments allocated from this receipt with the supplied set and
     * refresh every affected order. Requires distinct orders, positive amounts, matching payer
     * UNP and amounts within receipt/debt; newly added closed orders are refused, existing
     * linked closed orders remain eligible. Empty set clears allocations and returns
     * requires_review. Identical normalized allocation/type state is a no-op; no caller key or
     * expected_version precondition is supplied. Missing/invalid/ineligible context returns
     * 400. Requires system-tenant Manager access. These are platform mail/receipt records, not
     * a current-storefront-only journal.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param receiptId
     * @param requestBody
     * @returns BankReceiptResponse Successful Response
     * @throws ApiError
     */
    public static replaceManagerBankReceiptAllocations(
        receiptId: number,
        requestBody: BankReceiptAllocationsReplacePayload,
    ): CancelablePromise<BankReceiptResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/mail/bank-receipts/{receipt_id}/allocations',
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
     * Set a supported review/resolution status and manual reason on a platform receipt.
     * matched/partially_allocated must be produced by allocation commands (400 otherwise).
     * Moving to void/requires_review/closed_orders/non_order_income removes linked payments
     * and refreshes all affected orders; this is not just a label edit.
     * Missing/unsupported/service failure returns 400. No replay receipt or version
     * precondition is supplied. Requires system-tenant Manager access. These are platform
     * mail/receipt records, not a current-storefront-only journal.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Delete a platform receipt only when it has no matched_payment_id. A receipt linked to
     * payment must instead be marked erroneous through status handling. Missing receipt or
     * refusal returns 400, including repeat after deletion. This does not delete the original
     * mailbox message. Requires system-tenant Manager access. These are platform mail/receipt
     * records, not a current-storefront-only journal.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * List Manager Outgoing Emails
     * Page the platform outgoing-email journal with status/order/customer/recipient/text/date
     * filters and limit at most 100. Includes attempts and delivery/error metadata;
     * unsupported status or service failure returns 400. Reading does not send or retry
     * messages. Requires system-tenant Manager access. These are platform mail/receipt
     * records, not a current-storefront-only journal.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param page
     * @param limit
     * @param status
     * @param orderId
     * @param customerId
     * @param recipient
     * @param q
     * @param dateFrom
     * @param dateTo
     * @returns OutgoingEmailListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerOutgoingEmails(
        page: number = 1,
        limit: number = 50,
        status?: (string | null),
        orderId?: (number | null),
        customerId?: (number | null),
        recipient?: (string | null),
        q?: (string | null),
        dateFrom?: (string | null),
        dateTo?: (string | null),
    ): CancelablePromise<OutgoingEmailListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/mail/outgoing-emails',
            query: {
                'page': page,
                'limit': limit,
                'status': status,
                'order_id': orderId,
                'customer_id': customerId,
                'recipient': recipient,
                'q': q,
                'date_from': dateFrom,
                'date_to': dateTo,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Outgoing Email
     * Read a platform outgoing-email record including stored content/attachment metadata and
     * its retry attempts. Missing record or any detail-loading failure is mapped to 404 by
     * this route. Reading is not a delivery confirmation from the recipient’s mailbox and does
     * not retry. Requires system-tenant Manager access. These are platform mail/receipt
     * records, not a current-storefront-only journal.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param emailId
     * @returns OutgoingEmailDetailResponse Successful Response
     * @throws ApiError
     */
    public static getManagerOutgoingEmail(
        emailId: number,
    ): CancelablePromise<OutgoingEmailDetailResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/mail/outgoing-emails/{email_id}',
            path: {
                'email_id': emailId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Manager Order Outgoing Emails
     * Read the first page of platform outgoing-email history filtered by order ID, with limit
     * at most 100. This journal lookup does not perform the tenant/storefront order
     * authorization used by compose/send. Service failure returns 400; an order without
     * records can return an empty list. Requires system-tenant Manager access. These are
     * platform mail/receipt records, not a current-storefront-only journal.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @param limit
     * @returns OutgoingEmailListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerOrderOutgoingEmails(
        orderId: number,
        limit: number = 20,
    ): CancelablePromise<OutgoingEmailListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/mail/orders/{order_id}/outgoing-emails',
            path: {
                'order_id': orderId,
            },
            query: {
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Retry Manager Outgoing Email
     * Create a new linked attempt for a failed platform outgoing email using its stored
     * recipient/body; only failed originals are accepted (400 otherwise). Messages with
     * attachments cannot be reconstructed by this action: a failed attempt is recorded and
     * documents must be sent again from the order. SMTP failure can return HTTP success with
     * status=failed; inspect status/error. No caller replay receipt prevents another attempt.
     * Requires system-tenant Manager access. These are platform mail/receipt records, not a
     * current-storefront-only journal.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param emailId
     * @returns OutgoingEmailResponse Successful Response
     * @throws ApiError
     */
    public static retryManagerOutgoingEmail(
        emailId: number,
    ): CancelablePromise<OutgoingEmailResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/mail/outgoing-emails/{email_id}/retry',
            path: {
                'email_id': emailId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Send Manager Test Email
     * Send a real message through the configured system SMTP and record the attempt in the
     * platform journal. This is not a dry run despite the test route name. Invalid
     * configuration/content or SMTP failure returns 400; a failed recorded attempt may already
     * exist. No replay receipt is supplied, so inspect the journal before retrying an
     * uncertain result. Requires system-tenant Manager access. These are platform mail/receipt
     * records, not a current-storefront-only journal.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Compose Manager Order Email
     * Preview suggested recipient/subject/body/attachments for an order accessible in the
     * current system tenant/storefront. Requires system-tenant Manager access through the mail
     * router. Does not send email or change proposal/document lifecycle; invalid
     * order/document/template context returns 400.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @param requestBody
     * @returns OrderEmailComposeResponse Successful Response
     * @throws ApiError
     */
    public static composeManagerOrderEmail(
        orderId: number,
        requestBody: OrderEmailComposePayload,
    ): CancelablePromise<OrderEmailComposeResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/mail/orders/{order_id}/compose',
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
     * Send Manager Order Email
     * Send email with selected documents from an order accessible in the current system
     * tenant/storefront and record outgoing history. Requires system-tenant Manager access. At
     * most 10 documents, 10 MB per PDF and 20 MB total; native documents must be issued.
     * Success can mark native documents/proposals sent and advance negotiation substatus for
     * offer/invoice/contract. Invalid context/content or SMTP failure returns 400. No caller
     * replay receipt is supplied: inspect history before repeating an uncertain send.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
