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
  catalogQualityStateMatchesView,
  catalogQualityViewFiltersFromState,
  createDefaultCatalogQualityState,
  parseCatalogQualityState,
  serializeCatalogQualityState,
} from '../src/components/catalog-quality/catalog-quality-state';
import { countLabel } from '../src/components/catalog-quality/catalog-quality-copy';
import { navSections } from '../src/manager-navigation';
import {
  MANAGER_CAPABILITY,
  isManagerPathAllowed,
} from '../src/manager-capabilities';
import {
  buildProductWorkspacePath,
  getProductImageCount,
  getProductWorkspaceNeighbors,
  parseProductWorkspaceLocation,
} from '../src/utils/product-workspace';
import {
  canonicalEnergyClass,
  collapseWifiSpecs,
  getLegacySpecSuggestion,
} from '../src/utils/product-spec-safety';
import {
  cancelActiveDialog,
  confirmDialog,
  promptDialog,
  resetUiFeedbackForTests,
  setDialogInput,
  submitActiveDialog,
  uiDialogState,
} from '../src/services/ui-feedback';
import {
  buildBoardTransitionPayload,
  needsExecutionWithoutPaymentConfirmation,
  runOptimisticOrderTransition,
} from '../src/components/orders/order-transition';
import {
  buildCustomerPatchPayload,
  type CustomerForm,
} from '../src/components/customers/customer-profile-form';
import { getOrderDocumentAccess } from '../src/components/orders/order-document-access';

const assert = (condition: unknown, message: string) => {
  if (!condition) throw new Error(message);
};

const customerForm: CustomerForm = {
  name: 'ООО Клиент',
  phone: '+375 (29) 591-26-81',
  email: 'CLIENT@EXAMPLE.COM ',
  type: 'company',
  inn: '123 456 789',
  kpp: '',
  full_legal_name: 'ООО Клиент',
  legal_address: '',
  actual_address: '',
  bank_name: '',
  bic: '',
  iban: 'BY12 AKBB 3012 0000 0000 0000 0000',
  signer_position: '',
  signer_name: '',
  acting_basis: '',
};
const phoneOnlyPatch = buildCustomerPatchPayload(customerForm, { phone: true });
assert(
  Object.keys(phoneOnlyPatch).join(',') === 'phone',
  'customer PATCH must contain only fields changed by the user',
);
const tenantManagerAuth = {
  capabilities: [
    MANAGER_CAPABILITY.crmManage,
    MANAGER_CAPABILITY.catalogMasterRead,
    MANAGER_CAPABILITY.storefrontOffersRead,
    MANAGER_CAPABILITY.storefrontCollectionsManage,
  ],
};
assert(
  isManagerPathAllowed(tenantManagerAuth, '/manager/products'),
  'tenant managers must retain the safe catalog route',
);
assert(
  isManagerPathAllowed(tenantManagerAuth, '/manager/product-collections'),
  'tenant managers must retain their exact storefront collections route',
);
for (const path of ['/manager/products/1', '/manager/suppliers']) {
  assert(
    !isManagerPathAllowed(tenantManagerAuth, path),
    `tenant manager must not open platform route ${path}`,
  );
}
assert(
  phoneOnlyPatch.phone === '+375 (29) 591-26-81',
  'changed customer phone must be normalized before PATCH',
);
const blankSignerPatch = buildCustomerPatchPayload(customerForm, {
  signer_position: true,
  acting_basis: true,
});
assert(
  blankSignerPatch.signer_position === '' && blankSignerPatch.acting_basis === '',
  'explicitly cleared signer requisites must reach the API for safe defaulting',
);

assert(
  navSections.find((section) => section.id === 'catalog')?.items.map((item) => item.label).join('|')
    === 'Подбор оборудования|Кондиционеры|Подборки|Бренды|Фичи|Прайсы поставщиков|Маппинг прайсов|Поставки|Качество каталога|Медиатека|Теги',
  'catalog navigation must follow the product data workflow',
);

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

