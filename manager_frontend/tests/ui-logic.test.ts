import {
  ADDRESS_SUGGEST_DEBOUNCE_MS,
  buildYandexMapUrl,
  hasEnoughAddressCharacters,
} from '../src/utils/address';
import {
  STICKY_HEADER_COLLAPSE_TRAVEL_PX,
  STICKY_HEADER_EXPAND_TRAVEL_PX,
  getStickyHeaderLayoutCompensation,
  getStickyHeaderLogicalScrollTop,
  initialStickyHeaderState,
  reduceStickyHeaderScroll,
  syncStickyHeaderAfterLayout,
} from '../src/composables/useSmartStickyHeader';

const assert = (condition: unknown, message: string) => {
  if (!condition) throw new Error(message);
};

assert(ADDRESS_SUGGEST_DEBOUNCE_MS === 800, 'address debounce must remain 800 ms');
assert(!hasEnoughAddressCharacters('  а б  '), 'spaces must not count as significant address characters');
assert(hasEnoughAddressCharacters('Мин'), 'three significant characters must enable suggestions');
assert(buildYandexMapUrl('') === '', 'empty address must not create a map link');
assert(
  buildYandexMapUrl('Минск, Ленина 1').includes(encodeURIComponent('Минск, Ленина 1')),
  'manual address must create a text-based map link',
);
assert(
  buildYandexMapUrl('old address', { latitude: 53.9, longitude: 27.56 }).includes('ll=27.56,53.9'),
  'trusted coordinates must take priority in the map link',
);

let header = initialStickyHeaderState();
assert(!header.compact, 'header must open expanded');
header = reduceStickyHeaderScroll(header, 60);
assert(!header.compact, 'header must stay expanded in the top zone');
header = reduceStickyHeaderScroll(header, 90);
assert(!header.compact, 'one short downward movement must not collapse the header');
header = reduceStickyHeaderScroll(header, 90 + STICKY_HEADER_COLLAPSE_TRAVEL_PX);
assert(header.compact, 'sustained downward movement must collapse the header');
header = reduceStickyHeaderScroll(header, 90 + STICKY_HEADER_COLLAPSE_TRAVEL_PX - 8);
assert(header.compact, 'minor upward jitter must not expand the header');
header = reduceStickyHeaderScroll(header, 90 + STICKY_HEADER_COLLAPSE_TRAVEL_PX - STICKY_HEADER_EXPAND_TRAVEL_PX);
assert(!header.compact, 'meaningful upward movement must expand the header');
header = reduceStickyHeaderScroll(header, 20);
assert(!header.compact, 'returning to the top must keep the header expanded');

header = reduceStickyHeaderScroll(initialStickyHeaderState(90), 90 + STICKY_HEADER_COLLAPSE_TRAVEL_PX);
assert(header.compact, 'header must collapse before layout synchronization');
const compactedRawScrollTop = 62;
const compactedCompensation = getStickyHeaderLayoutCompensation(
  header.lastScrollTop,
  compactedRawScrollTop,
  header.compact,
);
header = syncStickyHeaderAfterLayout(
  header,
  getStickyHeaderLogicalScrollTop(compactedRawScrollTop, compactedCompensation),
);
assert(header.compact, 'layout-induced scroll correction must preserve compact mode');
assert(
  header.lastScrollTop === 90 + STICKY_HEADER_COLLAPSE_TRAVEL_PX,
  'logical scroll position must stay stable after compaction',
);
assert(header.upwardTravel === 0, 'layout synchronization must not count as upward user travel');
header = reduceStickyHeaderScroll(
  header,
  getStickyHeaderLogicalScrollTop(54, compactedCompensation),
);
assert(header.compact, 'small upward user travel after synchronization must keep compact mode');
header = reduceStickyHeaderScroll(
  header,
  getStickyHeaderLogicalScrollTop(20, compactedCompensation),
);
assert(!header.compact, 'meaningful upward user travel must still expand the compensated header');
assert(
  getStickyHeaderLayoutCompensation(header.lastScrollTop, 120, header.compact) === 0,
  'expanded mode must clear layout compensation',
);

console.log('Address and sticky header UI logic tests passed');
