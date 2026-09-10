import type { Ref } from 'vue';
import type { ManagerOrderDetailResponse } from '../client';
import type { ProductLine, ProductOption } from '../components/orders/order-editor-types';
import { buildKnownProductClientDescription } from '../components/orders/product-client-description';
import { api } from '../api';
import { confirmDialog } from '../services/ui-feedback';
import { getApiErrorMessage } from '../utils/api-errors';

type Options = {
  order: Readonly<Ref<ManagerOrderDetailResponse | null>>;
  productLines: Ref<ProductLine[]>;
  productLookupById: Ref<Record<number, ProductOption>>;
  mapSmartSearchItemToOption: (item: Record<string, unknown>) => ProductOption;
  rememberProductOption: (option: ProductOption) => void;
  setToast: (message: string, type?: 'success' | 'error') => void;
};

export const createOrderProductDescriptionFiller = ({
  order, productLines, productLookupById, mapSmartSearchItemToOption, rememberProductOption, setToast,
}: Options) => {
  return async (index: number) => {
    const row = productLines.value[index];
    if (!row?.product_id) return;
    const productId = row.product_id;
    const orderId = order.value?.id;
    const isCurrentLine = () => order.value?.id === orderId
      && productLines.value.includes(row)
      && row.product_id === productId;
    let product = productLookupById.value[productId];
    if (!product?.specs || !Object.keys(product.specs).length) {
      try {
        const response = await api.smartSearchProducts(row.product_query, 20);
        if (!isCurrentLine()) return;
        const matched = (Array.isArray(response) ? response : [])
          .map(mapSmartSearchItemToOption)
          .find((item) => item.id === productId);
        if (matched) {
          product = matched;
          rememberProductOption(matched);
        }
      } catch (error) {
        if (!isCurrentLine()) return;
        setToast(`Не удалось получить характеристики: ${getApiErrorMessage(error)}`, 'error');
        return;
      }
    }
    if (!product) {
      setToast('В каталоге не найдены характеристики этого товара.', 'error');
      return;
    }
    const generated = buildKnownProductClientDescription(product);
    if (!generated) {
      setToast('В каталоге нет проверенных характеристик для описания.', 'error');
      return;
    }
    if (row.client_description?.trim()) {
      const confirmed = await confirmDialog({
        title: 'Заменить описание для клиента?',
        description: 'Текущий текст был отредактирован. При заполнении из каталога он будет заменён.',
        confirmText: 'Заменить',
        variant: 'warning',
      });
      if (!confirmed || !isCurrentLine()) return;
    }
    if (!isCurrentLine()) return;
    row.client_description = generated;
  };

};
