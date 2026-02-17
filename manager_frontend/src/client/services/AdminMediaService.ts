/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_upload_images_admin_api_upload_images_post } from '../models/Body_upload_images_admin_api_upload_images_post';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AdminMediaService {
    /**
     * Upload Images
     * Bulk upload images for articles/products.
     * Returns list of web-accessible URLs.
     * @param formData
     * @returns any Successful Response
     * @throws ApiError
     */
    public static uploadImagesAdminApiUploadImagesPost(
        formData: Body_upload_images_admin_api_upload_images_post,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/admin/api/upload_images',
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Article Images
     * List all images associated with an article slug.
     * @param slug
     * @returns any Successful Response
     * @throws ApiError
     */
    public static listArticleImagesAdminApiArticleImagesSlugGet(
        slug: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/admin/api/article_images/{slug}',
            path: {
                'slug': slug,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
