import { ref } from 'vue';
import { ManagerSettingsService, type AddressSuggestionItem } from '../client';
import { normalizeAddressQuery } from '../utils/address';

export const useCompanyAddressSuggestion = () => {
  const candidates = ref<AddressSuggestionItem[]>([]);
  const loading = ref(false);
  const error = ref(false);
  const searched = ref(false);
  let requestId = 0;

  const reset = () => {
    requestId += 1;
    candidates.value = [];
    loading.value = false;
    error.value = false;
    searched.value = false;
  };

  const suggest = async (companyName: string) => {
    const query = normalizeAddressQuery(companyName);
    if (!query) return;

    const currentRequestId = ++requestId;
    candidates.value = [];
    loading.value = true;
    error.value = false;
    searched.value = true;
    try {
      const response = await ManagerSettingsService.suggestAddress(query);
      if (currentRequestId !== requestId) return;
      candidates.value = response.items || [];
    } catch (requestError) {
      if (currentRequestId !== requestId) return;
      console.warn('Company address suggestions are temporarily unavailable', requestError);
      error.value = true;
    } finally {
      if (currentRequestId === requestId) loading.value = false;
    }
  };

  return { candidates, loading, error, searched, suggest, reset };
};
