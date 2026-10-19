import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

import FeatureEditorDrawer from "../src/components/features/FeatureEditorDrawer.vue";
import MediaField from "../src/components/MediaField.vue";
import { ManagerFeaturesService, type ManagerFeatureResponse } from "../src/client";
import { api } from "../src/api";
import CatalogFeatureIconPicker from "../src/components/features/CatalogFeatureIconPicker.vue";
import FeaturePresentationPreview from "../src/components/features/FeaturePresentationPreview.vue";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

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

  it("saves the icon caption and applies all three previews without duplicating descriptions", async () => {
    const update = vi.spyOn(ManagerFeaturesService, "updateManagerFeature").mockResolvedValue(universalFeature(30));
    const wrapper = mount(FeatureEditorDrawer, {
      props: {
        open: true,
        feature: {
          ...universalFeature(30),
          icon_caption: "Старое пояснение",
          short_description: "Коротко об управлении",
          full_description: "Подробное описание управления и режимов",
          image_url: "https://cdn.mvn.by/library/original/illustration.webp",
        },
        categories: [universalFeature(30).category],
        brands: [],
        features: [],
      },
    });
    const caption = wrapper.findAll("label").find((label) => label.text().includes("Подпись к иконке"))!.find("input");
    expect(caption.attributes("maxlength")).toBe("160");
    expect(caption.element.value).toBe("Старое пояснение");
    await caption.setValue("  Управление со смартфона  ");

    const iconPreview = wrapper.get('[data-feature-preview="icon"]');
    expect(iconPreview.text()).toContain("Управление со смартфона");
    expect(iconPreview.text()).not.toContain("Подробное описание");
    const compactPreview = wrapper.get('[data-feature-preview="compact"]');
    expect(compactPreview.text()).toContain("Коротко об управлении");
    expect(compactPreview.text()).not.toContain("Подробное описание");
    const detailedPreview = wrapper.get('[data-feature-preview="detailed"]');
    expect(detailedPreview.text()).toContain("Подробное описание управления и режимов");
    expect(detailedPreview.get('img[alt="Общая фича 30"]').attributes("src")).toContain("illustration.webp");

    await wrapper.find("form").trigger("submit");
    expect(update).toHaveBeenCalledWith(30, expect.objectContaining({ icon_caption: "Управление со смартфона" }));
  });

  it("uses the immutable media URL and id after choosing a Kitlane icon", async () => {
    const create = vi.spyOn(ManagerFeaturesService, "createManagerFeature").mockResolvedValue(universalFeature(30));
    const wrapper = mount(FeatureEditorDrawer, {
      props: { open: true, feature: null, categories: [universalFeature(1).category], brands: [], features: [] },
    });
    await wrapper.get('input[required]').setValue("Wi-Fi");
    const picker = wrapper.getComponent(CatalogFeatureIconPicker);
    picker.vm.$emit("busy", true);
    await wrapper.vm.$nextTick();
    expect(wrapper.get('button[type="submit"]').attributes("disabled")).toBeDefined();
    await wrapper.get("form").trigger("submit");
    expect(create).not.toHaveBeenCalled();

    const iconUrl = `https://cdn.mvn.by/library/original/${"c".repeat(64)}.svg`;
    picker.vm.$emit("selected", { id: 43, url: iconUrl });
    picker.vm.$emit("busy", false);
    await wrapper.vm.$nextTick();
    await wrapper.get("form").trigger("submit");
    expect(create).toHaveBeenCalledWith(expect.objectContaining({ icon: iconUrl, icon_media_id: 43 }));
  });
});

describe("FeaturePresentationPreview", () => {
  it("falls back from caption to short description to name and ignores legacy semantic icon names", async () => {
    const wrapper = mount(FeaturePresentationPreview, { props: { feature: { name: "Wi-Fi", icon: "wifi", short_description: "Управление со смартфона" } } });
    expect(wrapper.get('[data-feature-preview="icon"]').text()).toContain("Управление со смартфона");
    expect(wrapper.findAll("img")).toHaveLength(0);
    await wrapper.setProps({ feature: { name: "Wi-Fi", icon_caption: "  ", short_description: "  " } });
    expect(wrapper.get('[data-feature-preview="icon"]').text()).toContain("Wi-Fi");
  });
});

describe("CatalogFeatureIconPicker", () => {
  it("imports the chosen SVG through the shared media library before emitting it", async () => {
    const iconUrl = `https://cdn.mvn.by/library/original/${"d".repeat(64)}.svg`;
    const asset = {
      id: 55,
      title: "wifi.svg",
      kind: "feature",
      variant_type: "original",
      url: iconUrl,
      mime_type: "image/svg+xml",
      storage_provider: "r2",
      processing_status: "ready",
      created_at: "2026-10-19T00:00:00Z",
      updated_at: "2026-10-19T00:00:00Z",
    };
    const upload = vi.spyOn(api, "uploadMediaAssets").mockResolvedValue({ uploaded: 1, items: [asset] });
    const fetchIcon = vi.fn().mockResolvedValue({ ok: true, headers: new Headers({ "content-type": "image/svg+xml" }), blob: async () => new Blob(["<svg/>"]) });
    vi.stubGlobal("fetch", fetchIcon);
    const wrapper = mount(CatalogFeatureIconPicker);

    expect(wrapper.findAll("button")).toHaveLength(12);
    await wrapper.get('button[aria-label="Выбрать иконку: Wi-Fi"]').trigger("click");
    await flushPromises();

    expect(fetchIcon).toHaveBeenCalledWith("/manager/assets/catalog-feature-icons/wifi.svg");
    expect(upload).toHaveBeenCalledWith(expect.objectContaining({ files: [expect.any(File)], kind: "feature" }));
    expect(upload.mock.calls[0]?.[0].files?.[0]?.type).toBe("image/svg+xml");
    expect(wrapper.emitted("selected")).toEqual([[asset]]);
    expect(wrapper.emitted("busy")).toEqual([[true], [false]]);
  });

  it("keeps the existing choice when a bundle request returns the SPA shell", async () => {
    const upload = vi.spyOn(api, "uploadMediaAssets");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, headers: new Headers({ "content-type": "text/html" }) }));
    const wrapper = mount(CatalogFeatureIconPicker);
    await wrapper.get('button[aria-label="Выбрать иконку: Wi-Fi"]').trigger("click");
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toContain("Не удалось открыть иконку");
    expect(upload).not.toHaveBeenCalled();
    expect(wrapper.emitted("selected")).toBeUndefined();
    expect(wrapper.get('button[aria-label="Выбрать иконку: Wi-Fi"]').attributes("disabled")).toBeUndefined();
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
