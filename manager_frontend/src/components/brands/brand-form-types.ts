import type { FeatureAssignment } from "./SeriesFeatureAssignments.vue";

export type BrandForm = {
  title: string;
  slug: string;
  logo_url: string;
  description: string;
  sort_order: number;
  is_published: boolean;
};

export type SeriesContentBlockForm = {
  kind: "text" | "image_text" | "media";
  title: string;
  text: string;
  image_url: string;
  layout: "text_left" | "text_right" | "full";
};

export type SeriesForm = {
  title: string;
  slug: string;
  tagline: string;
  short_description: string;
  description: string;
  hero_image: string;
  galleryImages: string[];
  feature_assignments: FeatureAssignment[];
  contentBlocks: SeriesContentBlockForm[];
  footnotesText: string;
  seo_title: string;
  seo_description: string;
  source_url: string;
  sort_order: number;
  is_published: boolean;
};
