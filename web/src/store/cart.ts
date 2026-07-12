import { atom, computed } from 'nanostores';
import { persistentAtom } from '@nanostores/persistent';
import { refreshProductPrices } from '../utils/api';
import {
    MAX_CART_LINES,
    MAX_CART_QUANTITY,
    MAX_INSTALLATION_METERS,
    MAX_INSTALLATION_OPTIONS,
    clampCartQuantity,
    normalizeCartItems,
} from '../utils/cart-normalization';

export type CartItem = {
    id: string;          // Product slug
    productId: number;   // Backend ID
    name: string;
    price: number;       // Base price
    image: string;       // Thumbnail URL
    quantity: number;
    withInstallation: boolean; // Toggle state
    installationPrice: number; // Calculated price for installation or 0
    installationRateId: number | null; // Matched public InstallationRate ID
    installationMeters: number; // Default 3
    installationOptions: string[]; // e.g., ['vibration_stand', 'canopy']
    category?: string; // Helpful for installation matching
};

const createPersistentStore = <T>(key: string, initial: T, normalize?: (value: unknown) => T) => {
    if (import.meta.env.SSR) {
        return atom<T>(initial);
    }

    return persistentAtom<T>(key, initial, {
        encode: JSON.stringify,
        decode: value => {
            try {
                const parsed = JSON.parse(value);
                return normalize ? normalize(parsed) : parsed;
            } catch {
                return initial;
            }
        },
    });
};

// Persistent store: key 'mvn_cart', initial value []
// Uses JSON encoder/decoder for complex objects in the browser only.
export const isCartOpen = createPersistentStore<boolean>('mvn_cart_open', false);
export const cartItems = createPersistentStore<CartItem[]>(
    'mvn_cart',
    [],
    value => normalizeCartItems(value) as CartItem[],
);

export const cartTotal = computed(cartItems, items => {
    return items.reduce((sum, item) => {
        // Calculate installation price dynamically based on meters/options
        // Ideally we should recalculate it via a helper, but for now use stored price + meter extras
        // NOTE: The UI should update installationPrice before calling updateInstallationDetails if logic is there,
        // OR we put pricing logic here.
        // Let's assume installationPrice is the BASE for standard + extra meters cost.
        // But extra meters cost depends on rate.
        // Simplified: store holds the FINAL calculated installationPrice.
        const itemPrice = item.price + (item.withInstallation ? item.installationPrice : 0);
        return sum + (itemPrice * item.quantity);
    }, 0);
});

export const cartCount = computed(cartItems, items => {
    return items.reduce((sum, item) => sum + item.quantity, 0);
});

// Actions
export function addItem(
    item: Omit<
        CartItem,
        'quantity' | 'withInstallation' | 'installationRateId' | 'installationMeters' | 'installationOptions'
    > & { withInstallation?: boolean, installationRateId?: number | null }
) : boolean {
    const current = cartItems.get();
    const existingIndex = current.findIndex(i => i.id === item.id && i.withInstallation === !!item.withInstallation);

    if (existingIndex > -1) {
        // Increment quantity if same item with same options exists
        const updated = [...current];
        updated[existingIndex].quantity = Math.min(
            MAX_CART_QUANTITY,
            updated[existingIndex].quantity + 1,
        );
        cartItems.set(updated);
        return true;
    } else {
        if (current.length >= MAX_CART_LINES) return false;
        // Add new item
        cartItems.set([...current, {
            ...item,
            quantity: 1,
            withInstallation: !!item.withInstallation,
            installationRateId: item.installationRateId || null,
            installationMeters: 3,
            installationOptions: [],
            installationPrice: item.installationPrice || 0
        }]);
        return true;
    }
}

export function removeItem(id: string, withInstallation: boolean) {
    const current = cartItems.get();
    cartItems.set(current.filter(i => !(i.id === id && i.withInstallation === withInstallation)));
}

export function updateQuantity(id: string, withInstallation: boolean, quantity: number) {
    if (quantity < 1) {
        removeItem(id, withInstallation);
        return;
    }
    const current = cartItems.get();
    const updated = current.map(item => {
        if (item.id === id && item.withInstallation === withInstallation) {
            return { ...item, quantity: clampCartQuantity(quantity) };
        }
        return item;
    });
    cartItems.set(updated);
}

export function updateInstallationDetails(
    id: string,
    withInstallation: boolean,
    details: { meters?: number, price?: number, options?: string[], rateId?: number | null }
) {
    const current = cartItems.get();
    const updated = current.map(item => {
        if (item.id === id && item.withInstallation === withInstallation) {
            const installationOptions = Array.from(new Set(
                details.options ?? item.installationOptions ?? []
            )).slice(0, MAX_INSTALLATION_OPTIONS);
            return {
                ...item,
                installationMeters: details.meters === undefined
                    ? item.installationMeters
                    : Math.min(MAX_INSTALLATION_METERS, Math.max(1, details.meters)),
                installationPrice: details.price ?? item.installationPrice,
                installationRateId: details.rateId ?? item.installationRateId ?? null,
                installationOptions,
            };
        }
        return item;
    });
    cartItems.set(updated);
}

export function toggleInstallation(id: string, currentWithInstallation: boolean) {
    const current = cartItems.get();
    const itemIndex = current.findIndex(i => i.id === id && i.withInstallation === currentWithInstallation);

    if (itemIndex === -1) return;

    const item = current[itemIndex];
    const newWithInstallation = !currentWithInstallation;

    // Check if there's already an item with the target state to merge with
    const targetIndex = current.findIndex(i => i.id === id && i.withInstallation === newWithInstallation);

    if (targetIndex > -1) {
        // Merge with existing item of that state
        const updated = [...current];
        updated[targetIndex].quantity = Math.min(
            MAX_CART_QUANTITY,
            updated[targetIndex].quantity + item.quantity,
        );
        // Remove the source item
        updated.splice(itemIndex, 1);
        cartItems.set(updated);
    } else {
        // Just flip the state
        const updated = [...current];
        // Reset defaults when toggling ON
        const newMeters = newWithInstallation ? 3 : item.installationMeters;
        updated[itemIndex] = { ...item, withInstallation: newWithInstallation, installationMeters: newMeters };
        cartItems.set(updated);
    }
}

export async function refreshPrices() {
    const current = cartItems.get();
    if (current.length === 0) return;

    // Extract Slugs or IDs (using ID if available, else slug)
    // Actually our refreshProductPrices handles both, but let's prefer Slug as it is the main ID in cart (item.id)
    // Check if we have numeric IDs? item.productId

    // We can just fetch by slug because item.id is slug
    const idsToFetch = current.map(i => i.id);

    try {
        const freshProducts: any[] = await refreshProductPrices(idsToFetch);

        if (!freshProducts || freshProducts.length === 0) return;

        // Create a map for quick lookup
        const productMap = new Map();
        freshProducts.forEach(p => {
            productMap.set(p.slug, p);
        });

        const updated = current.map(item => {
            const fresh = productMap.get(item.id);
            if (fresh) {
                // Update price and ensure ID is set
                return {
                    ...item,
                    price: fresh.price,
                    productId: fresh.id, // Update numeric ID just in case
                    name: fresh.title, // Sync name if changed
                    image: fresh.card_image || fresh.main_image // Sync image
                };
            }
            return item;
        });

        cartItems.set(updated);
    } catch (e) {
        console.error("Failed to refresh cart prices", e);
    }
}

export function clearCart() {
    cartItems.set([]);
}
