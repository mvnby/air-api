import { ref } from 'vue';
import type { ManagerRepairComplaintPresetCreatePayload, ManagerRepairComplaintPresetResponse, ManagerRepairComplaintPresetUpdatePayload } from '../../../client';
import { ManagerRepairComplaintsService } from '../../../client';
import { getApiErrorMessage } from '../../../utils/api-errors';
import { confirmDialog } from '../../../services/ui-feedback';
import type { RepairComplaintPresetForm } from './platform-settings-types';

export const usePlatformRepairComplaints = (setToast: (message: string, type?: 'success' | 'error') => void) => {
const repairComplaintPresets = ref<RepairComplaintPresetForm[]>([]);
const repairComplaintSearch = ref('');
const repairComplaintGroupFilter = ref('');
const loadingRepairComplaints = ref(false);
const savingRepairComplaintKeys = ref<Set<string>>(new Set());
const deletingRepairComplaintId = ref<number | null>(null);
const emptyRepairComplaintPreset = (): RepairComplaintPresetForm => ({
    id: null,
    complaint_group: repairComplaintGroupFilter.value || 'other',
    customer_phrase: '',
    document_wording: '',
    likely_diagnosis: '',
    is_favorite: false,
    is_active: true,
    sort_order: repairComplaintPresets.value.length * 10,
    comment: '',
});

const mapRepairComplaintPresetToForm = (item: ManagerRepairComplaintPresetResponse): RepairComplaintPresetForm => ({
    id: item.id,
    complaint_group: item.complaint_group || 'other',
    customer_phrase: item.customer_phrase || '',
    document_wording: item.document_wording || '',
    likely_diagnosis: item.likely_diagnosis || '',
    is_favorite: item.is_favorite === true,
    is_active: item.is_active !== false,
    sort_order: Number(item.sort_order ?? 0),
    comment: item.comment || '',
});

const repairComplaintPayload = (preset: RepairComplaintPresetForm): ManagerRepairComplaintPresetCreatePayload => ({
    complaint_group: preset.complaint_group.trim() || 'other',
    customer_phrase: preset.customer_phrase.trim(),
    document_wording: preset.document_wording.trim(),
    likely_diagnosis: preset.likely_diagnosis.trim(),
    is_favorite: preset.is_favorite,
    is_active: preset.is_active,
    sort_order: Number(preset.sort_order || 0),
    comment: preset.comment.trim() || undefined,
});
const loadRepairComplaintPresets = async () => {
    loadingRepairComplaints.value = true;
    try {
        const res = await ManagerRepairComplaintsService.listManagerRepairComplaintPresets(
            repairComplaintSearch.value.trim(),
            repairComplaintGroupFilter.value || null,
            true,
            false,
            200,
        );
        repairComplaintPresets.value = res.items.map(mapRepairComplaintPresetToForm);
    } catch (e) {
        setToast(getApiErrorMessage(e), 'error');
    } finally {
        loadingRepairComplaints.value = false;
    }
};

const addRepairComplaintPreset = () => {
    repairComplaintPresets.value = [emptyRepairComplaintPreset(), ...repairComplaintPresets.value];
};

const saveRepairComplaintPreset = async (preset: RepairComplaintPresetForm) => {
    const key = String(preset.id || `new:${preset.complaint_group}:${preset.sort_order}`);
    if (savingRepairComplaintKeys.value.has(key)) return;
    if (!preset.customer_phrase.trim()) {
        setToast('Заполните жалобу клиента', 'error');
        return;
    }
    savingRepairComplaintKeys.value.add(key);
    try {
        const payload = repairComplaintPayload(preset);
        const saved = preset.id
            ? await ManagerRepairComplaintsService.updateManagerRepairComplaintPreset(preset.id, payload as ManagerRepairComplaintPresetUpdatePayload)
            : await ManagerRepairComplaintsService.createManagerRepairComplaintPreset(payload);
        const savedForm = mapRepairComplaintPresetToForm(saved);
        const index = repairComplaintPresets.value.indexOf(preset);
        if (index >= 0) {
            repairComplaintPresets.value[index] = savedForm;
        }
        setToast('Пресет жалобы сохранен');
    } catch (e) {
        setToast(getApiErrorMessage(e), 'error');
    } finally {
        savingRepairComplaintKeys.value.delete(key);
    }
};

const deleteRepairComplaintPreset = async (preset: RepairComplaintPresetForm) => {
    if (!preset.id) {
        repairComplaintPresets.value = repairComplaintPresets.value.filter((item) => item !== preset);
        return;
    }
    if (!await confirmDialog({ title: 'Удалить пресет?', description: preset.customer_phrase, confirmText: 'Удалить', variant: 'danger' })) return;
    deletingRepairComplaintId.value = preset.id;
    try {
        await ManagerRepairComplaintsService.deleteManagerRepairComplaintPreset(preset.id);
        repairComplaintPresets.value = repairComplaintPresets.value.filter((item) => item.id !== preset.id);
        setToast('Пресет жалобы удален');
    } catch (e) {
        setToast(getApiErrorMessage(e), 'error');
    } finally {
        deletingRepairComplaintId.value = null;
    }
};

    return { repairComplaintPresets, repairComplaintSearch, repairComplaintGroupFilter, loadingRepairComplaints, savingRepairComplaintKeys, deletingRepairComplaintId, loadRepairComplaintPresets, addRepairComplaintPreset, saveRepairComplaintPreset, deleteRepairComplaintPreset };
};
