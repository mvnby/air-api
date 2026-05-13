export const SITE_CONFIG = {
    phone: "+375 (33) 359-59-59",
    // Auto-generated clean phone if needed, but nice to have explicit
    phoneClean: "+375333595959",
    email: "a@mvn.by",
    address: "г. Витебск, пр-т Победы, 15",

};

export function normalizePhoneForTel(value?: string | null): string {
    const raw = String(value || "").trim();
    if (!raw) return "";

    const digits = raw.replace(/\D/g, "");
    if (!digits) return "";

    return raw.startsWith("+") ? `+${digits}` : digits;
}
