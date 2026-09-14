import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import FeatureEditorDrawer from "../src/components/features/FeatureEditorDrawer.vue";
import MediaField from "../src/components/MediaField.vue";
import { ManagerFeaturesService, type ManagerFeatureResponse } from "../src/client";

const universalFeature = (id: number): ManagerFeatureResponse => ({
  id,
  slug: `feature-${id}`,
  name: `Общая фича ${id}`,
  category: {
    id: 1,
    name: "Комфорт",
    slug: "comfort",
    sort_order: 0,
    is_active: true,
  },
  scope_type: "universal",
  is_active: true,
  sort_order: id * 10,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
});

describe("FeatureEditorDrawer", () => {
  it("uses the separate universal list for replacement and removes rules for a brand feature", async () => {
    const wrapper = mount(FeatureEditorDrawer, {
      props: {
        open: true,
        feature: {
          ...universalFeature(20),
          seo_title: "SEO title from AI",
          seo_description: "SEO description from AI",
          rules: [
            {
              spec_key: "inverter",
              operator: "exists",
              target_value: true,
              is_active: true,
              sort_order: 0,
            },
          ],
        },
        categories: [
          {
            id: 1,
            name: "Комфорт",
            slug: "comfort",
            sort_order: 0,
            is_active: true,
          },
        ],
        brands: [
          {
            id: 2,
            title: "TCL",
            slug: "tcl",
            is_published: true,
            sort_order: 0,
            created_at: "2026-01-01T00:00:00Z",
          },
        ],
        features: [universalFeature(10)],
      },
    });

    expect(wrapper.text()).toContain(
      "Автоматическое назначение по характеристикам",
    );
    const seoTitle = wrapper
      .findAll("label")
      .find((label) => label.text().includes("SEO title"));
    const seoDescription = wrapper
      .findAll("label")
      .find((label) => label.text().includes("SEO description"));
    expect(seoTitle?.find("input").element.value).toBe("SEO title from AI");
    expect(seoDescription?.find("textarea").element.value).toBe(
      "SEO description from AI",
    );
    const brandScopeButton = wrapper
      .findAll("button")
      .find((button) => button.text() === "Брендовая");
    await brandScopeButton?.trigger("click");

    expect(wrapper.text()).not.toContain(
      "Автоматическое назначение по характеристикам",
    );
    const replacementSelect = wrapper.findAll("select").at(-1);
    expect(replacementSelect?.text()).toContain("Общая фича 10");
    expect(replacementSelect?.text()).not.toContain("Общая фича 20");
  });

  it("keeps the selected media asset ids in the feature payload", async () => {
    const create = vi
      .spyOn(ManagerFeaturesService, "createManagerFeature")
      .mockResolvedValue(universalFeature(30));
    const wrapper = mount(FeatureEditorDrawer, {
      props: {
        open: true,
        feature: null,
        categories: [
          {
            id: 1,
            name: "Комфорт",
            slug: "comfort",
            sort_order: 0,
            is_active: true,
          },
        ],
        brands: [],
        features: [],
      },
    });
    await wrapper.find('input[required]').setValue("SVG фича");
    const fields = wrapper.findAllComponents(MediaField);
    const svgUrl = `https://cdn.mvn.by/library/original/${"a".repeat(64)}.svg`;
    const imageUrl = `https://cdn.mvn.by/library/original/${"b".repeat(64)}.webp`;
    fields[0]?.vm.$emit("update:modelValue", svgUrl);
    fields[0]?.vm.$emit("selected", { id: 41, url: svgUrl });
    fields[1]?.vm.$emit("update:modelValue", imageUrl);
    fields[1]?.vm.$emit("selected", { id: 42, url: imageUrl });
    await wrapper.vm.$nextTick();
    await wrapper.find("form").trigger("submit");

    expect(create).toHaveBeenCalledWith(
      expect.objectContaining({
        icon: svgUrl,
        icon_media_id: 41,
        image_url: imageUrl,
        image_media_id: 42,
      }),
    );
    create.mockRestore();
  });
});

describe("MediaField", () => {
  it("does not allow a raw URL to bypass the media library", () => {
    const wrapper = mount(MediaField, {
      props: { label: "Логотип", modelValue: "https://vendor.example/logo.svg" },
    });

    expect(wrapper.find('input[type="text"]').attributes("readonly")).toBeDefined();
  });
});
