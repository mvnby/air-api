const FALLBACK_DESCRIPTION = "Кондиционеры в Витебске: подбор, продажа, монтаж и обслуживание MVN.";
const MAX_META_DESCRIPTION_LENGTH = 170;

const ENTITY_MAP = {
    "&amp;": "&",
    "&quot;": '"',
    "&#34;": '"',
    "&#39;": "'",
    "&apos;": "'",
    "&lt;": "<",
    "&gt;": ">",
    "&nbsp;": " ",
};

export function sanitizeSeoText(value) {
    return String(value || "")
        .replace(/<[^>]*>/g, " ")
        .replace(/&(amp|quot|apos|lt|gt|nbsp);|&#(?:34|39);/g, (entity) => ENTITY_MAP[entity] || " ")
        .replace(/[|•·]+/g, " ")
        .replace(/\s+/g, " ")
        .trim();
}

export function trimSeoDescription(value, maxLength = MAX_META_DESCRIPTION_LENGTH) {
    const normalized = sanitizeSeoText(value);
    if (normalized.length <= maxLength) return normalized;

    const hardLimit = Math.max(20, maxLength - 3);
    const breakpoint = normalized.lastIndexOf(" ", hardLimit);
    const end = breakpoint >= 80 ? breakpoint : hardLimit;
    return `${normalized.slice(0, end).trim()}...`;
}

export function normalizeCanonicalPath(value = "/") {
    const raw = String(value || "/").trim() || "/";
    const parsed = new URL(raw, "https://mvn.by");
    let pathname = parsed.pathname || "/";

    if (pathname === "/index.php" && parsed.searchParams.has("_route_")) {
        pathname = `/${String(parsed.searchParams.get("_route_") || "").replace(/^\/+/, "")}`;
    } else if (pathname === "/index.php") {
        pathname = "/";
    }

    pathname = pathname.replace(/\/{2,}/g, "/");
    if (!pathname.startsWith("/")) {
        pathname = `/${pathname}`;
    }

    const hasFileExtension = /\.[a-z0-9]{2,8}$/i.test(pathname);
    if (!hasFileExtension && pathname !== "/" && !pathname.endsWith("/")) {
        pathname = `${pathname}/`;
    }

    return pathname;
}

export function buildCanonicalUrl(value = "/", site = "https://mvn.by") {
    return new URL(normalizeCanonicalPath(value), site).toString();
}

const getTagGroupSlug = (tag) => tag?.group?.slug || tag?.group_slug || "";

const getTagByGroup = (product, groupSlug) =>
    (product?.tags || []).find((tag) => getTagGroupSlug(tag) === groupSlug);

function formatNumber(value) {
    const number = Number(value);
    if (!Number.isFinite(number) || number <= 0) return "";
    return Number.isInteger(number) ? String(number) : String(number).replace(".", ",");
}

function uniqueParts(parts) {
    const seen = new Set();
    return parts
        .map(sanitizeSeoText)
        .filter(Boolean)
        .filter((part) => {
            const key = part.toLowerCase();
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });
}

function getProductBrandTitle(product) {
    const brand = sanitizeSeoText(product?.brand?.title);
    if (brand) return brand;
    return sanitizeSeoText(getTagByGroup(product, "brand")?.title);
}

function getProductCategoryTitle(product) {
    return sanitizeSeoText(getTagByGroup(product, "category")?.title);
}

function getProductSpecParts(product) {
    const parts = [];
    const title = sanitizeSeoText(product?.title).toLowerCase();
    const area = formatNumber(product?.specs?.area_m2);
    const powerCooling = formatNumber(product?.power_cooling);

    if (product?.is_inverter || title.includes("инвертор")) {
        parts.push("инвертор");
    }
    if (area) {
        parts.push(`до ${area} м²`);
    }
    if (powerCooling) {
        parts.push(`${powerCooling} кВт`);
    }

    return uniqueParts(parts).slice(0, 3);
}

export function buildProductMetaDescription(product) {
    const productName = sanitizeSeoText(product?.title) || "Кондиционер MVN";
    const brandTitle = getProductBrandTitle(product);
    const categoryTitle = getProductCategoryTitle(product);
    const specParts = getProductSpecParts(product);
    const descriptors = uniqueParts([
        brandTitle && !productName.toLowerCase().includes(brandTitle.toLowerCase()) ? brandTitle : "",
        categoryTitle,
        ...specParts,
    ]);
    const specsSentence = descriptors.length ? ` ${descriptors.join(", ")}.` : "";

    const candidates = [
        `${productName}: купить в Витебске с монтажом и гарантией.${specsSentence} Подбор и сервис MVN.`,
        `${productName}: купить в Витебске с монтажом и гарантией. Подбор и обслуживание MVN.`,
        `${productName}: купить в Витебске с монтажом и гарантией MVN.`,
        productName,
    ];

    const firstWithinLimit = candidates
        .map((candidate) => sanitizeSeoText(candidate))
        .find((candidate) => candidate.length <= MAX_META_DESCRIPTION_LENGTH);

    return firstWithinLimit || trimSeoDescription(candidates[0]);
}

export function buildBrandSeoTitle(brand) {
    const brandTitle = sanitizeSeoText(brand?.title) || "бренда";
    return `Кондиционеры ${brandTitle}: купить в Витебске`;
}

export function buildBrandMetaDescription(brand) {
    const brandTitle = sanitizeSeoText(brand?.title) || "бренда";
    return trimSeoDescription(
        `Кондиционеры ${brandTitle} в Витебске: подбор, продажа, монтаж и обслуживание. Гарантия, консультация и сервис MVN.`,
    ) || FALLBACK_DESCRIPTION;
}
