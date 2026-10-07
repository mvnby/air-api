/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InstallationLegacyComparisonResponse } from '../models/InstallationLegacyComparisonResponse';
import type { InstallationPublishResponse } from '../models/InstallationPublishResponse';
import type { ManagerActionMessageResponse } from '../models/ManagerActionMessageResponse';
import type { ManagerQuickTariffListResponse } from '../models/ManagerQuickTariffListResponse';
import type { ManagerTariffCreatePayload } from '../models/ManagerTariffCreatePayload';
import type { ManagerTariffListResponse } from '../models/ManagerTariffListResponse';
import type { ManagerTariffResponse } from '../models/ManagerTariffResponse';
import type { ManagerTariffRuleCreatePayload } from '../models/ManagerTariffRuleCreatePayload';
import type { ManagerTariffRuleListResponse } from '../models/ManagerTariffRuleListResponse';
import type { ManagerTariffRuleResponse } from '../models/ManagerTariffRuleResponse';
import type { ManagerTariffRuleUpdatePayload } from '../models/ManagerTariffRuleUpdatePayload';
import type { ManagerTariffServiceKind } from '../models/ManagerTariffServiceKind';
import type { ManagerTariffUpdatePayload } from '../models/ManagerTariffUpdatePayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerTariffsService {
    /**
     * Publish Manager Installation Price Book
     * Validate active typed installation drafts and atomically publish an immutable tenant
     * price-book revision under the publication lock. Invalid/empty pricing, conflicting codes
     * or equally specific matchers, incompatible historical matcher/component identity or
     * invalid required prices return 422 without publication. An unchanged fingerprint reuses
     * the current revision. New publication changes future resolution and retires legacy
     * installation-rate/estimate writes; accepted estimates and documents retain their
     * snapshots.
     *
     * Access and scope: Manager access is required; service catalog data belongs to the
     * authenticated tenant, independently of storefront. The system tenant also reads legacy
     * rows with NULL tenant ownership. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
     * @returns InstallationPublishResponse Successful Response
     * @throws ApiError
     */
    public static publishManagerInstallationPriceBook(): CancelablePromise<InstallationPublishResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/tariffs/price-book/publish',
        });
    }
    /**
     * List Manager Installation Legacy Comparison
     * Read a paginated comparison of legacy installation tariff data for review, using offset
     * and limit 1–100. This report does not migrate prices, repair drafts, publish a book or
     * rewrite accepted estimates.
     *
     * Access and scope: Manager access is required; service catalog data belongs to the
     * authenticated tenant, independently of storefront. The system tenant also reads legacy
     * rows with NULL tenant ownership. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
     * @param offset
     * @param limit
     * @returns InstallationLegacyComparisonResponse Successful Response
     * @throws ApiError
     */
    public static listManagerInstallationLegacyComparison(
        offset?: number,
        limit: number = 100,
    ): CancelablePromise<InstallationLegacyComparisonResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/tariffs/price-book/legacy-comparison',
            query: {
                'offset': offset,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Manager Tariffs
     * Read the tenant’s service tariff drafts, optionally by service kind; inactive entries
     * are included by default. This route is unpaginated. Draft amounts may differ from the
     * active immutable installation price book and do not themselves define its current
     * resolver.
     *
     * Access and scope: Manager access is required; service catalog data belongs to the
     * authenticated tenant, independently of storefront. The system tenant also reads legacy
     * rows with NULL tenant ownership. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
     * @param serviceKind
     * @param includeInactive
     * @returns ManagerTariffListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerTariffs(
        serviceKind?: (ManagerTariffServiceKind | null),
        includeInactive: boolean = true,
    ): CancelablePromise<ManagerTariffListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/tariffs',
            query: {
                'service_kind': serviceKind,
                'include_inactive': includeInactive,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Tariff
     * Create a tenant service tariff draft with its calculation/matching and price fields.
     * Required nonblank short name is validated; included route length is reset to zero for
     * service kinds that do not support it. This does not publish an installation price book.
     * No idempotency receipt exists, so repeated creation can add another draft.
     *
     * Access and scope: Manager access is required; service catalog data belongs to the
     * authenticated tenant, independently of storefront. The system tenant also reads legacy
     * rows with NULL tenant ownership. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
     * @param requestBody
     * @returns ManagerTariffResponse Successful Response
     * @throws ApiError
     */
    public static createManagerTariff(
        requestBody: ManagerTariffCreatePayload,
    ): CancelablePromise<ManagerTariffResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/tariffs',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Manager Quick Tariffs
     * Read bounded quick-add service suggestions with optional text filter and limit 1–100.
     * These combine active ordinary draft tariffs and fixed published installation standards;
     * after book publication legacy installation drafts are excluded. Published standards may
     * have no legacy tariff_id. Suggestions for free commercial rows do not confirm an
     * installation estimate or establish equipment identity.
     *
     * Access and scope: Manager access is required; service catalog data belongs to the
     * authenticated tenant, independently of storefront. The system tenant also reads legacy
     * rows with NULL tenant ownership. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
     * @param q
     * @param serviceKind
     * @param limit
     * @returns ManagerQuickTariffListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerQuickTariffs(
        q: string = '',
        serviceKind?: (ManagerTariffServiceKind | null),
        limit: number = 10,
    ): CancelablePromise<ManagerQuickTariffListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/tariffs/quick-add',
            query: {
                'q': q,
                'service_kind': serviceKind,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Manager Tariff
     * Update only submitted tariff draft fields. Missing/out-of-scope tariff returns 404 and
     * blank short name fails validation. Included route length is reset to zero when
     * incompatible with the service kind. Changes take effect in the draft dictionary;
     * published installation pricing and accepted estimate snapshots remain unchanged until a
     * separate successful publication.
     *
     * Access and scope: Manager access is required; service catalog data belongs to the
     * authenticated tenant, independently of storefront. The system tenant also reads legacy
     * rows with NULL tenant ownership. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
     * @param tariffId
     * @param requestBody
     * @returns ManagerTariffResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerTariff(
        tariffId: number,
        requestBody: ManagerTariffUpdatePayload,
    ): CancelablePromise<ManagerTariffResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/tariffs/{tariff_id}',
            path: {
                'tariff_id': tariffId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Manager Tariff
     * Permanently delete a tenant tariff draft. Missing/out-of-scope tariff returns 404,
     * including repeats. This is not publication of a replacement price book; existing
     * immutable published installation data is not rewritten.
     *
     * Access and scope: Manager access is required; service catalog data belongs to the
     * authenticated tenant, independently of storefront. The system tenant also reads legacy
     * rows with NULL tenant ownership. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
     * @param tariffId
     * @returns ManagerActionMessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteManagerTariff(
        tariffId: number,
    ): CancelablePromise<ManagerActionMessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/tariffs/{tariff_id}',
            path: {
                'tariff_id': tariffId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Manager Favorite Tariff Rules
     * Read favorite draft rules for the required service kind, optionally excluding one
     * tariff. Inactive rules are excluded by default and the result is unpaginated. These are
     * reusable draft options, not accepted estimate components or automatically attached order
     * lines.
     *
     * Access and scope: Manager access is required; service catalog data belongs to the
     * authenticated tenant, independently of storefront. The system tenant also reads legacy
     * rows with NULL tenant ownership. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
     * @param serviceKind
     * @param includeInactive
     * @param excludeTariffId
     * @returns ManagerTariffRuleListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerFavoriteTariffRules(
        serviceKind: ManagerTariffServiceKind,
        includeInactive: boolean = false,
        excludeTariffId?: (number | null),
    ): CancelablePromise<ManagerTariffRuleListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/tariffs/rules/favorites',
            query: {
                'service_kind': serviceKind,
                'include_inactive': includeInactive,
                'exclude_tariff_id': excludeTariffId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Manager Tariff Rules
     * Read draft rules belonging to one tenant tariff; inactive rules are included by default
     * and no pagination is accepted. Missing/out-of-scope tariff returns 404. This does not
     * select a rule into an estimate or publish installation components.
     *
     * Access and scope: Manager access is required; service catalog data belongs to the
     * authenticated tenant, independently of storefront. The system tenant also reads legacy
     * rows with NULL tenant ownership. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
     * @param tariffId
     * @param includeInactive
     * @returns ManagerTariffRuleListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerTariffRules(
        tariffId: number,
        includeInactive: boolean = true,
    ): CancelablePromise<ManagerTariffRuleListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/tariffs/{tariff_id}/rules',
            path: {
                'tariff_id': tariffId,
            },
            query: {
                'include_inactive': includeInactive,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Tariff Rule
     * Create a rule under a tenant tariff; missing parent returns 404. An existing rule with
     * matching semantic fields is reused, and a requested favorite flag may promote it to
     * favorite. This deduplication does not apply every submitted field to an existing rule
     * and is not an idempotency receipt. Changes remain draft data until a separate
     * installation price-book publication.
     *
     * Access and scope: Manager access is required; service catalog data belongs to the
     * authenticated tenant, independently of storefront. The system tenant also reads legacy
     * rows with NULL tenant ownership. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
     * @param tariffId
     * @param requestBody
     * @returns ManagerTariffRuleResponse Successful Response
     * @throws ApiError
     */
    public static createManagerTariffRule(
        tariffId: number,
        requestBody: ManagerTariffRuleCreatePayload,
    ): CancelablePromise<ManagerTariffRuleResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/tariffs/{tariff_id}/rules',
            path: {
                'tariff_id': tariffId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Manager Tariff Rule
     * Update submitted draft-rule fields after cleaning text. Missing/out-of-scope tariff or
     * rule belonging to another tariff returns 404. This edits the draft component definition
     * without modifying current published installation entries or saved estimate snapshots.
     *
     * Access and scope: Manager access is required; service catalog data belongs to the
     * authenticated tenant, independently of storefront. The system tenant also reads legacy
     * rows with NULL tenant ownership. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
     * @param tariffId
     * @param ruleId
     * @param requestBody
     * @returns ManagerTariffRuleResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerTariffRule(
        tariffId: number,
        ruleId: number,
        requestBody: ManagerTariffRuleUpdatePayload,
    ): CancelablePromise<ManagerTariffRuleResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/tariffs/{tariff_id}/rules/{rule_id}',
            path: {
                'tariff_id': tariffId,
                'rule_id': ruleId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Manager Tariff Rule
     * Permanently remove a draft rule from its tenant tariff. Missing/out-of-scope parent or
     * rule returns 404, including repeats. Current immutable price-book revisions and accepted
     * installation snapshots are not rewritten.
     *
     * Access and scope: Manager access is required; service catalog data belongs to the
     * authenticated tenant, independently of storefront. The system tenant also reads legacy
     * rows with NULL tenant ownership. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
     * @param tariffId
     * @param ruleId
     * @returns ManagerActionMessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteManagerTariffRule(
        tariffId: number,
        ruleId: number,
    ): CancelablePromise<ManagerActionMessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/tariffs/{tariff_id}/rules/{rule_id}',
            path: {
                'tariff_id': tariffId,
                'rule_id': ruleId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
