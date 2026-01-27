import { computed } from 'nanostores';
import { persistentAtom } from '@nanostores/persistent';

export type CartItem = {
    id: string;          // Product slug
    productId: number;   // Backend ID
    name: string;
    price: number;       // Base price
    image: string;       // Thumbnail URL
    quantity: number;
    withInstallation: boolean; // Toggle state
    installationPrice: number; // Calculated price for installation or 0
    installationMeters: number; // Default 3
    installationOptions: string[]; // e.g., ['vibration_stand', 'canopy']
    category?: string; // Helpful for installation matching
};

// Persistent store: key 'mvn_cart', initial value []
// Uses JSON encoder/decoder for complex objects
export const isCartOpen = persistentAtom<boolean>('mvn_cart_open', false, {
    encode: JSON.stringify,
    decode: JSON.parse,
});
export const cartItems = persistentAtom<CartItem[]>('mvn_cart', [], {
    encode: JSON.stringify,
    decode: JSON.parse,
});

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
export function addItem(item: Omit<CartItem, 'quantity' | 'withInstallation' | 'installationMeters' | 'installationOptions'> & { withInstallation?: boolean }) {
    const current = cartItems.get();
    const existingIndex = current.findIndex(i => i.id === item.id && i.withInstallation === !!item.withInstallation);

    if (existingIndex > -1) {
        // Increment quantity if same item with same options exists
        const updated = [...current];
        updated[existingIndex].quantity += 1;
        cartItems.set(updated);
    } else {
        // Add new item
        cartItems.set([...current, {
            ...item,
            quantity: 1,
            withInstallation: !!item.withInstallation,
            installationMeters: 3,
            installationOptions: [],
            installationPrice: item.installationPrice || 0
        }]);
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
            return { ...item, quantity };
        }
        return item;
    });
    cartItems.set(updated);
}

export function updateInstallationDetails(id: string, withInstallation: boolean, details: { meters?: number, price?: number, options?: string[] }) {
    const current = cartItems.get();
    const updated = current.map(item => {
        if (item.id === id && item.withInstallation === withInstallation) {
            return {
                ...item,
                installationMeters: details.meters ?? item.installationMeters,
                installationPrice: details.price ?? item.installationPrice,
                installationOptions: details.options ?? item.installationOptions ?? []
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
        updated[targetIndex].quantity += item.quantity;
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

export function clearCart() {
    cartItems.set([]);
}
