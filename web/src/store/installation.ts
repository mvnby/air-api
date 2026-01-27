import { atom } from 'nanostores';

const ENV_API_URL = import.meta.env.INTERNAL_API_URL || 'http://app:8000/api/v1';
const PUBLIC_API_URL = (import.meta.env.PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace(/\/$/, "");
const API_V1 = import.meta.env.SSR ? ENV_API_URL : PUBLIC_API_URL;

export interface InstallationOption {
    id: number;
    name: string;
    slug: string;
    price: number;
    image?: string;
    description?: string;
}

export const installationOptions = atom<InstallationOption[]>([]);

export async function fetchInstallationOptions() {
    try {
        const res = await fetch(`${API_V1}/services/options?category=installation_option`);
        if (!res.ok) throw new Error('Failed to fetch options');

        const data = await res.json();
        // Backend returns ServiceResponse: { id, title, slug, base_price, image, description ... }
        const mapped: InstallationOption[] = data.map((item: any) => ({
            id: item.id,
            name: item.title,
            slug: item.slug,
            price: item.base_price,
            image: item.image,
            description: item.description
        }));

        installationOptions.set(mapped);
    } catch (e) {
        console.error("Error loading installation options:", e);
    }
}
