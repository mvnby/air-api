import type { ManagerOrderDetailResponse } from '../../client';
import { OpenAPI } from '../../client/core/OpenAPI';
import { request } from '../../client/core/request';
import type { EquipmentRegistryListResponse, EquipmentRegistryQuery } from './types';

export const listEquipmentRegistry = (query: EquipmentRegistryQuery) => request<EquipmentRegistryListResponse>(
  OpenAPI,
  {
    method: 'GET',
    url: '/api/manager/equipment',
    query: {
      page: query.page,
      limit: query.limit,
      q: query.q?.trim() || undefined,
      attention: query.attention === 'all' ? undefined : query.attention,
    },
    errors: {
      400: 'Некорректный фильтр оборудования',
      422: 'Некорректные параметры запроса',
    },
  },
);

export const createEquipmentMaintenanceOrder = (equipmentId: number) => request<ManagerOrderDetailResponse>(
  OpenAPI,
  {
    method: 'POST',
    url: '/api/manager/equipment/{equipment_id}/maintenance-order',
    path: {
      equipment_id: equipmentId,
    },
    errors: {
      400: 'Не удалось создать заказ на ТО',
      404: 'Оборудование не найдено',
      422: 'Некорректный идентификатор оборудования',
    },
  },
);
