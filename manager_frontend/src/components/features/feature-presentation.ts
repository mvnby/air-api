export type FeatureDisplayMode = "icon" | "compact" | "detailed";

export const FEATURE_DISPLAY_MODES: {
  value: FeatureDisplayMode;
  label: string;
}[] = [
  { value: "icon", label: "Иконка" },
  { value: "compact", label: "Кратко" },
  { value: "detailed", label: "Подробно" },
];

export type FeaturePresentationContent = {
  name: string;
  icon_caption?: string | null;
  short_description?: string | null;
  full_description?: string | null;
  icon?: string | null;
  icon_url?: string | null;
  image_url?: string | null;
};

export const featureIconLabel = (feature: FeaturePresentationContent): string =>
  feature.icon_caption?.trim() || feature.short_description?.trim() || feature.name;

// Legacy features may use a semantic icon name instead of an image URL.
export const featureIconUrl = (feature: FeaturePresentationContent): string | null => {
  const icon = feature.icon_url || feature.icon;
  return icon && /^(?:https?:\/\/|\/)/i.test(icon) ? icon : null;
};

export const CATALOG_FEATURE_ICONS = [
  { id: "wifi", label: "Wi-Fi" },
  { id: "wifi-ready", label: "Wi-Fi Ready" },
  { id: "airflow-4d", label: "4D-обдув" },
  { id: "ai-compressor", label: "AI-компрессор" },
  { id: "fresh-air", label: "Свежий воздух" },
  { id: "air-filter", label: "Фильтрация" },
  { id: "quiet", label: "Тихий режим" },
  { id: "turbo", label: "Турборежим" },
  { id: "heating", label: "Обогрев" },
  { id: "self-clean", label: "Самоочистка" },
  { id: "energy-saving", label: "Экономия энергии" },
  { id: "timer", label: "Таймер" },
].map((icon) => ({
  ...icon,
  url: `/manager/assets/catalog-feature-icons/${icon.id}.svg`,
}));
