import { computed, ref } from 'vue';
import { api } from '../../../api';
import type { ManagerGoogleAuthStatusResponse, ManagerSettingResponse, ManagerSettingUpdatePayload } from '../../../client';
import { ManagerSettingsService } from '../../../client';
import { getApiErrorMessage } from '../../../utils/api-errors';
import { BOT_SELECTION_RULES_DESCRIPTION, BOT_SELECTION_RULES_KEY, COMPANY_REQUISITE_DESCRIPTIONS, COMPANY_REQUISITE_KEYS, DEFAULT_BOT_SELECTION_RULES, DEFAULT_COMPANY_REQUISITES, DOCUMENT_ROLE_OPTIONS, EMAIL_LEAD_AUTO_IMPORT_KEY, EMAIL_LEAD_INTERVAL_KEY, EMAIL_LEAD_LAST_IMPORT_KEY, EMAIL_LEAD_SETTING_KEYS, normalizeRoleType } from './platform-settings-types';
import type { ContractTemplateForm, SettingsTab } from './platform-settings-types';

export const usePlatformSettingsCore = () => {
const settings = ref<ManagerSettingResponse[]>([]);
const loading = ref(false);
const error = ref('');
const toast = ref('');
const toastType = ref<'success' | 'error'>('success');

// A set to keep track of which settings are currently being saved
const savingKeys = ref<Set<string>>(new Set());
const contractTemplateDrafts = ref<Record<string, ContractTemplateForm[]>>({});
const activeSettingsTab = ref<SettingsTab>('general');
const showCreateForm = ref(false);
const newKey = ref('');
const newValue = ref('');
const newDescription = ref('');
const creating = ref(false);
const googleAuthStatus = ref<ManagerGoogleAuthStatusResponse | null>(null);
const googleAuthLoading = ref(false);
const googleAuthBusy = ref(false);
const emailLeadSettings = ref({
    autoImport: false,
    intervalMinutes: 20,
    lastImportAt: '',
});
const emailLeadSettingsSaving = ref(false);
const botSelectionRulesText = ref('');
const botSelectionRulesUpdatedAt = ref('');
const botSelectionRulesSaving = ref(false);
const companyRequisites = ref({ ...DEFAULT_COMPANY_REQUISITES });
const companyRequisitesSaving = ref(false);
const goToBackups = () => {
    if (window.location.pathname !== '/manager/settings/backup') {
        window.history.pushState({}, '', '/manager/settings/backup');
        window.dispatchEvent(new PopStateEvent('popstate'));
    }
};

const setToast = (msg: string, type: 'success' | 'error' = 'success') => {
    toast.value = msg;
    toastType.value = type;
    window.setTimeout(() => { toast.value = ''; }, 3000);
}

const isEnabledSettingValue = (value?: string | null) => ['1', 'true', 'yes', 'on'].includes(String(value || '').trim().toLowerCase());

const parsePositiveIntSetting = (value: string | null | undefined, fallback: number, max = 1000) => {
    const parsed = Number.parseInt(String(value || ''), 10);
    return Number.isFinite(parsed) ? Math.min(max, Math.max(1, parsed)) : fallback;
};

const hydrateEmailLeadSettings = (items: ManagerSettingResponse[]) => {
    const byKey = new Map(items.map((item) => [item.key, item.value]));
    emailLeadSettings.value = {
        autoImport: isEnabledSettingValue(byKey.get(EMAIL_LEAD_AUTO_IMPORT_KEY)),
        intervalMinutes: parsePositiveIntSetting(byKey.get(EMAIL_LEAD_INTERVAL_KEY), 20, 1440),
        lastImportAt: byKey.get(EMAIL_LEAD_LAST_IMPORT_KEY) || '',
    };
};

const formatJsonText = (value: unknown) => JSON.stringify(value, null, 2);

const formatJsonSettingValue = (value?: string | null) => {
    if (!value) return formatJsonText(DEFAULT_BOT_SELECTION_RULES);
    try {
        return formatJsonText(JSON.parse(value));
    } catch {
        return value;
    }
};

const hydrateBotSelectionRules = (items: ManagerSettingResponse[]) => {
    const setting = items.find((item) => item.key === BOT_SELECTION_RULES_KEY);
    botSelectionRulesText.value = formatJsonSettingValue(setting?.value);
    botSelectionRulesUpdatedAt.value = setting?.updated_at || '';
};

const hydrateCompanyRequisites = (items: ManagerSettingResponse[]) => {
    const byKey = new Map(items.map((item) => [item.key, item.value]));
    companyRequisites.value = {
        ...DEFAULT_COMPANY_REQUISITES,
        ...Object.fromEntries(
            COMPANY_REQUISITE_KEYS.map((key) => [key, byKey.get(key) || DEFAULT_COMPANY_REQUISITES[key]]),
        ),
    };
};

const parsedBotSelectionRules = computed(() => {
    try {
        const parsed = JSON.parse(botSelectionRulesText.value || '{}');
        return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, any> : null;
    } catch {
        return null;
    }
});

const botSelectionRulesError = computed(() => {
    const parsed = parsedBotSelectionRules.value;
    if (!parsed) return 'Некорректный JSON';
    if (!parsed.power_classes || typeof parsed.power_classes !== 'object' || Array.isArray(parsed.power_classes)) {
        return 'Нет блока power_classes';
    }
    if (!parsed.tiers || typeof parsed.tiers !== 'object' || Array.isArray(parsed.tiers)) {
        return 'Нет блока tiers';
    }
    return '';
});

const botSelectionPowerPreview = computed(() => {
    const powerClasses = parsedBotSelectionRules.value?.power_classes;
    if (!powerClasses || typeof powerClasses !== 'object' || Array.isArray(powerClasses)) return [];
    return Object.entries(powerClasses)
        .map(([code, config]) => {
            const item = config as { kw?: number; area_min?: number; area_max?: number; area?: number[] };
            const areaMin = item.area_min ?? item.area?.[0];
            const areaMax = item.area_max ?? item.area?.[1];
            return {
                code,
                kw: item.kw,
                area: areaMin && areaMax ? `${areaMin}-${areaMax}` : '—',
            };
        })
        .sort((a, b) => Number(a.code) - Number(b.code));
});

const botSelectionTierPreview = computed(() => {
    const tiers = parsedBotSelectionRules.value?.tiers;
    if (!tiers || typeof tiers !== 'object' || Array.isArray(tiers)) return [];
    return Object.entries(tiers).map(([mode, items]) => ({
        mode,
        labels: Array.isArray(items)
            ? items.map((item: any) => String(item?.label || item?.key || '').trim()).filter(Boolean).join(' / ')
            : '',
    }));
});

const upsertSettingValue = async (key: string, value: string, description: string) => {
    try {
        return await ManagerSettingsService.updateManagerSetting(key, { value, description });
    } catch {
        return await ManagerSettingsService.createManagerSetting({ key, value, description });
    }
};

const saveCompanyRequisites = async () => {
    companyRequisitesSaving.value = true;
    error.value = '';
    try {
        for (const key of COMPANY_REQUISITE_KEYS) {
            await upsertSettingValue(
                key,
                companyRequisites.value[key] || '',
                COMPANY_REQUISITE_DESCRIPTIONS[key],
            );
        }
        setToast('Реквизиты сохранены');
        await loadSettings();
    } catch (e) {
        setToast(getApiErrorMessage(e), 'error');
    } finally {
        companyRequisitesSaving.value = false;
    }
};

const saveEmailLeadSettings = async () => {
    emailLeadSettingsSaving.value = true;
    error.value = '';
    const interval = Math.min(1440, Math.max(1, Number(emailLeadSettings.value.intervalMinutes) || 20));
    try {
        await upsertSettingValue(
            EMAIL_LEAD_AUTO_IMPORT_KEY,
            emailLeadSettings.value.autoImport ? 'true' : 'false',
            'Автоматически проверять входящую почту и создавать лиды из потенциальных заказов.',
        );
        await upsertSettingValue(
            EMAIL_LEAD_INTERVAL_KEY,
            String(interval),
            'Интервал автоматической проверки email-лидов в минутах.',
        );
        emailLeadSettings.value.intervalMinutes = interval;
        setToast('Настройки email-лидов сохранены');
        await loadSettings();
    } catch (e) {
        setToast(getApiErrorMessage(e), 'error');
    } finally {
        emailLeadSettingsSaving.value = false;
    }
};

const saveBotSelectionRules = async () => {
    if (botSelectionRulesError.value) {
        setToast(botSelectionRulesError.value, 'error');
        return;
    }
    botSelectionRulesSaving.value = true;
    error.value = '';
    try {
        const formatted = formatJsonText(parsedBotSelectionRules.value);
        await upsertSettingValue(BOT_SELECTION_RULES_KEY, formatted, BOT_SELECTION_RULES_DESCRIPTION);
        botSelectionRulesText.value = formatted;
        setToast('Правила подбора бота сохранены');
        await loadSettings();
    } catch (e) {
        setToast(getApiErrorMessage(e), 'error');
    } finally {
        botSelectionRulesSaving.value = false;
    }
};

const resetBotSelectionRulesDraft = () => {
    botSelectionRulesText.value = formatJsonText(DEFAULT_BOT_SELECTION_RULES);
};

const loadGoogleAuthStatus = async () => {
    googleAuthLoading.value = true;
    try {
        googleAuthStatus.value = await api.getManagerGoogleAuthStatus();
    } catch (e) {
        setToast(getApiErrorMessage(e), 'error');
    } finally {
        googleAuthLoading.value = false;
    }
};

const openGoogleAuth = async () => {
    googleAuthBusy.value = true;
    try {
        const response = await api.getManagerGoogleAuthUrl();
        window.open(response.url, '_blank', 'noopener,noreferrer');
        setToast('Открыли Google Login в новой вкладке');
    } catch (e) {
        setToast(getApiErrorMessage(e), 'error');
    } finally {
        googleAuthBusy.value = false;
    }
};

const loadSettings = async () => {
    loading.value = true;
    error.value = '';
    try {
        const res = await api.listManagerSettings();
        hydrateEmailLeadSettings(res.items);
        hydrateBotSelectionRules(res.items);
        hydrateCompanyRequisites(res.items);
        settings.value = res.items.filter(
            (setting) =>
                setting.key !== 'contract_templates' &&
                setting.key !== 'install_discount' &&
                setting.key !== BOT_SELECTION_RULES_KEY &&
                !COMPANY_REQUISITE_KEYS.includes(setting.key as (typeof COMPANY_REQUISITE_KEYS)[number]) &&
                !EMAIL_LEAD_SETTING_KEYS.has(setting.key),
        );
        contractTemplateDrafts.value = Object.fromEntries(
            res.items
                .filter((setting) => setting.key === 'contract_templates')
                .map((setting) => [setting.key, parseContractTemplates(setting.value)]),
        );
    } catch (e) {
        error.value = getApiErrorMessage(e);
    } finally {
        loading.value = false;
    }
};
const parseContractTemplates = (raw: string): ContractTemplateForm[] => {
    try {
        const items = JSON.parse(raw || '[]');
        if (!Array.isArray(items)) return [];
        return items
            .filter((item) => item && typeof item === 'object')
            .map((item) => ({
                id: String(item.id || '').trim(),
                name: String(item.name || '').trim(),
                document_role_type: normalizeRoleType(item.document_role_type),
                is_open_contract: item.is_open_contract === true,
            }))
            .filter((item) => item.id || item.name);
    } catch {
        return [];
    }
};

const ensureContractTemplateDraft = (setting: ManagerSettingResponse) => {
    if (!contractTemplateDrafts.value[setting.key]) {
        contractTemplateDrafts.value[setting.key] = parseContractTemplates(setting.value);
    }
    return contractTemplateDrafts.value[setting.key] ?? [];
};

const addContractTemplateRow = (setting: ManagerSettingResponse) => {
    ensureContractTemplateDraft(setting).push({
        id: '',
        name: '',
        document_role_type: 'seller_buyer',
        is_open_contract: false,
    });
};

const removeContractTemplateRow = (setting: ManagerSettingResponse, index: number) => {
    ensureContractTemplateDraft(setting).splice(index, 1);
};

const saveContractTemplates = async (setting: ManagerSettingResponse) => {
    const rows = ensureContractTemplateDraft(setting)
        .map((row) => ({
            id: row.id.trim(),
            name: row.name.trim(),
            document_role_type: normalizeRoleType(row.document_role_type),
            is_open_contract: row.is_open_contract === true,
        }))
        .filter((row) => row.id && row.name);
    setting.value = JSON.stringify(rows, null, 2);
    await saveSetting(setting);
};

const saveSetting = async (setting: ManagerSettingResponse) => {
    if (savingKeys.value.has(setting.key)) return;

    savingKeys.value.add(setting.key);
    error.value = '';

    try {
        const payload: ManagerSettingUpdatePayload = {
            value: setting.value,
            description: setting.description || undefined
        };
        const updated = await api.updateManagerSetting(setting.key, payload);

        // Update local state with the exact response
        const index = settings.value.findIndex(s => s.key === updated.key);
        if (index !== -1) {
            settings.value[index] = updated;
        }

        setToast('Настройка сохранена');
    } catch (e) {
        error.value = getApiErrorMessage(e);
        // Reload to revert to actual state in case of error
        await loadSettings();
    } finally {
        savingKeys.value.delete(setting.key);
    }
};

const createSetting = async () => {
    if (!newKey.value.trim() || !newValue.value.trim()) {
        setToast('Заполните ключ и значение', 'error');
        return;
    }
    creating.value = true;
    error.value = '';
    try {
        await ManagerSettingsService.createManagerSetting({
            key: newKey.value.trim(),
            value: newValue.value.trim(),
            description: newDescription.value.trim() || undefined,
        });
        setToast('Настройка создана');
        newKey.value = '';
        newValue.value = '';
        newDescription.value = '';
        showCreateForm.value = false;
        await loadSettings();
    } catch (e) {
        setToast(getApiErrorMessage(e), 'error');
    } finally {
        creating.value = false;
    }
};

const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('ru-RU', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
    });
};

    return {
        settings, loading, error, toast, toastType, savingKeys, contractTemplateDrafts, activeSettingsTab, showCreateForm, newKey, newValue, newDescription, creating, googleAuthStatus, googleAuthLoading, googleAuthBusy, emailLeadSettings, emailLeadSettingsSaving, botSelectionRulesText, botSelectionRulesUpdatedAt, botSelectionRulesSaving, companyRequisites, companyRequisitesSaving, goToBackups, setToast, loadGoogleAuthStatus, openGoogleAuth, loadSettings, saveCompanyRequisites, saveEmailLeadSettings, saveBotSelectionRules, resetBotSelectionRulesDraft, botSelectionRulesError, botSelectionPowerPreview, botSelectionTierPreview, createSetting, formatDate, ensureContractTemplateDraft, addContractTemplateRow, removeContractTemplateRow, saveContractTemplates, saveSetting, DOCUMENT_ROLE_OPTIONS,
    };
};
