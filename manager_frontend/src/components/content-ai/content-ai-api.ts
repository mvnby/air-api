import {
  ManagerContentAiService,
  type BrandShortDescriptionDraft,
  type BrandShortDescriptionDraftRequest,
  type FeatureContentDraft,
  type FeatureContentDraftRequest,
  type ProductSeriesContentDraft,
  type ProductSeriesContentDraftRequest,
} from "../../client";

export type DraftMode = FeatureContentDraftRequest["mode"];
export type SeriesContentDraft = ProductSeriesContentDraft;
export type {
  BrandShortDescriptionDraft,
  BrandShortDescriptionDraftRequest,
  FeatureContentDraft,
};

export const contentAiApi = {
  featureDraft: (payload: FeatureContentDraftRequest) =>
    ManagerContentAiService.createManagerFeatureContentAiDraft(payload),
  seriesDraft: (payload: ProductSeriesContentDraftRequest) =>
    ManagerContentAiService.createManagerSeriesContentAiDraft(payload),
  brandShortDescriptionDraft: (payload: BrandShortDescriptionDraftRequest) =>
    ManagerContentAiService.createManagerBrandShortDescriptionAiDraft(payload),
};
