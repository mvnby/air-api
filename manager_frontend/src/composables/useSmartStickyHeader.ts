import { nextTick, onBeforeUnmount, ref, watch, type Ref } from 'vue';

export const STICKY_HEADER_TOP_ZONE_PX = 80;
export const STICKY_HEADER_COLLAPSE_TRAVEL_PX = 72;
export const STICKY_HEADER_EXPAND_TRAVEL_PX = 32;
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
) => Math.max(0, rawScrollTop + compensation);

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

export const useSmartStickyHeader = (scrollContainer: Ref<HTMLElement | null>) => {
  const compact = ref(false);
  let motionState = initialStickyHeaderState();
  let frameId: number | null = null;
  let layoutFrameId: number | null = null;
  let layoutSyncGeneration = 0;
  let layoutSyncPending = false;
  let scrollCompensation = 0;
  let currentContainer: HTMLElement | null = null;

  const syncAfterLayoutChange = (logicalScrollTop: number, targetCompact: boolean) => {
    layoutSyncPending = true;
    const generation = ++layoutSyncGeneration;

    void nextTick(() => {
      if (generation !== layoutSyncGeneration || !currentContainer) return;
      layoutFrameId = window.requestAnimationFrame(() => {
        layoutFrameId = null;
        if (generation !== layoutSyncGeneration || !currentContainer) return;
        const rawScrollTop = currentContainer.scrollTop;
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

  const detach = () => {
    currentContainer?.removeEventListener('scroll', onScroll);
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
  };

  const reset = () => {
    const scrollTop = currentContainer?.scrollTop || 0;
    scrollCompensation = 0;
    motionState = initialStickyHeaderState(scrollTop);
    compact.value = false;
  };

  watch(scrollContainer, (container) => {
    detach();
    currentContainer = container;
    reset();
    currentContainer?.addEventListener('scroll', onScroll, { passive: true });
  }, { immediate: true, flush: 'post' });

  onBeforeUnmount(detach);

  return { compact, reset };
};
