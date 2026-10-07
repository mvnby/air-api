/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_upload_manager_customer_contract } from '../models/Body_upload_manager_customer_contract';
import type { ManagerActionMessageResponse } from '../models/ManagerActionMessageResponse';
import type { ManagerCustomerContractCreatePayload } from '../models/ManagerCustomerContractCreatePayload';
import type { ManagerCustomerContractItemResponse } from '../models/ManagerCustomerContractItemResponse';
import type { ManagerCustomerContractListResponse } from '../models/ManagerCustomerContractListResponse';
import type { ManagerCustomerContractUpdatePayload } from '../models/ManagerCustomerContractUpdatePayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerContractsService {
    /**
     * Get Manager Customer Contracts
     * List active and archived open contracts for a customer owned by the current tenant, with
     * provider edit links. Missing or inaccessible customer returns 404. Reading does not
     * generate a contract.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param customerId
     * @returns ManagerCustomerContractListResponse Successful Response
     * @throws ApiError
     */
    public static getManagerCustomerContracts(
        customerId: number,
    ): CancelablePromise<ManagerCustomerContractListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/customers/{customer_id}/contracts',
            path: {
                'customer_id': customerId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Customer Contract
     * Generate a new open contract from the configured shared Google template for a
     * current-tenant company or individual entrepreneur. Copies the provider file and
     * substitutes current customer requisites; omitted number is allocated by the contract
     * service and omitted expiry defaults to one year. Missing customer returns 404;
     * unsupported party type or unavailable open-contract template returns 400. Repeating POST
     * creates another contract/file; no caller replay receipt is supplied.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param customerId
     * @param requestBody
     * @returns ManagerCustomerContractItemResponse Successful Response
     * @throws ApiError
     */
    public static createManagerCustomerContract(
        customerId: number,
        requestBody: ManagerCustomerContractCreatePayload,
    ): CancelablePromise<ManagerCustomerContractItemResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/customers/{customer_id}/contracts',
            path: {
                'customer_id': customerId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upload Manager Customer Contract
     * Upload an existing open-contract file to the configured Google provider and register it
     * for a current-tenant company or individual entrepreneur. Requires number, contract date,
     * expiry and a configured template marked as open contract. Missing customer returns 404;
     * unsupported party/template or invalid metadata returns 400. No caller replay receipt or
     * route-specific file-size limit is supplied; repeating POST can create another
     * file/record.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param customerId
     * @param formData
     * @returns ManagerCustomerContractItemResponse Successful Response
     * @throws ApiError
     */
    public static uploadManagerCustomerContract(
        customerId: number,
        formData: Body_upload_manager_customer_contract,
    ): CancelablePromise<ManagerCustomerContractItemResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/customers/{customer_id}/contracts/upload',
            path: {
                'customer_id': customerId,
            },
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Manager Customer Contract
     * Patch supplied metadata of an open contract belonging to the current-tenant customer.
     * Number/date/expiry/document-role changes also attempt placeholder replacement in its
     * Google file; this is not immutable native document versioning. Missing customer/contract
     * returns 404; empty number or unsupported status returns 400. No expected_version
     * precondition is provided.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param customerId
     * @param contractId
     * @param requestBody
     * @returns ManagerCustomerContractItemResponse Successful Response
     * @throws ApiError
     */
    public static patchManagerCustomerContract(
        customerId: number,
        contractId: number,
        requestBody: ManagerCustomerContractUpdatePayload,
    ): CancelablePromise<ManagerCustomerContractItemResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/customers/{customer_id}/contracts/{contract_id}',
            path: {
                'customer_id': customerId,
                'contract_id': contractId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Manager Customer Contract
     * Delete an open-contract record of the current-tenant customer, clear orders’ references
     * to it and attempt Google file deletion. Provider cleanup is best effort, so success does
     * not prove the remote file was removed. Missing customer/contract returns 404, including
     * a repeat after deletion. Archiving is the alternative when the record should remain.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param customerId
     * @param contractId
     * @returns ManagerActionMessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteManagerCustomerContract(
        customerId: number,
        contractId: number,
    ): CancelablePromise<ManagerActionMessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/customers/{customer_id}/contracts/{contract_id}',
            path: {
                'customer_id': customerId,
                'contract_id': contractId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Archive Manager Customer Contract
     * Mark an open contract of the current-tenant customer archived, retaining its file and
     * existing order references. Repeating archive sets the same state; no separate replay
     * receipt is supplied. Missing customer/contract returns 404. This does not delete or
     * regenerate the contract.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param customerId
     * @param contractId
     * @returns ManagerActionMessageResponse Successful Response
     * @throws ApiError
     */
    public static archiveManagerCustomerContract(
        customerId: number,
        contractId: number,
    ): CancelablePromise<ManagerActionMessageResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/customers/{customer_id}/contracts/{contract_id}/archive',
            path: {
                'customer_id': customerId,
                'contract_id': contractId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
