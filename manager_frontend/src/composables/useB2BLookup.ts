import { getCurrentScope, onScopeDispose, ref, watch, type WatchSource } from 'vue';
import { api } from '../api';
import { getCompanyFromEgr, getBankFromLookup, normalizeUnp, normalizeIban } from '../utils/legal-requisites';
import { getApiErrorMessage } from '../utils/api-errors';

type LookupContext = {
    companyInput?: () => string;
    bankInput?: () => string;
    // Sources identify the current customer, customer type and editing session.
    context?: WatchSource[];
};

export function useB2BLookup(context: LookupContext = {}) {
    const isEgrLoading = ref(false);
    const isBankLoading = ref(false);
    const egrError = ref('');
    const bankError = ref('');
    let companyRequest = 0;
    let bankRequest = 0;
    let disposed = false;

    function invalidateCompany() {
        companyRequest += 1;
        isEgrLoading.value = false;
        egrError.value = '';
    }
    function invalidateBank() {
        bankRequest += 1;
        isBankLoading.value = false;
        bankError.value = '';
    }
    function invalidateLookups() {
        invalidateCompany();
        invalidateBank();
    }

    // Invalidate on typing, even without another blur, including A → B → A.
    // Synchronous watchers prevent an already-resolved promise from winning a
    // race against a queued Vue watcher for a changed input or editing session.
    if (context.companyInput) watch(() => normalizeUnp(context.companyInput!()), invalidateCompany, { flush: 'sync' });
    if (context.bankInput) watch(() => normalizeIban(context.bankInput!()), invalidateBank, { flush: 'sync' });
    if (context.context) watch(context.context, invalidateLookups, { flush: 'sync' });
    if (getCurrentScope()) onScopeDispose(() => {
        disposed = true;
        invalidateLookups();
    });

    /**
     * Looks up company details by UNP (INN).
     * @param unp 9-digit UNP string
     * @param apply Run field updates here, not after await: the input/session can
     * change between resolving this promise and resuming its caller.
     * @returns Object with fullLegalName and legalAddress if found
     */
    async function lookupCompany(unp: string, apply?: (company: ReturnType<typeof getCompanyFromEgr>) => void) {
        invalidateCompany();
        const request = companyRequest;
        const normalized = normalizeUnp(unp);
        const isCurrent = () => !disposed && request === companyRequest
            && (!context.companyInput || normalizeUnp(context.companyInput()) === normalized);
        if (!/^\d{9}$/.test(normalized) || !isCurrent()) return null;

        isEgrLoading.value = true;
        egrError.value = '';
        try {
            const response = await api.getCompanyByUnp(normalized);
            if (!isCurrent()) return null;
            const company = getCompanyFromEgr(response);
            if (!company.fullLegalName) {
                egrError.value = 'Компания не найдена в базе ЕГР';
                return null;
            }
            apply?.(company);
            return company;
        } catch (error) {
            if (!isCurrent()) return null;
            console.error('EGR Lookup error:', error);
            egrError.value = `Ошибка ЕГР: ${getApiErrorMessage(error)}`;
            return null;
        } finally {
            if (isCurrent()) isEgrLoading.value = false;
        }
    }

    /**
     * Looks up bank details by IBAN or BIC.
     * @param search IBAN or BIC string
     * @param apply Run field updates here, not after await: the input/session can
     * change between resolving this promise and resuming its caller.
     * @returns Object with bankName and bic if found
     */
    async function lookupBank(search: string, apply?: (bank: ReturnType<typeof getBankFromLookup>) => void) {
        invalidateBank();
        const request = bankRequest;
        const normalized = normalizeIban(search);
        const isCurrent = () => !disposed && request === bankRequest
            && (!context.bankInput || normalizeIban(context.bankInput()) === normalized);
        if (normalized.length < 8 || !isCurrent()) return null;

        isBankLoading.value = true;
        bankError.value = '';
        try {
            const response = await api.getBankBySearch(normalized);
            if (!isCurrent()) return null;
            const bank = getBankFromLookup(response);
            if (!bank.bankName) {
                bankError.value = 'Банк не найден';
                return null;
            }
            apply?.(bank);
            return bank;
        } catch (error) {
            if (!isCurrent()) return null;
            console.error('Bank Lookup error:', error);
            bankError.value = `Ошибка поиска банка: ${getApiErrorMessage(error)}`;
            return null;
        } finally {
            if (isCurrent()) isBankLoading.value = false;
        }
    }

    return {
        lookupCompany,
        lookupBank,
        invalidateLookups,
        isEgrLoading,
        isBankLoading,
        egrError,
        bankError,
    };
}
