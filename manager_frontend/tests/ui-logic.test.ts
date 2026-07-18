import {
  ADDRESS_SUGGEST_DEBOUNCE_MS,
  buildYandexMapUrl,
  hasEnoughAddressCharacters,
} from '../src/utils/address';
import {
  STICKY_HEADER_COLLAPSE_TRAVEL_PX,
  STICKY_HEADER_EXPAND_TRAVEL_PX,
  STICKY_HEADER_RESIZE_DURATION_MS,
  getStickyHeaderLayoutCompensation,
  getStickyHeaderLogicalScrollTop,
  initialStickyHeaderState,
  reduceStickyHeaderScroll,
  syncStickyHeaderAfterLayout,
} from '../src/composables/useSmartStickyHeader';
import { uploadSequentially } from '../src/utils/sequential-upload';
import {
  CLIENT_IMAGE_MIN_OPTIMIZE_BYTES,
  needsImageOptimization,
  optimizedImageFileName,
  shouldOptimizeImageUpload,
} from '../src/utils/image-upload-optimization';
import { compactLegalName } from '../src/components/orders/order-utils';
import {
  buildMeasurementSummary,
  buildOrderWorkspaceViewModel,
} from '../src/components/orders/order-workspace';
import {
  isProposalRevisionLocked,
  proposalPrimaryAction,
  proposalStatusLabel,
} from '../src/components/orders/proposal-lifecycle';
import {
  applyCatalogQualityView,
  createDefaultCatalogQualityState,
  parseCatalogQualityState,
  serializeCatalogQualityState,
} from '../src/components/catalog-quality/catalog-quality-state';
import { countLabel } from '../src/components/catalog-quality/catalog-quality-copy';

const assert = (condition: unknown, message: string) => {
  if (!condition) throw new Error(message);
};

assert(ADDRESS_SUGGEST_DEBOUNCE_MS === 800, 'address debounce must remain 800 ms');
assert(
  STICKY_HEADER_RESIZE_DURATION_MS >= 300 && STICKY_HEADER_RESIZE_DURATION_MS <= 450,
  'sticky header resize must stay quick but perceptible',
);
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

const uploadOrder: number[] = [];
const uploadProgress: string[] = [];
const uploadResults = await uploadSequentially(
  [1, 2, 3],
  async (item) => {
    uploadOrder.push(item);
    return item * 10;
  },
  (_result, progress) => uploadProgress.push(`${progress.completed}/${progress.total}`),
);
assert(uploadOrder.join(',') === '1,2,3', 'media files must upload sequentially in selection order');
assert(uploadResults.join(',') === '10,20,30', 'sequential upload must return every response');
assert(uploadProgress.join(',') === '1/3,2/3,3/3', 'sequential upload must report completed file count');
assert(
  shouldOptimizeImageUpload({ type: 'image/png', size: CLIENT_IMAGE_MIN_OPTIMIZE_BYTES }),
  'raster images must be eligible for browser preparation',
);
assert(
  !shouldOptimizeImageUpload({ type: 'image/svg+xml', size: CLIENT_IMAGE_MIN_OPTIMIZE_BYTES * 4 }),
  'vector images must not be rasterized by client optimization',
);
assert(optimizedImageFileName('outside.unit.PNG') === 'outside.unit.webp', 'optimized files must use WebP names');
assert(
  needsImageOptimization(5000, 1200, CLIENT_IMAGE_MIN_OPTIMIZE_BYTES / 2),
  'oversized pixel dimensions must be optimized even when the encoded file is small',
);

assert(
  compactLegalName('Общество с ограниченной ответственностью "НПП Юни"') === 'ООО "НПП Юни"',
  'common legal forms must be compact in narrow order surfaces',
);
assert(
  compactLegalName('Унитарное предприятие «Торговый дом»') === 'УП «Торговый дом»',
  'unitary enterprise names must be compact in narrow order surfaces',
);
assert(
  compactLegalName('ЗАО «Витебскагропродукт»') === 'ЗАО «Витебскагропродукт»',
  'already compact legal names must remain unchanged',
);

