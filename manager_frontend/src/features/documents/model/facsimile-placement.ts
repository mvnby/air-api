import type {
  DocumentFacsimilePdfPayload,
  DocumentFacsimilePreviewResponse,
  FacsimileImagePlacement,
  FacsimilePlacement as ApiFacsimilePlacement,
  FacsimilePreviewAsset,
  FacsimilePreviewPage,
} from '../../../client';

export type FacsimileKind = 'signature' | 'seal';
export type FacsimilePage = FacsimilePreviewPage;
export type FacsimileAsset = FacsimilePreviewAsset;
export type StampPlacement = FacsimileImagePlacement;
export type FacsimilePlacement = ApiFacsimilePlacement;
export type FacsimilePreview = DocumentFacsimilePreviewResponse;
export type FacsimileSave = DocumentFacsimilePdfPayload & { expected_signed_artifact_id: string | null };

export const stampRatio = (asset: FacsimileAsset) => asset.height_px / asset.width_px;
export const constrainStamp = (stamp: StampPlacement, page: FacsimilePage, asset: FacsimileAsset): StampPlacement => {
  const ratio = stampRatio(asset);
  const maxWidth = Math.min(page.width_mm, page.height_mm / ratio);
  const width = Math.min(maxWidth, Math.max(Math.min(5, maxWidth), stamp.width_mm));
  return {
    page_number: page.page_number,
    width_mm: width,
    x_mm: Math.max(0, Math.min(page.width_mm - width, stamp.x_mm)),
    y_mm: Math.max(0, Math.min(page.height_mm - width * ratio, stamp.y_mm)),
  };
};
export const pagePoint = (x: number, y: number, rect: Pick<DOMRect, 'left' | 'top' | 'width' | 'height'>, page: FacsimilePage) => ({
  x_mm: (x - rect.left) / rect.width * page.width_mm,
  y_mm: (y - rect.top) / rect.height * page.height_mm,
});
export const canEditDocumentFacsimile = (document: { status: string; artifacts?: Array<{ kind: string }> | null }) => (
  document.status === 'issued'
  || (['sent', 'signed'].includes(document.status) && !document.artifacts?.some((item) => item.kind === 'signed_pdf'))
);
export const facsimileSavePayload = (preview: FacsimilePreview, placement: FacsimilePlacement): FacsimileSave => ({
  source_checksum_sha256: preview.source_checksum_sha256,
  expected_signed_artifact_id: preview.signed_artifact_id,
  signature_asset_id: preview.signature.asset_id,
  seal_asset_id: preview.seal.asset_id,
  signature: { ...placement.signature },
  seal: { ...placement.seal },
});
