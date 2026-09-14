import { onMounted } from 'vue';
import { usePlatformDocumentTemplates } from './usePlatformDocumentTemplates';
import { usePlatformRepairComplaints } from './usePlatformRepairComplaints';
import { usePlatformSettingsCore } from './usePlatformSettingsCore';

export const usePlatformSettings = () => {
    const core = usePlatformSettingsCore();
    const documents = usePlatformDocumentTemplates(core.setToast);
    const repairComplaints = usePlatformRepairComplaints(core.setToast);
    onMounted(() => {
        void core.loadSettings();
        void documents.loadDocumentTemplates().then(() => documents.loadCustomers());
        void repairComplaints.loadRepairComplaintPresets();
        void documents.loadTemplateFiles();
        void core.loadGoogleAuthStatus();
    });
    return { ...core, ...documents, ...repairComplaints };
};
export type PlatformSettingsController = ReturnType<typeof usePlatformSettings>;
