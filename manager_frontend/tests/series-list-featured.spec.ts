import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SeriesList from "../src/components/brands/SeriesList.vue";

const brand = {
  id: 1,
  title: "TCL",
  slug: "tcl",
  logo_url: null,
  description: null,
  short_description: null,
  sort_order: 0,
  is_published: true,
  products_count: 0,
};

const series = (overrides = {}) => ({
  id: 1,
  title: "Elite",
  slug: "elite",
  tagline: null,
  short_description: null,
  description: null,
  hero_image: null,
  gallery_images: [],
  brand_features: [],
  content_blocks: [],
  footnotes: [],
  seo_title: null,
  seo_description: null,
  source_url: null,
  is_published: true,
  is_featured: false,
  products_count: 0,
  ...overrides,
});

const mountList = (item = series()) =>
  mount(SeriesList, {
    props: {
      brand,
      items: [item],
      loading: false,
      error: "",
      reordering: false,
      reorderDisabled: false,
      featuredSeriesId: null,
      draggedId: null,
      dropTargetId: null,
      expandedIds: new Set(),
    },
  });

describe("SeriesList featured toggle", () => {
  it("toggles a published series directly", async () => {
    const item = series();
    const wrapper = mountList(item);

    await wrapper.get("button[title='Добавить в подборку']").trigger("click");

    expect(wrapper.emitted("toggleFeatured")?.[0]).toEqual([item]);
  });

  it("does not let a draft series enter the selection", () => {
    const wrapper = mountList(series({ is_published: false }));

    expect(wrapper.get("button[title='Сначала опубликуйте серию']").attributes("disabled")).toBeDefined();
  });

  it("lets a selected draft series leave the selection", async () => {
    const item = series({ is_published: false, is_featured: true });
    const wrapper = mountList(item);

    const button = wrapper.get("button[title='Убрать из подборки']");
    expect(button.attributes("disabled")).toBeUndefined();
    await button.trigger("click");
    expect(wrapper.emitted("toggleFeatured")?.[0]).toEqual([item]);
  });
});
