type CatalogSeoProduct = {
    id?: number;
    title: string;
    slug?: string | null;
    price?: number | null;
    main_image?: string | null;
    availability_status?: string | null;
    vitebsk_qty?: number | null;
    minsk_qty?: number | null;
};

function absoluteUrl(path: string | null | undefined, origin: string) {
    if (!path) return undefined;
    if (/^https?:\/\//i.test(path)) return path;
    return new URL(path.startsWith("/") ? path : `/${path}`, origin).toString();
}

export function getSchemaAvailability(product: CatalogSeoProduct) {
    const status = product.availability_status || "";
    const stockQty = Number(product.vitebsk_qty || 0) + Number(product.minsk_qty || 0);

    if (status === "out_of_stock") return "https://schema.org/OutOfStock";
    if (status === "check_availability") return "https://schema.org/LimitedAvailability";
    if (stockQty > 0 || status === "in_stock_now" || status === "available_2_3_days") {
        return "https://schema.org/InStock";
    }
    return "https://schema.org/OutOfStock";
}

export function buildCatalogItemListSchema(products: CatalogSeoProduct[], origin: string) {
    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        itemListElement: products.slice(0, 20).map((product, index) => ({
            "@type": "ListItem",
            position: index + 1,
            item: {
                "@type": "Product",
                name: product.title,
                url: absoluteUrl(product.slug ? `/product/${product.slug}` : undefined, origin),
                image: absoluteUrl(product.main_image, origin),
                sku: product.id ? String(product.id) : undefined,
                offers: {
                    "@type": "Offer",
                    price: Number(product.price || 0),
                    priceCurrency: "BYN",
                    availability: getSchemaAvailability(product),
                    url: absoluteUrl(product.slug ? `/product/${product.slug}` : undefined, origin),
                },
            },
        })),
    };
}
