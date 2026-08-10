import { mount, shallowMount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

vi.mock("../src/components/content-ai/content-ai-api", () => ({
  contentAiApi: { seriesDraft: vi.fn() },
}));
vi.mock("../src/services/ui-feedback", () => ({
  confirmDialog: vi.fn().mockResolvedValue(false),
}));

import SeriesContentAiActions from "../src/components/brands/SeriesContentAiActions.vue";
import SeriesEditorModal from "../src/components/brands/SeriesEditorModal.vue";

describe("SeriesContentAiActions", () => {
  it("does not send an incomplete from-source request", async () => {
    const wrapper = mount(SeriesContentAiActions, {
      props: {
        sourceUrl: "",
        description: "",
        title: "Elite",
        brandName: "TCL",
      },
    });
    await wrapper.findAll("button")[0]?.trigger("click");
    expect(wrapper.text()).toContain("Сначала укажите источник.");
    expect(wrapper.emitted("draft")).toBeUndefined();
  });

  it("does not send a polish request without text", async () => {
    const wrapper = mount(SeriesContentAiActions, {
      props: { sourceUrl: "", description: " ", title: "Elite" },
    });
    await wrapper.findAll("button")[1]?.trigger("click");
    expect(wrapper.text()).toContain("Сначала вставьте описание серии.");
  });

  it("asks before replacing a populated short description even when full text is empty", async () => {
    const wrapper = mount(SeriesContentAiActions, {
      props: {
        sourceUrl: "https://example.test/series",
        description: "",
        title: "Elite",
        hasExistingContent: true,
      },
    });
    await wrapper.findAll("button")[0]?.trigger("click");
    expect(wrapper.emitted("draft")).toBeUndefined();
  });

  it("applies server AI SEO fields and has no local prompt actions", async () => {
    const form = {
      title: "Elite",
      slug: "elite",
      tagline: "",
      short_description: "",
      description: "",
      hero_image: "",
      galleryImages: [],
      feature_assignments: [],
      contentBlocks: [],
      footnotesText: "",
      seo_title: "",
      seo_description: "",
      source_url: "",
      sort_order: 0,
      is_published: true,
    };
    const wrapper = shallowMount(SeriesEditorModal, {
      props: {
        open: true,
        form,
        editing: true,
        features: [],
        featuresLoading: false,
        saving: false,
        galleryApplying: false,
      },
    });

    wrapper.findComponent(SeriesContentAiActions).vm.$emit("draft", {
      tagline: "Тихая серия",
      short_description: "Кратко",
      description: "Полное описание",
      seo_title: "TCL Elite — тихое охлаждение",
      seo_description: "Серия TCL Elite для тихого охлаждения дома.",
      prompt_version: "series-v1",
    });
    await wrapper.vm.$nextTick();

    expect(form.seo_title).toBe("TCL Elite — тихое охлаждение");
    expect(form.seo_description).toBe(
      "Серия TCL Elite для тихого охлаждения дома.",
    );
    expect(wrapper.text()).not.toContain("SEO из контента");
    expect(wrapper.text()).not.toContain("Промпт для AI");
  });

  it("shows a series save error inside the open editor", () => {
    const wrapper = shallowMount(SeriesEditorModal, {
      props: {
        open: true,
        form: {
          title: "Elite",
          slug: "elite",
          tagline: "",
          short_description: "",
          description: "",
          hero_image: "",
          galleryImages: [],
          feature_assignments: [],
          contentBlocks: [],
          footnotesText: "",
          seo_title: "",
          seo_description: "",
          source_url: "",
          sort_order: 0,
          is_published: true,
        },
        editing: true,
        features: [],
        featuresLoading: false,
        saving: false,
        galleryApplying: false,
        error: "Фичи недоступны этой серии: 40",
      },
    });

    expect(wrapper.get('[role="alert"]').text()).toBe(
      "Фичи недоступны этой серии: 40",
    );
  });
});
