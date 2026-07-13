import {
  ManagerEquipmentService,
  type ManagerEquipmentItemResponse,
} from '../../client';

type ListAllCustomerEquipmentOptions = {
  customerId: number;
  customerBranchId?: number | null;
  includeArchived?: boolean;
};

const PAGE_LIMIT = 100;

export const listAllCustomerEquipment = async ({
  customerId,
  customerBranchId = null,
  includeArchived = false,
}: ListAllCustomerEquipmentOptions): Promise<ManagerEquipmentItemResponse[]> => {
  const itemsById = new Map<number, ManagerEquipmentItemResponse>();
  let page = 1;

  while (true) {
    const response = await ManagerEquipmentService.listManagerEquipment(
      customerId,
      customerBranchId,
      page,
      PAGE_LIMIT,
      includeArchived,
    );
    for (const item of response.items || []) itemsById.set(item.id, item);

    const totalPages = Math.max(1, Number(response.meta?.pages || 1));
    if (page >= totalPages) break;
    page += 1;
  }

  return [...itemsById.values()];
};
