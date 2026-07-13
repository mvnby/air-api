export const MAX_CART_LINES = 20;
export const MAX_CART_QUANTITY = 20;
export const MAX_INSTALLATION_METERS = 50;
export const MAX_INSTALLATION_OPTIONS = 20;

const OPTION_SLUG_PATTERN = /^[a-z0-9]+(?:[-_][a-z0-9]+)*$/;

const finiteNumber = (value, fallback = 0) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
};

export const clampCartQuantity = (value) => Math.min(
    MAX_CART_QUANTITY,
    Math.max(1, Math.trunc(finiteNumber(value, 1))),
);

export function normalizeCartItems(value) {
    if (!Array.isArray(value)) return [];

    const normalized = [];
    for (const raw of value) {
        if (!raw || typeof raw !== 'object') continue;
        const id = String(raw.id || '').trim();
        const productId = Math.trunc(finiteNumber(raw.productId));
        if (!id || productId <= 0) continue;

        const withInstallation = raw.withInstallation === true;
        const rateId = Math.trunc(finiteNumber(raw.installationRateId));
        const options = Array.from(new Set(
            (Array.isArray(raw.installationOptions) ? raw.installationOptions : [])
                .map(option => String(option || '').trim())
                .filter(option => OPTION_SLUG_PATTERN.test(option)),
        )).slice(0, MAX_INSTALLATION_OPTIONS);
        const item = {
            ...raw,
            id,
            productId,
            name: String(raw.name || '').slice(0, 300),
            image: String(raw.image || '').slice(0, 2_000),
            price: Math.max(0, finiteNumber(raw.price)),
            quantity: clampCartQuantity(raw.quantity),
            withInstallation,
            // Keep the last non-authoritative quote while installation is off.
            // The cart toggle can then restore an honest preview after reload;
            // checkout still recalculates and validates the rate on the server.
            installationPrice: Math.max(0, finiteNumber(raw.installationPrice)),
            installationRateId: rateId > 0 ? rateId : null,
            installationMeters: Math.min(
                MAX_INSTALLATION_METERS,
                Math.max(1, finiteNumber(raw.installationMeters, 3)),
            ),
            installationOptions: withInstallation ? options : [],
        };

        const existing = normalized.find(candidate => (
            candidate.id === item.id
            && candidate.withInstallation === item.withInstallation
        ));
        if (existing) {
            existing.quantity = Math.min(
                MAX_CART_QUANTITY,
                existing.quantity + item.quantity,
            );
            continue;
        }
        if (normalized.length >= MAX_CART_LINES) break;
        normalized.push(item);
    }
    return normalized;
}
