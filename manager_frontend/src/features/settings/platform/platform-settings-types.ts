export type DocumentRoleType = 'seller_buyer' | 'executor_customer' | 'contractor_customer' | 'seller_payer' | 'executor_payer';
export type SettingsTab = 'general' | 'documentTemplates' | 'repairComplaints' | 'emailLeads' | 'botSelection';
export type ManagedDocumentType = 'contract' | 'act' | 'invoice' | 'retail_receipt' | 'service_act' | 'maintenance_service_act' | 'warranty_certificate' | 'defect_act';
export type DocumentTemplateFileOption = {
    id: string;
    name: string;
    mime_type?: string | null;
    created_time?: string | null;
};
export interface ContractTemplateForm {
    id: string;
    name: string;
    document_role_type: DocumentRoleType;
    is_open_contract: boolean;
}
export type DocumentTemplateForm = {
    document_template_id?: number | null;
    name: string;
    doc_type: ManagedDocumentType;
    google_template_id: string;
    document_role_type: DocumentRoleType;
    description: string;
    base_document_type_label: string;
    is_default: boolean;
    is_active: boolean;
    is_open_contract: boolean;
    client_restricted: boolean;
    sort_order: number;
    customer_ids: number[];
    linked_contract_template_ids: number[];
    linked_act_template_ids: number[];
};
export type RepairComplaintPresetForm = {
    id?: number | null;
    complaint_group: string;
    customer_phrase: string;
    document_wording: string;
    likely_diagnosis: string;
    is_favorite: boolean;
    is_active: boolean;
    sort_order: number;
    comment: string;
};
export const DOCUMENT_ROLE_OPTIONS: Array<{ value: DocumentRoleType; label: string }> = [
    { value: 'seller_buyer', label: 'Продавец / Покупатель' },
    { value: 'seller_payer', label: 'Продавец / Плательщик' },
    { value: 'executor_customer', label: 'Исполнитель / Заказчик' },
    { value: 'executor_payer', label: 'Исполнитель / Плательщик' },
    { value: 'contractor_customer', label: 'Подрядчик / Заказчик' },
];
export const EMAIL_LEAD_AUTO_IMPORT_KEY = 'mail_lead_auto_import_enabled';
export const EMAIL_LEAD_INTERVAL_KEY = 'mail_lead_import_interval_minutes';
export const EMAIL_LEAD_LAST_IMPORT_KEY = 'mail_lead_last_import_at';
export const EMAIL_LEAD_SETTING_KEYS = new Set([
    EMAIL_LEAD_AUTO_IMPORT_KEY,
    EMAIL_LEAD_INTERVAL_KEY,
    EMAIL_LEAD_LAST_IMPORT_KEY,
    'mail_lead_import_limit',
]);
export const BOT_SELECTION_RULES_KEY = 'bot_product_selection_rules';
export const BOT_SELECTION_RULES_DESCRIPTION = 'JSON-правила подбора кондиционеров для staff Telegram-бота';
export const COMPANY_REQUISITE_KEYS = [
    'company_name',
    'company_full_legal_name',
    'company_unp',
    'company_legal_address',
    'company_bank_name',
    'company_iban',
    'company_bic',
    'company_signer_position',
    'company_signer_name',
    'company_acting_basis',
] as const;
export const COMPANY_REQUISITE_DESCRIPTIONS: Record<(typeof COMPANY_REQUISITE_KEYS)[number], string> = {
    company_name: 'Краткое название нашей организации для внутренних списков.',
    company_full_legal_name: 'Полное наименование нашей организации для документов.',
    company_unp: 'УНП нашей организации.',
    company_legal_address: 'Юридический адрес нашей организации.',
    company_bank_name: 'Банк нашей организации.',
    company_iban: 'IBAN расчетного счета нашей организации.',
    company_bic: 'BIC банка нашей организации.',
    company_signer_position: 'Должность подписанта в документах.',
    company_signer_name: 'ФИО подписанта в документах.',
    company_acting_basis: 'Основание полномочий подписанта.',
};
export const DEFAULT_COMPANY_REQUISITES = {
    company_name: 'ИП Янулевич Д.В.',
    company_full_legal_name: 'ИП Янулевич Д.В.',
    company_unp: '',
    company_legal_address: '',
    company_bank_name: '',
    company_iban: '',
    company_bic: '',
    company_signer_position: '',
    company_signer_name: 'Янулевич Д.В.',
    company_acting_basis: '',
};
export const DEFAULT_BOT_SELECTION_RULES = {
    power_classes: {
        '7': { kw: 1.9, area_min: 15, area_max: 24 },
        '9': { kw: 2.6, area_min: 25, area_max: 32 },
        '12': { kw: 3.5, area_min: 33, area_max: 42 },
        '18': { kw: 5.3, area_min: 45, area_max: 60 },
        '24': { kw: 7.0, area_min: 65, area_max: 80 },
        '36': { kw: 10.5, area_min: 90, area_max: 110 },
    },
    default_tag_slugs: ['cat-household'],
    tiers: {
        mixed: [
            { key: 'budget', label: 'Бюджетнее', is_inverter: false, sort: 'price' },
            { key: 'optimal', label: 'Оптимально', is_inverter: true, sort: 'balanced' },
            { key: 'premium', label: 'Премиум', is_inverter: true, sort: 'premium' },
        ],
        inverter_only: [
            { key: 'optimal', label: 'Оптимально', is_inverter: true, sort: 'balanced' },
            { key: 'premium', label: 'Премиум', is_inverter: true, sort: 'premium' },
        ],
        onoff_only: [
            { key: 'onoff', label: 'ON-OFF', is_inverter: false, sort: 'price' },
        ],
    },
};

