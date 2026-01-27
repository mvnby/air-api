import { atom } from 'nanostores';

export interface Toast {
    id: string;
    message: string;
    type: 'success' | 'info' | 'error';
}

export const toastStore = atom<Toast[]>([]);

export const addToast = (message: string, type: 'success' | 'info' | 'error' = 'success') => {
    const id = Math.random().toString(36).substring(2);
    const newToast: Toast = { id, message, type };

    toastStore.set([...toastStore.get(), newToast]);

    // Auto remove after 3 seconds
    setTimeout(() => {
        removeToast(id);
    }, 3000);
};

export const removeToast = (id: string) => {
    toastStore.set(toastStore.get().filter(t => t.id !== id));
};
