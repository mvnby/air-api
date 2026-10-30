import { nextTick, onBeforeUnmount, ref, watch, type Ref } from 'vue';

export const STICKY_HEADER_TOP_ZONE_PX = 80;
export const STICKY_HEADER_COLLAPSE_TRAVEL_PX = 72;
export const STICKY_HEADER_EXPAND_TRAVEL_PX = 32;
export const STICKY_HEADER_RESIZE_DURATION_MS = 360;
const MIN_SCROLL_DELTA_PX = 2;

export type StickyHeaderMotionState = {
  compact: boolean;
  lastScrollTop: number;
  downwardTravel: number;
  upwardTravel: number;
};
export const initialStickyHeaderState = (scrollTop = 0): StickyHeaderMotionState => ({
  compact: false,
  lastScrollTop: Math.max(0, scrollTop),
  downwardTravel: 0,
  upwardTravel: 0,
});

export const syncStickyHeaderAfterLayout = (
  state: StickyHeaderMotionState,
  scrollTop: number,
): StickyHeaderMotionState => ({
  ...state,
  lastScrollTop: Math.max(0, scrollTop),
  downwardTravel: 0,
  upwardTravel: 0,
});

export const getStickyHeaderLogicalScrollTop = (
  rawScrollTop: number,
  compensation: number,
) => rawScrollTop <= 0 ? 0 : Math.max(0, rawScrollTop + compensation);

export const getStickyHeaderLayoutCompensation = (
  logicalScrollTop: number,
  rawScrollTop: number,
  compact: boolean,
) => compact ? logicalScrollTop - rawScrollTop : 0;

export const reduceStickyHeaderScroll = (
  state: StickyHeaderMotionState,
  rawScrollTop: number,
): StickyHeaderMotionState => {
  const scrollTop = Math.max(0, rawScrollTop);
  const delta = scrollTop - state.lastScrollTop;

  if (scrollTop <= STICKY_HEADER_TOP_ZONE_PX) {
    return initialStickyHeaderState(scrollTop);
  }
  if (Math.abs(delta) < MIN_SCROLL_DELTA_PX) {
    return { ...state, lastScrollTop: scrollTop };
  }

  if (delta > 0) {
    const downwardTravel = state.downwardTravel + delta;
    return {
      compact: state.compact || downwardTravel >= STICKY_HEADER_COLLAPSE_TRAVEL_PX,
      lastScrollTop: scrollTop,
      downwardTravel,
      upwardTravel: 0,
    };
  }

  const upwardTravel = state.upwardTravel + Math.abs(delta);
  return {
    compact: state.compact && upwardTravel < STICKY_HEADER_EXPAND_TRAVEL_PX,
    lastScrollTop: scrollTop,
    downwardTravel: 0,
    upwardTravel,
  };
};

