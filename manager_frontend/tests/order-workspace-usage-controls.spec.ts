import { describe, expect, it, vi } from 'vitest';
import { useOrderWorkspaceUsageControls } from '../src/composables/useOrderWorkspaceUsageControls';

describe('useOrderWorkspaceUsageControls', () => {
  it('reads only the stable marker when a click originates from an SVG child', () => {
    const track = vi.fn();
    const { trackControl } = useOrderWorkspaceUsageControls(track);
    const button = document.createElement('button');
    button.setAttribute('data-order-usage', 'order_product_add');
    const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    button.append(icon);
    document.body.append(button);

    trackControl({ type: 'click', target: icon } as unknown as Event);

    expect(track).toHaveBeenCalledWith('product_add');
    button.remove();
  });

  it('counts a descriptor only on change, never input keystrokes', () => {
    const track = vi.fn();
    const { trackControl } = useOrderWorkspaceUsageControls(track);
    const field = document.createElement('textarea');
    field.setAttribute('data-order-usage', 'order_product_description');

    trackControl({ type: 'input', target: field } as unknown as Event);
    trackControl({ type: 'click', target: field } as unknown as Event);
    trackControl({ type: 'change', target: field } as unknown as Event);

    expect(track).toHaveBeenCalledTimes(1);
    expect(track).toHaveBeenCalledWith('product_description_edit');
  });

  it.each(['document_create', 'payment_add'])('records the actual %s control marker', (marker) => {
    const track = vi.fn();
    const button = document.createElement('button');
    button.setAttribute('data-order-usage', marker);
    useOrderWorkspaceUsageControls(track).trackControl({ type: 'click', target: button } as unknown as Event);
    expect(track).toHaveBeenCalledWith(marker);
  });
});
