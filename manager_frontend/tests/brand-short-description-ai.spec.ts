import { mount, shallowMount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { brandShortDescriptionDraft, confirmDialog } = vi.hoisted(() => ({
  brandShortDescriptionDraft: vi.fn(),
  confirmDialog: vi.fn(),
}));

vi.mock("../src/components/content-ai/content-ai-api", () => ({
  contentAiApi: { brandShortDescriptionDraft },
}));
vi.mock("../src/services/ui-feedback", () => ({ confirmDialog }));

import BrandEditorModal from "../src/components/brands/BrandEditorModal.vue";
import BrandShortDescriptionAiAction from "../src/components/brands/BrandShortDescriptionAiAction.vue";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("BrandShortDescriptionAiAction", () => {
  it("is unavailable until the full description is present", () => {
    const wrapper = mount(BrandShortDescriptionAiAction, {
      props: { title: "TCL", description: "" },
    });

    expect(wrapper.get("button").attributes("disabled")).toBeDefined();
    expect(brandShortDescriptionDraft).not.toHaveBeenCalled();
  });

  it("confirms before replacing text and only emits a persistence-free draft", async () => {
    confirmDialog.mockResolvedValue(true);
    brandShortDescriptionDraft.mockResolvedValue({
      short_description: "Техника TCL для дома и бизнеса.",
      prompt_version: "manager-brand-short-description-v1",
    });
    const wrapper = mount(BrandShortDescriptionAiAction, {
      props: {
        title: "TCL",
        description: "Полное редакторское описание бренда.",
        hasExistingContent: true,
      },
    });

    await wrapper.get("button").trigger("click");

    expect(confirmDialog).toHaveBeenCalled();
    expect(brandShortDescriptionDraft).toHaveBeenCalledWith({
      brand_name: "TCL",
      full_description: "Полное редакторское описание бренда.",
    });
    expect(wrapper.emitted("draft")?.[0]).toEqual([
      {
        short_description: "Техника TCL для дома и бизнеса.",
        prompt_version: "manager-brand-short-description-v1",
      },
    ]);
  });

  it("does not start duplicate requests while confirmation is open", async () => {
    let resolveConfirmation: ((value: boolean) => void) | undefined;
    confirmDialog.mockImplementation(
      () =>
        new Promise<boolean>((resolve) => {
          resolveConfirmation = resolve;
        }),
    );
    brandShortDescriptionDraft.mockResolvedValue({
      short_description: "Короткий текст",
      prompt_version: "manager-brand-short-description-v1",
    });
    const wrapper = mount(BrandShortDescriptionAiAction, {
      props: {
        title: "TCL",
        description: "Полное описание",
        hasExistingContent: true,
      },
    });

    await wrapper.get("button").trigger("click");
    await wrapper.get("button").trigger("click");

    expect(confirmDialog).toHaveBeenCalledTimes(1);
    resolveConfirmation?.(true);
    await vi.waitFor(() => expect(brandShortDescriptionDraft).toHaveBeenCalledTimes(1));
  });
});

describe("BrandEditorModal", () => {
  it("applies an AI draft to the form without saving it", async () => {
    const form = {
      title: "TCL",
      slug: "tcl",
      logo_url: "",
      short_description: "",
      description: "Полное описание",
      sort_order: 0,
      is_published: true,
    };
    const wrapper = shallowMount(BrandEditorModal, {
      props: { open: true, form, editing: true, saving: false },
    });

    wrapper.findComponent(BrandShortDescriptionAiAction).vm.$emit("draft", {
      short_description: "Короткий текст",
      prompt_version: "manager-brand-short-description-v1",
    });
    await wrapper.vm.$nextTick();

    expect(form.short_description).toBe("Короткий текст");
    expect(wrapper.emitted("save")).toBeUndefined();
  });
});