export const useSmartStickyHeader = (scrollContainer: Ref<HTMLElement | null>, options: { retainCompactWhenContentFits?: boolean } = {}) => {
  const compact = ref(false);
  let motionState = initialStickyHeaderState();
  let frameId: number | null = null;
  let layoutFrameId: number | null = null;
  let layoutTimerId: number | null = null;
  let layoutSyncGeneration = 0;
  let layoutSyncPending = false;
  let scrollCompensation = 0;
  let currentContainer: HTMLElement | null = null;
  let upwardIntent = 0;
  let touchY: number | null = null;

  const cancelLayoutSync = () => {
    layoutSyncGeneration += 1;
    layoutSyncPending = false;
    if (layoutTimerId !== null) window.clearTimeout(layoutTimerId);
    if (layoutFrameId !== null) window.cancelAnimationFrame(layoutFrameId);
    layoutTimerId = layoutFrameId = null;
  };

  const syncAfterLayoutChange = (logicalScrollTop: number, targetCompact: boolean) => {
    layoutSyncPending = true;
    const generation = ++layoutSyncGeneration;

    void nextTick(() => {
      if (generation !== layoutSyncGeneration || !currentContainer) return;
      const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      layoutTimerId = window.setTimeout(() => {
        layoutTimerId = null;
        layoutFrameId = window.requestAnimationFrame(() => {
          layoutFrameId = null;
          if (generation !== layoutSyncGeneration || !currentContainer) return;
          const rawScrollTop = currentContainer.scrollTop;
          // A manager can scroll back while the header is resizing. Those
          // events are deferred, but the real top must never be compensated
          // into an imaginary offset that leaves the controls hidden.
          if (rawScrollTop <= 0 && !(options.retainCompactWhenContentFits && targetCompact && currentContainer.scrollHeight <= currentContainer.clientHeight)) {
            scrollCompensation = 0;
            motionState = initialStickyHeaderState();
            compact.value = false;
            layoutSyncPending = false;
            return;
          }
          scrollCompensation = getStickyHeaderLayoutCompensation(
            logicalScrollTop,
            rawScrollTop,
            targetCompact,
          );
          motionState = syncStickyHeaderAfterLayout(
            motionState,
            targetCompact
              ? getStickyHeaderLogicalScrollTop(rawScrollTop, scrollCompensation)
              : rawScrollTop,
          );
          layoutSyncPending = false;
        });
      }, reducedMotion ? 0 : STICKY_HEADER_RESIZE_DURATION_MS);
    });
  };

  const updateFromScroll = () => {
    frameId = null;
    if (!currentContainer || layoutSyncPending) return;
    const wasCompact = motionState.compact;
    const logicalScrollTop = getStickyHeaderLogicalScrollTop(
      currentContainer.scrollTop,
      scrollCompensation,
    );
    motionState = reduceStickyHeaderScroll(motionState, logicalScrollTop);
    compact.value = motionState.compact;
    if (wasCompact !== motionState.compact) {
      syncAfterLayoutChange(motionState.lastScrollTop, motionState.compact);
    }
  };

  const onScroll = () => {
    if (layoutSyncPending) return;
    if (frameId === null) frameId = window.requestAnimationFrame(updateFromScroll);
  };

  // Resizing can consume all overflow. Wheel/touch intent still reveals chrome,
  // even when the browser can no longer produce an upward scroll event.
  const revealFromIntent = (travel: number) => {
    upwardIntent = travel > 0 ? upwardIntent + travel : 0;
    if (!compact.value || upwardIntent < STICKY_HEADER_EXPAND_TRAVEL_PX) return;
    cancelLayoutSync();
    scrollCompensation = 0;
    motionState = initialStickyHeaderState(currentContainer?.scrollTop || 0);
    compact.value = false;
    syncAfterLayoutChange(motionState.lastScrollTop, false);
    upwardIntent = 0;
  };
  const onWheel = (event: WheelEvent) => revealFromIntent(-event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? (currentContainer?.clientHeight || 1) : 1));
  const onTouchStart = (event: TouchEvent) => { touchY = event.touches[0]?.clientY ?? null; upwardIntent = 0; };
  const onTouchMove = (event: TouchEvent) => {
    const next = event.touches[0]?.clientY ?? null;
    if (next !== null && touchY !== null) revealFromIntent(next - touchY);
    touchY = next;
  };

  const detach = () => {
    currentContainer?.removeEventListener('scroll', onScroll);
    currentContainer?.removeEventListener('wheel', onWheel);
    currentContainer?.removeEventListener('touchstart', onTouchStart);
    currentContainer?.removeEventListener('touchmove', onTouchMove);
    currentContainer = null;
    layoutSyncPending = false;
    scrollCompensation = 0;
    layoutSyncGeneration += 1;
    if (frameId !== null) {
      window.cancelAnimationFrame(frameId);
      frameId = null;
    }
    if (layoutFrameId !== null) {
      window.cancelAnimationFrame(layoutFrameId);
      layoutFrameId = null;
    }
    if (layoutTimerId !== null) {
      window.clearTimeout(layoutTimerId);
      layoutTimerId = null;
    }
  };

  const reset = () => {
    const wasCompact = compact.value;
    cancelLayoutSync();
    upwardIntent = 0;
    const scrollTop = currentContainer?.scrollTop || 0;
    scrollCompensation = 0;
    motionState = initialStickyHeaderState(scrollTop);
    compact.value = false;
    if (wasCompact && currentContainer) syncAfterLayoutChange(scrollTop, false);
  };

  watch(scrollContainer, (container) => {
    detach();
    currentContainer = container;
    reset();
    currentContainer?.addEventListener('scroll', onScroll, { passive: true });
    if (options.retainCompactWhenContentFits) {
      currentContainer?.addEventListener('wheel', onWheel, { passive: true });
      currentContainer?.addEventListener('touchstart', onTouchStart, { passive: true });
      currentContainer?.addEventListener('touchmove', onTouchMove, { passive: true });
    }
  }, { immediate: true, flush: 'post' });

  onBeforeUnmount(detach);

  return { compact, reset };
};
