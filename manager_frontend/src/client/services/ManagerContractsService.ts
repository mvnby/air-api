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
