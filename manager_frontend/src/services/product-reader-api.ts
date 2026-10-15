import { ManagerTenantCatalogService, type ManagerTenantCatalogProductDetailResponse } from '../client';

export type ProductReaderDetail = ManagerTenantCatalogProductDetailResponse;

export const productReaderApi = {
  detail(productId: number): Promise<ProductReaderDetail> {
    return ManagerTenantCatalogService.getManagerTenantCatalogProduct(productId);
  },
};

/** Only navigable web URLs; never execute imported catalog content. */
export const productReaderUrl = (value: string | null | undefined): string | null => {
  if (!value?.trim()) return null;
  try {
    const url = new URL(value, window.location.origin);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
};