const qualityState = parseCatalogQualityState(
  '?equipmentType=cat-multi&brandId=7&seriesId=18&supplierState=in_stock&view=table&page=3&limit=100',
);
assert(qualityState.equipmentType === 'cat-multi', 'catalog quality equipment type must restore from URL');
assert(qualityState.seriesId === '18', 'catalog quality series cascade must restore from URL');
assert(qualityState.view === 'table' && qualityState.page === 3, 'catalog quality workspace state must restore from URL');
const serializedQualityState = serializeCatalogQualityState(qualityState);
assert(serializedQualityState.includes('equipmentType=cat-multi'), 'active catalog filters must be shareable in URL');
assert(!serializedQualityState.includes('onlyProblems=true'), 'default catalog filters must stay out of URL');
const invalidQualityState = parseCatalogQualityState('?view=broken&limit=13&page=-2&supplierState=broken');
assert(invalidQualityState.view === 'cards' && invalidQualityState.limit === 50, 'invalid catalog URL values must fall back safely');
const savedQualityView = applyCatalogQualityView(
  { ...createDefaultCatalogQualityState(), view: 'table', limit: 100 },
  { availability: 'in_stock', category: 'media', page: 9 },
);
assert(savedQualityView.availability === 'in_stock' && savedQualityView.category === 'media', 'saved catalog view must apply its filters');
assert(savedQualityView.view === 'table' && savedQualityView.limit === 100, 'saved catalog view must preserve personal display preferences');
assert(savedQualityView.page === 1, 'saved catalog view must restart pagination');
assert(countLabel(1, 'поставщик', 'поставщика', 'поставщиков') === '1 поставщик', 'catalog counts must use singular form');
assert(countLabel(3, 'поставщик', 'поставщика', 'поставщиков') === '3 поставщика', 'catalog counts must use paucal form');
assert(countLabel(12, 'поставщик', 'поставщика', 'поставщиков') === '12 поставщиков', 'catalog counts must use plural form');

const workspaceBase = {
  status: 'negotiation',
  negotiationStatus: 'awaiting_offer',
  activeProposalId: 7,
  activeProposalLineCount: 2,
  activeProposalTotal: 2400,
  productCount: 1,
  serviceCount: 1,
  linkedEquipmentCount: 0,
  documents: [],
  total: 2400,
  paid: 0,
  balance: 2400,
};
assert(
  buildOrderWorkspaceViewModel({ ...workspaceBase, activeProposalStatus: 'draft' }).nextAction.command === 'finish_proposal',
  'valid draft proposal must lead to preparation completion',
);
assert(
  buildOrderWorkspaceViewModel({ ...workspaceBase, activeProposalStatus: 'ready_to_send' }).nextAction.command === 'send_proposal',
  'ready proposal must lead to sending',
);
assert(
  buildOrderWorkspaceViewModel({ ...workspaceBase, activeProposalStatus: 'sent' }).nextAction.command === 'record_proposal_response',
  'sent proposal must lead to recording the response',
);
assert(
  buildOrderWorkspaceViewModel({ ...workspaceBase, activeProposalStatus: 'rejected' }).nextAction.command === 'create_proposal_variant',
  'rejected proposal must lead to a new variant',
);
assert(proposalPrimaryAction('approved') === null, 'accepted proposal must not expose another proposal action');
assert(isProposalRevisionLocked('sent'), 'sent proposal revision must be locked');
assert(isProposalRevisionLocked('approved'), 'accepted proposal revision must be locked');
assert(!isProposalRevisionLocked('ready_to_send'), 'ready proposal must remain editable before sending');
assert(proposalStatusLabel('accepted') === 'Принято клиентом', 'legacy accepted alias must render consistently');

assert(
  buildMeasurementSummary({ required: false }) === 'Замер не требуется',
  'optional measurement must be described as not required',
);
assert(
  buildMeasurementSummary({ required: true }) === 'Замер не назначен',
  'required measurement without a date must be described as not scheduled',
);
assert(
  buildMeasurementSummary({ required: true, date: '2026-07-20', formatDate: () => '20.07.2026' }) === 'Замер назначен: 20.07.2026',
  'scheduled measurement must show its date',
);
assert(
  buildMeasurementSummary({ required: true, result: 'Осмотр выполнен', kind: 'diagnostic' }) === 'Диагностика выполнена',
  'completed diagnostic must use the correct wording',
);

console.log('Manager UI logic tests passed');
