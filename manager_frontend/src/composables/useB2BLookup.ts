import { ref } from 'vue';
import { api } from '../api';
import { getCompanyFromEgr, getBankFromLookup, normalizeUnp, normalizeIban } from '../utils/legal-requisites';
import { getApiErrorMessage } from '../utils/api-errors';

export function useB2BLookup() {
    const isEgrLoading = ref(false);
    const isBankLoading = ref(false);
    const egrError = ref('');
    const bankError = ref('');

    /**
     * Looks up company details by UNP (INN).
     * @param unp 9-digit UNP string
     * @returns Object with fullLegalName and legalAddress if found
     */
    async function lookupCompany(unp: string) {
        const normalized = normalizeUnp(unp);
        if (normalized.length !== 9) return null;

        isEgrLoading.value = true;
        egrError.value = '';
        try {
            const response = await api.getCompanyByUnp(normalized);
            const company = getCompanyFromEgr(response);
            if (!company.fullLegalName) {
                egrError.value = 'Компания не найдена в базе ЕГР';
                return null;
            }
            return company;
        } catch (error) {
            console.error('EGR Lookup error:', error);
            egrError.value = `Ошибка ЕГР: ${getApiErrorMessage(error)}`;
            return null;
        } finally {
            isEgrLoading.value = false;
        }
    }

    /**
     * Looks up bank details by IBAN or BIC.
     * @param search IBAN or BIC string
     * @returns Object with bankName and bic if found
     */
    async function lookupBank(search: string) {
        const normalized = normalizeIban(search);
        if (normalized.length < 8) return null;

        isBankLoading.value = true;
        bankError.value = '';
        try {
            const response = await api.getBankBySearch(normalized);
            const bank = getBankFromLookup(response);
            if (!bank.bankName) {
                bankError.value = 'Банк не найден';
                return null;
            }
            return bank;
        } catch (error) {
            console.error('Bank Lookup error:', error);
            bankError.value = `Ошибка поиска банка: ${getApiErrorMessage(error)}`;
            return null;
        } finally {
            isBankLoading.value = false;
        }
    }

    return {
        lookupCompany,
        lookupBank,
        isEgrLoading,
        isBankLoading,
        egrError,
        bankError,
    };
}
