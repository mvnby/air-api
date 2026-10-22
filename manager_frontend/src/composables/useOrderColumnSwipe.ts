// Touch-only enhancement on the free space in the column header. Cards and controls
// never begin a gesture; vertical intent is abandoned without preventDefault.
export const useOrderColumnSwipe = (enabled: () => boolean, change: (direction: number) => void) => {
  let start: { id: number; x: number; y: number; time: number; horizontal: boolean } | null = null;
  let suppressClickUntil = 0;
  const cancel = () => { start = null; };
  const down = (event: PointerEvent) => {
    start = null; suppressClickUntil = 0;
    if (!enabled() || event.pointerType !== 'touch' || !event.isPrimary) return;
    const target = event.target as Element | null;
    if (!target?.closest('[data-column-swipe-zone]') || target.closest('article, a, button, input, select, textarea, table, [role="button"], [contenteditable]')) return;
    start = { id: event.pointerId, x: event.clientX, y: event.clientY, time: event.timeStamp, horizontal: false };
  };
  const move = (event: PointerEvent) => {
    if (!start || start.id !== event.pointerId) return;
    const dx = Math.abs(event.clientX - start.x), dy = Math.abs(event.clientY - start.y);
    if (dy > 12 && dy >= dx * 0.75) { cancel(); return; }
    if (!start.horizontal && dx > 16 && dx > dy * 1.5) {
      start.horizontal = true;
      (event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);
    }
  };
  const up = (event: PointerEvent) => {
    const gesture = start; cancel();
    if (!gesture || gesture.id !== event.pointerId || !enabled()) return;
    const dx = event.clientX - gesture.x, dy = event.clientY - gesture.y;
    if (gesture.horizontal && Math.abs(dx) >= 48 && Math.abs(dx) > Math.abs(dy) * 1.5 && event.timeStamp - gesture.time < 800) {
      suppressClickUntil = performance.now() + 400; change(dx < 0 ? 1 : -1);
    }
  };
  const click = (event: MouseEvent) => {
    if (!suppressClickUntil || event.detail === 0 || performance.now() > suppressClickUntil) return;
    suppressClickUntil = 0; event.preventDefault(); event.stopPropagation();
  };
  return { down, move, up, cancel, click };
};
