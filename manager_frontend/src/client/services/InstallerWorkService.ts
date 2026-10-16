/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InstallerWorkDetail } from '../models/InstallerWorkDetail';
import type { InstallerWorksResponse } from '../models/InstallerWorksResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class InstallerWorkService {
    /**
     * List Works
     * Read only the actor's live explicit work assignments in the selected company/site.
     *
     * Active account, actual membership, worker profile, assignment and work lifecycle
     * are rechecked. Payroll-only or historical links never grant access. Date filters
     * precede count/pagination; limit is at most 100. Financial/private CRM fields are
     * absent. See https://github.com/mvnby/air-api/blob/main/docs/installer-workspace.md.
     * @param page
     * @param limit
     * @param bucket
     * @returns InstallerWorksResponse Successful Response
     * @throws ApiError
     */
    public static listInstallerWorks(
        page: number = 1,
        limit: number = 50,
        bucket: string = 'all',
    ): CancelablePromise<InstallerWorksResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/installer/works',
            query: {
                'page': page,
                'limit': limit,
                'bucket': bucket,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Read Work
     * Read a live assigned task with approved instructions, technical equipment and materials.
     *
     * Missing, revoked, foreign-company/site or inactive work returns404. No raw order
     * comments, quotes, payment ledger, supplier, purchase price or cost is returned.
     * Collection amount is visible only to the designated recipient while its financial
     * snapshot is current. See the installer-workspace domain contract.
     * @param assignmentId
     * @returns InstallerWorkDetail Successful Response
     * @throws ApiError
     */
    public static getInstallerWork(
        assignmentId: number,
    ): CancelablePromise<InstallerWorkDetail> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/installer/works/{assignment_id}',
            path: {
                'assignment_id': assignmentId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Read Material
     * Proxy explicitly published technical bytes after live assignment/link checks.
     *
     * ACL is rechecked after storage I/O. No bearer/presigned URL is issued, caching is
     * disabled and conditional304 cannot bypass authorization. Archived, unpublished,
     * revoked or foreign materials return404. Original filenames/source metadata are
     * never exposed; only approved image/PDF media are allowed.
     * @param assignmentId
     * @param materialId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static readInstallerWorkMaterial(
        assignmentId: number,
        materialId: number,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/installer/works/{assignment_id}/materials/{material_id}/content',
            path: {
                'assignment_id': assignmentId,
                'material_id': materialId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
