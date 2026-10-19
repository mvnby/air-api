import { OpenAPI } from '../client/core/OpenAPI';
import { request } from '../client/core/request';

export type CatalogDocumentTarget = 'brand' | 'series' | 'product';
export type CatalogDocumentKind = 'catalog' | 'operation' | 'installation' | 'service' | 'brochure' | 'certificate' | 'other';
export type CatalogDocumentInput = {
  title: string;
  url: string;
  kind: CatalogDocumentKind;
  source_url: string | null;
  language: string | null;
  year: number | null;
  visibility: 'public' | 'internal';
  inherit_to_products: boolean;
};
export type CatalogDocument = CatalogDocumentInput & {
  id: number;
  origin_type: CatalogDocumentTarget;
  origin_id: number;
  origin_title: string;
  inherited: boolean;
};
export type CatalogDocumentWorkspace = {
  own: CatalogDocument[];
  inherited: CatalogDocument[];
  effective: CatalogDocument[];
};

export const catalogDocumentsApi = {
  get(targetType: CatalogDocumentTarget, targetId: number) {
    return request<CatalogDocumentWorkspace>(OpenAPI, {
      method: 'GET', url: '/api/manager/catalog-documents/{target_type}/{target_id}',
      path: { target_type: targetType, target_id: targetId },
    });
  },
  replace(targetType: CatalogDocumentTarget, targetId: number, documents: CatalogDocumentInput[]) {
    return request<CatalogDocumentWorkspace>(OpenAPI, {
      method: 'PUT', url: '/api/manager/catalog-documents/{target_type}/{target_id}',
      path: { target_type: targetType, target_id: targetId }, body: { documents }, mediaType: 'application/json',
    });
  },
  upload(targetType: CatalogDocumentTarget, targetId: number, file: File) {
    return request<{ url: string; title: string }>(OpenAPI, {
      method: 'POST', url: '/api/manager/catalog-documents/{target_type}/{target_id}/upload',
      path: { target_type: targetType, target_id: targetId }, formData: { file },
    });
  },
};
