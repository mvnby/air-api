export type CalendarEventInput = {
  id: string;
  title: string;
  start: string;
  allDay?: boolean;
  color: string;
  type: string;
  status: string;
  order_id?: number | null;
  equipment_id?: number | null;
  customer_name?: string | null;
  customer_phone?: string | null;
  address?: string | null;
};

type CalendarEventClickInput = {
  type?: string | null;
  orderId?: unknown;
  equipmentId?: unknown;
};

export type CalendarEventClickTarget =
  | { kind: 'order'; orderId: number }
  | { kind: 'equipment'; equipmentId: number }
  | { kind: 'unavailable' };

export const isEquipmentMaintenanceEvent = (type?: string | null) => type === 'equipment_maintenance';

export const mapCalendarEvent = (event: CalendarEventInput) => {
  const isMaintenance = isEquipmentMaintenanceEvent(event.type);

  return {
    id: event.id,
    title: event.title,
    start: event.start,
    allDay: event.allDay,
    backgroundColor: event.color,
    borderColor: event.color,
    editable: !isMaintenance,
    startEditable: !isMaintenance,
    extendedProps: {
      order_id: event.order_id,
      equipment_id: event.equipment_id,
      type: event.type,
      customer_name: event.customer_name,
      customer_phone: event.customer_phone,
      address: event.address,
      status: event.status,
    },
  };
};

const asPositiveId = (value: unknown): number | null => (
  typeof value === 'number' && Number.isSafeInteger(value) && value > 0 ? value : null
);

export const resolveCalendarEventClick = (event: CalendarEventClickInput): CalendarEventClickTarget => {
  if (isEquipmentMaintenanceEvent(event.type)) {
    const equipmentId = asPositiveId(event.equipmentId);
    return equipmentId ? { kind: 'equipment', equipmentId } : { kind: 'unavailable' };
  }

  const orderId = asPositiveId(event.orderId);
  return orderId ? { kind: 'order', orderId } : { kind: 'unavailable' };
};
