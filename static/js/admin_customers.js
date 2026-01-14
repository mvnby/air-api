document.addEventListener("DOMContentLoaded", function () {
    console.log("Admin customers JS loaded");

    const innField = document.getElementById("inn");
    const bicField = document.getElementById("bic");
    const ibanField = document.getElementById("iban");

    const nameField = document.getElementById("name");
    const fullLegalNameField = document.getElementById("full_legal_name");
    const legalAddressField = document.getElementById("legal_address");
    const bankNameField = document.getElementById("bank_name");

    function showLoading(field, show) {
        if (field) field.style.opacity = show ? "0.5" : "1";
    }

    if (innField) {
        innField.addEventListener("change", async function () {
            const unp = innField.value.trim();
            if (unp.length === 9) {
                showLoading(innField, true);
                try {
                    const response = await fetch(`/api/admin/proxy/egr?unp=${unp}`);
                    const data = await response.json();
                    if (data && data.row) {
                        const info = data.row;
                        // Fields from real response: vnaimp (full), vnaimk (short)
                        if (fullLegalNameField) fullLegalNameField.value = info.vnaimp || "";
                        if (nameField && !nameField.value) nameField.value = info.vnaimk || info.vnaimp || "";
                        // Address might be in vpadres or another field
                        if (legalAddressField) legalAddressField.value = info.vpadres || "";
                    }
                } catch (e) {
                    console.error("EGR fetch error", e);
                } finally {
                    showLoading(innField, false);
                }
            }
        });
    }

    async function updateBankInfo(bicCode = null, bankPrefix = null) {
        try {
            // Fetching full list is more reliable as search params are picky
            const response = await fetch("/api/admin/proxy/bank");
            const banks = await response.json();

            if (Array.isArray(banks)) {
                let foundBank = null;

                // Priority 1: Active records only (CdControl is null and it's a head office "Банк")
                const activeBanks = banks.filter(b => b && b.CdControl === null);

                if (bicCode) {
                    foundBank = activeBanks.find(b => b.CDBank === bicCode);
                    // Fallback to non-active if really needed (unlikely)
                    if (!foundBank) foundBank = banks.find(b => b.CDBank === bicCode);
                } else if (bankPrefix) {
                    // Match by first 4 characters from IBAN
                    // Prioritize head offices "Банк" among active ones
                    foundBank = activeBanks.find(b => b.CDBank && b.CDBank.startsWith(bankPrefix) && b.typ === "Банк");
                    // Fallback to any active with this prefix
                    if (!foundBank) foundBank = activeBanks.find(b => b.CDBank && b.CDBank.startsWith(bankPrefix));
                }

                if (foundBank) {
                    if (bankNameField) {
                        bankNameField.value = `${foundBank.NmBankShort}, ${foundBank.AdrBank}`;
                    }
                    if (bicField) {
                        // Always update BIC if it's from prefix (IBAN)
                        bicField.value = foundBank.CDBank;
                    }
                }
            }
        } catch (e) {
            console.error("Bank fetch error", e);
        }
    }

    if (bicField) {
        bicField.addEventListener("change", function () {
            const bic = bicField.value.trim().toUpperCase();
            if (bic.length >= 8) {
                updateBankInfo(bic);
            }
        });
    }

    if (ibanField) {
        ibanField.addEventListener("change", function () {
            const iban = ibanField.value.trim().toUpperCase();
            if (iban.length === 28 && iban.startsWith("BY")) {
                const bankPrefix = iban.substring(4, 8); // 5th to 8th chars
                updateBankInfo(null, bankPrefix);
            }
        });
    }
});