export const DOCUMENT_TYPE_OPTIONS: Array<{ value: ManagedDocumentType; label: string; addLabel: string }> = [
    { value: 'contract', label: 'Договор', addLabel: 'Договор' },
    { value: 'invoice', label: 'Счет / счет-договор', addLabel: 'Счет' },
    { value: 'retail_receipt', label: 'Товарный чек', addLabel: 'Товарный чек' },
    { value: 'service_act', label: 'Заказ-акт', addLabel: 'Заказ-акт' },
    { value: 'maintenance_service_act', label: 'Заказ-акт ТО', addLabel: 'Заказ-акт ТО' },
    { value: 'warranty_certificate', label: 'Гарантийный талон', addLabel: 'Гарантийный талон' },
    { value: 'act', label: 'Акт', addLabel: 'Акт' },
    { value: 'defect_act', label: 'Дефектный акт', addLabel: 'Дефектный акт' },
];
export const REPAIR_COMPLAINT_GROUP_OPTIONS = [
    { value: 'water_drainage', label: 'Вода / дренаж' },
    { value: 'noise_vibration', label: 'Шум / вибрация' },
    { value: 'cooling', label: 'Охлаждение' },
    { value: 'smell_contamination', label: 'Запах / загрязнение' },
    { value: 'control_electronics', label: 'Управление / электроника' },
    { value: 'freezing', label: 'Обмерзание' },
    { value: 'shutdown_error', label: 'Отключение / ошибка' },
    { value: 'other', label: 'Другое' },
];

export const normalizeRoleType = (value: unknown): DocumentRoleType => {
    const raw = String(value || '').trim();
    if (raw === 'executor_customer' || raw === 'contractor_customer' || raw === 'seller_payer' || raw === 'executor_payer') return raw;
    return 'seller_buyer';
};

export const normalizeDocumentType = (value: unknown): ManagedDocumentType => {
    const raw = String(value || '').trim();
    if (raw === 'act' || raw === 'invoice' || raw === 'retail_receipt' || raw === 'service_act' || raw === 'maintenance_service_act' || raw === 'warranty_certificate' || raw === 'defect_act') return raw;
    return 'contract';
};