const executionDocumentAccess = getOrderDocumentAccess('execution');
assert(
  executionDocumentAccess.mode === 'active'
    && executionDocumentAccess.canCreate
    && executionDocumentAccess.canUpload
    && executionDocumentAccess.canReplace
    && executionDocumentAccess.canDelete,
  'documents must remain fully actionable while an order is in works',
);
const closedDocumentAccess = getOrderDocumentAccess('closed');
assert(
  closedDocumentAccess.mode === 'history'
    && !closedDocumentAccess.canCreate
    && !closedDocumentAccess.canUpload
    && !closedDocumentAccess.canReplace
    && !closedDocumentAccess.canDelete
    && closedDocumentAccess.canSend,
  'completed orders must keep document history and resend access without document mutations',
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
const qualityView = {
  id: 'custom-quality',
  name: 'KINGHOME media',
  filters: catalogQualityViewFiltersFromState(savedQualityView),
};
assert(catalogQualityStateMatchesView(savedQualityView, qualityView), 'saved catalog view must match its source filters');
assert(!catalogQualityStateMatchesView({ ...savedQualityView, brandId: '4' }, qualityView), 'changed filters must mark applied view as changed');
assert(!('page' in qualityView.filters) && !('view' in qualityView.filters), 'saved view must not persist pagination or display mode');
assert(countLabel(1, 'поставщик', 'поставщика', 'поставщиков') === '1 поставщик', 'catalog counts must use singular form');
assert(countLabel(3, 'поставщик', 'поставщика', 'поставщиков') === '3 поставщика', 'catalog counts must use paucal form');
assert(countLabel(12, 'поставщик', 'поставщика', 'поставщиков') === '12 поставщиков', 'catalog counts must use plural form');

assert(
  buildProductWorkspacePath(143, 'media') === '/manager/products/143/media',
  'product workspace links must preserve the requested section',
);
assert(
  buildProductWorkspacePath(143, 'relations') === '/manager/products/143/relations',
  'product workspace must expose relations as a real section',
);
const parsedProductWorkspace = parseProductWorkspaceLocation('/manager/products/143/specifications');
assert(
  parsedProductWorkspace?.productId === 143 && parsedProductWorkspace.section === 'specifications',
  'product workspace location must restore product and section',
);
assert(
  parseProductWorkspaceLocation('/manager/products/not-a-number').productId === null,
  'invalid product workspace routes must not resolve',
);
const middleProductNeighbors = getProductWorkspaceNeighbors([11, 143, 22], 143);
assert(
  middleProductNeighbors.previousId === 11 && middleProductNeighbors.nextId === 22,
  'product workspace navigation must follow the saved list order',
);
const edgeProductNeighbors = getProductWorkspaceNeighbors([11, 143, 22], 11);
assert(
  edgeProductNeighbors.previousId === null && edgeProductNeighbors.nextId === 143,
  'product workspace navigation must stop at list boundaries',
);
assert(
  getProductImageCount({
    main_image: '/media/main.webp',
    gallery_images: [{ id: 1, url: '/media/main.webp' }, { id: 2, url: '/media/side.webp' }],
  } as any) === 2,
  'product media count must deduplicate the main image from the gallery',
);
const wifiSpecs = collapseWifiSpecs([
  { key: 'wifi_ready', value: 'true' },
  { key: 'wifi_builtin', value: 'true' },
  { key: 'energy_class_cooling', value: 'А++' },
]);
assert(wifiSpecs.filter((row) => row.key.startsWith('wifi_')).length === 1, 'Wi-Fi aliases must collapse to one editor field');
assert(wifiSpecs.find((row) => row.key === 'wifi_state')?.value === 'builtin', 'built-in Wi-Fi must take priority over ready');
assert(canonicalEnergyClass(' А++ ') === 'A++', 'energy class must use canonical Latin A');
assert(
  getLegacySpecSuggestion('pipe_gas', '5')?.value === '5/8"',
  'ambiguous legacy pipe values must offer an explicit conversion',
);

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
const invoiceDocument = {
  id: 101,
  doc_type: 'invoice',
  number: 'СЧ-101',
  date: '2026-07-23T10:00:00',
};
assert(
  buildOrderWorkspaceViewModel({
    ...workspaceBase,
    activeProposalStatus: 'draft',
    documents: [invoiceDocument],
  }).nextAction.label === 'Отправить счёт',
  'created invoice must be sendable without forcing a commercial offer',
);
assert(
  buildOrderWorkspaceViewModel({
    ...workspaceBase,
    activeProposalStatus: 'draft',
    documents: [invoiceDocument],
    sentDocumentTypes: ['invoice'],
  }).nextAction.target === 'payments',
  'sent invoice must advance the workspace to payment waiting',
);
assert(
  buildOrderWorkspaceViewModel({
    ...workspaceBase,
    activeProposalStatus: 'draft',
    negotiationStatus: 'awaiting_signature',
    documents: [{
      id: 102,
      doc_type: 'contract',
      number: 'Д-102',
      date: '2026-07-23T10:00:00',
    }],
    sentDocumentTypes: ['contract'],
  }).nextAction.label === 'Ожидать подписанный договор',
  'sent contract must advance the workspace without requiring a commercial offer',
);
assert(
  buildOrderWorkspaceViewModel({
    ...workspaceBase,
    activeProposalStatus: 'sent',
    documents: [invoiceDocument],
    sentDocumentTypes: ['offer'],
  }).nextAction.label === 'Отправить счёт',
  'a prepared invoice must be offered after a commercial offer was sent',
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

resetUiFeedbackForTests();
const confirmation = confirmDialog({ title: 'Подтвердить действие' });
assert(uiDialogState.open && uiDialogState.kind === 'confirm', 'confirmation dialog must open through the shared host state');
await submitActiveDialog();
assert(await confirmation === true, 'confirmation must resolve true after submit');

const cancellation = confirmDialog({ title: 'Отменить действие' });
cancelActiveDialog();
assert(await cancellation === false, 'confirmation must resolve false after cancel or Escape');

let asyncConfirmCalls = 0;
let releaseAsyncConfirm!: () => void;
const asyncGate = new Promise<void>((resolve) => { releaseAsyncConfirm = resolve; });
const asyncConfirmation = confirmDialog({
  title: 'Асинхронное действие',
  onConfirm: async () => {
    asyncConfirmCalls += 1;
    await asyncGate;
  },
});
const firstSubmit = submitActiveDialog();
const duplicateSubmit = submitActiveDialog();
assert(uiDialogState.loading, 'dialog must expose loading state during async confirmation');
assert(asyncConfirmCalls === 1, 'loading dialog must ignore repeated confirmation clicks');
cancelActiveDialog();
assert(uiDialogState.open, 'Escape or backdrop must not cancel a running operation');
releaseAsyncConfirm();
await Promise.all([firstSubmit, duplicateSubmit]);
assert(await asyncConfirmation === true, 'async confirmation must resolve after its action succeeds');

const failedConfirmation = confirmDialog({
  title: 'Ошибка операции',
  onConfirm: async () => { throw new Error('API unavailable'); },
  getErrorMessage: (error) => `Ошибка: ${(error as Error).message}`,
});
await submitActiveDialog();
assert(uiDialogState.open, 'failed async confirmation must stay open');
assert(uiDialogState.error === 'Ошибка: API unavailable', 'failed confirmation must expose a useful error');
cancelActiveDialog();
assert(await failedConfirmation === false, 'failed confirmation must remain cancellable after the request ends');

const prompt = promptDialog({ title: 'Причина', required: true });
await submitActiveDialog();
assert(uiDialogState.error.length > 0 && uiDialogState.open, 'required prompt must validate before resolving');
setDialogInput('Доверенный клиент');
await submitActiveDialog();
assert(await prompt === 'Доверенный клиент', 'prompt must resolve the validated input value');

const unpaidOrder = { balance_due: 500, execution_without_payment: false } as any;
assert(
  needsExecutionWithoutPaymentConfirmation(unpaidOrder, 'execution'),
  'moving an unpaid order to works must require confirmation',
);
assert(
  !needsExecutionWithoutPaymentConfirmation(unpaidOrder, 'execution:awaiting_payment'),
  'moving an unpaid order to awaiting payment must not require the exception dialog',
);
assert(
  !needsExecutionWithoutPaymentConfirmation({ balance_due: 0, execution_without_payment: false } as any, 'execution'),
  'paid order transition must continue without confirmation',
);
const unpaidTransition = buildBoardTransitionPayload(unpaidOrder, 'execution', 'Доверенный клиент');
assert(
  unpaidTransition?.status === 'execution'
    && unpaidTransition.execution_without_payment === true
    && unpaidTransition.execution_without_payment_reason === 'Доверенный клиент',
  'confirmed unpaid transition must preserve the existing business flags and reason',
);
let optimisticStatus = 'negotiation';
let rollbackCalls = 0;
await runOptimisticOrderTransition({
  snapshot: 'negotiation',
  apply: () => { optimisticStatus = 'execution'; },
  persist: async () => ({ status: 'execution' }),
  rollback: (snapshot) => { optimisticStatus = snapshot; rollbackCalls += 1; },
});
assert(optimisticStatus === 'execution' && rollbackCalls === 0, 'successful order transition must remain in its target column');
try {
  await runOptimisticOrderTransition({
    snapshot: 'negotiation',
    apply: () => { optimisticStatus = 'execution'; },
    persist: async () => { throw new Error('API failed'); },
    rollback: (snapshot) => { optimisticStatus = snapshot; rollbackCalls += 1; },
  });
} catch {
  // Expected: the dialog keeps the error visible while the card returns to its source column.
}
assert(optimisticStatus === 'negotiation' && rollbackCalls === 1, 'failed order transition must roll the card back exactly once');

console.log('Manager UI logic tests passed');
