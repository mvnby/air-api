import type { Product } from '../api';

export type ProductWorkspaceSection = 'main' | 'media' | 'specifications' | 'suppliers' | 'publication' | 'relations';

export type ProductListWorkspaceContext = {
  returnTo: string;
  productIds: number[];
  currentProductId: number;
  scrollTop: number;
  page: number;
  listState: Record<string, unknown>;
};

export const PRODUCT_WORKSPACE_CONTEXT_KEY = 'manager:products:workspace-context:v1';

const sectionPath: Record<ProductWorkspaceSection, string> = {
  main: '',
  media: '/media',
  specifications: '/specifications',
  suppliers: '/suppliers',
  publication: '/publication',
  relations: '/relations',
};

export const buildProductWorkspacePath = (
  productId: number,
  section: ProductWorkspaceSection = 'main',
): string => `/manager/products/${productId}${sectionPath[section]}`;

export const parseProductWorkspaceLocation = (pathname: string): {
  productId: number | null;
  section: ProductWorkspaceSection;
} => {
  const match = pathname.match(/^\/manager\/products\/(\d+)(?:\/(media|specifications|suppliers|publication|relations))?\/?$/);
  if (!match) return { productId: null, section: 'main' };
  const productId = Number(match[1]);
  return {
    productId: Number.isInteger(productId) && productId > 0 ? productId : null,
    section: (match[2] || 'main') as ProductWorkspaceSection,
  };
};

export const getProductImageUrls = (product: Pick<Product, 'main_image' | 'gallery_images'>): string[] => {
  const urls = [
    product.main_image,
    ...product.gallery_images.map((image) => image.url),
  ]
    .map((value) => String(value || '').trim())
    .filter(Boolean);
  return Array.from(new Set(urls));
};

export const getProductImageCount = (product: Pick<Product, 'main_image' | 'gallery_images'>): number => (
  getProductImageUrls(product).length
);

export const getProductWorkspaceNeighbors = (
  productIds: number[],
  currentProductId: number,
): { previousId: number | null; nextId: number | null } => {
  const index = productIds.indexOf(currentProductId);
  if (index < 0) return { previousId: null, nextId: null };
  return {
    previousId: index > 0 ? (productIds[index - 1] ?? null) : null,
    nextId: index < productIds.length - 1 ? (productIds[index + 1] ?? null) : null,
  };
};

export const saveProductWorkspaceContext = (context: ProductListWorkspaceContext): void => {
  window.sessionStorage.setItem(PRODUCT_WORKSPACE_CONTEXT_KEY, JSON.stringify(context));
};

export const loadProductWorkspaceContext = (): ProductListWorkspaceContext | null => {
  try {
    const raw = window.sessionStorage.getItem(PRODUCT_WORKSPACE_CONTEXT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ProductListWorkspaceContext>;
    const productIds = Array.isArray(parsed.productIds)
      ? parsed.productIds.map(Number).filter((id) => Number.isInteger(id) && id > 0)
      : [];
    const currentProductId = Number(parsed.currentProductId);
    if (!parsed.returnTo || !Number.isInteger(currentProductId) || currentProductId <= 0) return null;
    return {
      returnTo: String(parsed.returnTo),
      productIds,
      currentProductId,
      scrollTop: Math.max(0, Number(parsed.scrollTop) || 0),
      page: Math.max(1, Number(parsed.page) || 1),
      listState: parsed.listState && typeof parsed.listState === 'object' ? parsed.listState : {},
    };
  } catch {
    return null;
  }
};
