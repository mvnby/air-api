import { atom } from 'nanostores';
import { getServiceOptions } from '../utils/api';

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
        const data = await getServiceOptions('installation_option');

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
