import { describe, expect, it } from 'vitest';
import {
  mapCalendarEvent,
  resolveCalendarEventClick,
} from '../src/views/calendar-event-presentation';

describe('calendar equipment maintenance events', () => {
  it('keeps maintenance reminders fixed while preserving draggable order events', () => {
    const maintenance = mapCalendarEvent({
      id: 'maintenance-18',
      title: 'Позвонить клиенту: ТО',
      start: '2026-09-12T10:00:00+03:00',
      color: '#f59e0b',
      type: 'equipment_maintenance',
      status: 'due',
      order_id: null,
      equipment_id: 18,
      customer_name: 'Анна',
      customer_phone: '+375291234567',
    });
    const order = mapCalendarEvent({
      id: 'order-42',
      title: 'Замер',
      start: '2026-09-12T12:00:00+03:00',
      color: '#0d9488',
      type: 'measurement',
      status: 'new',
      order_id: 42,
    });

    expect(maintenance.editable).toBe(false);
    expect(maintenance.startEditable).toBe(false);
    expect(maintenance.extendedProps).toMatchObject({
      equipment_id: 18,
      customer_phone: '+375291234567',
      order_id: null,
    });
    expect(order.editable).toBe(true);
    expect(order.startEditable).toBe(true);
  });

  it('opens equipment for a maintenance reminder and safely ignores incomplete events', () => {
    expect(resolveCalendarEventClick({
      type: 'equipment_maintenance',
      orderId: null,
      equipmentId: 18,
    })).toEqual({ kind: 'equipment', equipmentId: 18 });
    expect(resolveCalendarEventClick({
      type: 'equipment_maintenance',
      orderId: null,
      equipmentId: null,
    })).toEqual({ kind: 'unavailable' });
    expect(resolveCalendarEventClick({ type: 'installation', orderId: 42 })).toEqual({
      kind: 'order',
      orderId: 42,
    });
  });
});
