import {
  ManagerFeaturesService,
  type ManagerFeatureSeriesMigrationCandidate,
} from "../../client";

export type FeatureSeriesMigrationCandidate =
  ManagerFeatureSeriesMigrationCandidate;

export const featureSeriesMigrationApi = {
  preview: () => ManagerFeaturesService.previewManagerFeatureSeriesMigration(),
  apply: (
    candidates: Pick<
      ManagerFeatureSeriesMigrationCandidate,
      "series_id" | "feature_id" | "candidate_token"
    >[],
  ) =>
    ManagerFeaturesService.applyManagerFeatureSeriesMigration({ candidates }),
};
