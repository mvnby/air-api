import type { ManagerCatalogCustomerItemResponse } from '../client';

export const CUSTOMER_UPDATED_EVENT = 'manager:customer-updated';

export type CustomerUpdatedEventPayload = {
  customer: ManagerCatalogCustomerItemResponse;
};

export function dispatchCustomerUpdated(customer: ManagerCatalogCustomerItemResponse) {
  window.dispatchEvent(
    new CustomEvent<CustomerUpdatedEventPayload>(CUSTOMER_UPDATED_EVENT, {
      detail: { customer },
    }),
  );
}

