import { ApiError } from '../client/core/ApiError';
import type { SupplierOfferCandidateResponse } from '../client/models/SupplierOfferCandidateResponse';
import type { SupplierOfferMappingPutPayload } from '../client/models/SupplierOfferMappingPutPayload';
import { ManagerService } from '../client/services/ManagerService';

export type SupplierOfferCandidate = SupplierOfferCandidateResponse;

export const isSupplierOffersConflict = (error: unknown): boolean => (
  error instanceof ApiError && error.status === 409
);

export const productSupplierOffersApi = {
  listCandidates(productId: number, filters: {
    supplierId: number;
    sourceId?: number | null;
    q?: string;
    page?: number;
    limit?: number;
  }) {
    return ManagerService.listProductSupplierOfferCandidates(
      productId,
      filters.supplierId,
      filters.sourceId,
      filters.q?.trim() || null,
      filters.page || 1,
      filters.limit || 25,
    );
  },
  map(offerId: number, payload: SupplierOfferMappingPutPayload) {
    return ManagerService.putSupplierOfferMapping(offerId, payload);
  },
};

export const supplierMappingApi = {
  listUnmapped(page: number, limit: number, filters: {
    supplierId?: number;
    sourceId?: number;
    q?: string;
  }) {
    return ManagerService.listUnmappedSupplierOffers(
      page,
      limit,
      filters.supplierId ?? null,
      filters.sourceId ?? null,
      filters.q?.trim() || null,
    );
  },
};
