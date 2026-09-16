import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ProductCollectionPlacementsEditor from "../src/components/product-collections/ProductCollectionPlacementsEditor.vue";
import {
  articleCollectionSnippet,
  placementDateForInput,
} from "../src/components/product-collections/product-collection-placements";

const placement = (overrides = {}) => ({
  surface_key: "home",
  slot_key: "product_of_day",
  is_enabled: true,
  position: 7,
  display_mode: "single" as const,
  rotation_mode: "daily" as const,
  grid_columns: 3,
  item_limit: 8,
  ...overrides,
});

describe("collection placement editing", () => {
  it("toggles visibility directly without losing rendering or schedule fields", async () => {
    const original = placement({ starts_at: "2026-09-20T09:00:00Z" });
    const wrapper = mount(ProductCollectionPlacementsEditor, {
      props: { modelValue: [original] },
    });
    await wrapper.get('[role="switch"]').trigger("click");
    expect(wrapper.emitted("update:modelValue")?.[0]?.[0]).toEqual([
      { ...original, is_enabled: false },
    ]);
    expect(original.is_enabled).toBe(true);
  });

  it("clears incompatible rotation when switching away from a single product", async () => {
    const wrapper = mount(ProductCollectionPlacementsEditor, {
      props: { modelValue: [placement()] },
    });
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Сетка")!
      .trigger("click");
    expect(wrapper.emitted("update:modelValue")?.[0]?.[0]).toEqual([
      placement({ display_mode: "grid", rotation_mode: "none" }),
    ]);
  });

  it("keeps unsupported existing locations selectable and preserves their keys", () => {
    const row = placement({ surface_key: "legacy", slot_key: "special" });
    const wrapper = mount(ProductCollectionPlacementsEditor, {
      props: { modelValue: [row] },
    });
    expect(wrapper.get('option[value="custom"]').text()).toContain(
      "legacy / special",
    );
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
  });

  it("flags duplicate locations and disables editing during save", async () => {
    const wrapper = mount(ProductCollectionPlacementsEditor, {
      props: { modelValue: [placement(), placement()], disabled: true },
    });
    expect(wrapper.findAll('[role="alert"]')).toHaveLength(2);
    await wrapper.get('[role="switch"]').trigger("click");
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
    expect(wrapper.get("fieldset").attributes("disabled")).toBeDefined();
  });

  it("produces safe MDX insertion text only for valid slot keys", () => {
    expect(articleCollectionSnippet("heating-guide")).toContain(
      '<ArticleProductCollection slot="heating-guide" />',
    );
    expect(articleCollectionSnippet('bad" /><script>')).toBe("");
    expect(articleCollectionSnippet("")).toBe("");
  });

  it("round-trips scheduled instants through local datetime inputs", () => {
    const instant = "2026-09-20T09:25:00.000Z";
    expect(new Date(placementDateForInput(instant)).toISOString()).toBe(
      instant,
    );
    expect(placementDateForInput("invalid")).toBe("");
  });
});
