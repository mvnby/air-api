import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createCatalogRequestGuard,
  createImmutableQuerySnapshot,
} from '../src/utils/catalog-request-guard.js';

const deferred = () => {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
};

const beginReload = (guard, q) => guard.beginReload({
  filterSnapshot: { page: 1, limit: 20, q },
  requestSnapshot: { apiParams: { page: 1, limit: 20, q } },
});

test('immutable snapshots are detached from later query mutations', () => {
  const query = { q: 'alpha', tag_slugs: ['cat-household'] };
  const snapshot = createImmutableQuerySnapshot(query);

  query.q = 'beta';
  query.tag_slugs.push('sale');

  assert.deepEqual(snapshot, { q: 'alpha', tag_slugs: ['cat-household'] });
  assert.equal(Object.isFrozen(snapshot), true);
  assert.equal(Object.isFrozen(snapshot.tag_slugs), true);
});

test('only the newest reload commits when responses arrive out of order', async () => {
  const guard = createCatalogRequestGuard();
  guard.setCommittedFilterSnapshot({ page: 1, limit: 20, q: 'initial' });
  const slow = deferred();
  const fast = deferred();
  const committed = [];

  const first = beginReload(guard, 'first');
  const firstResult = slow.promise.then((value) => {
    guard.commit(first, first.filterSnapshot, () => committed.push(value));
    guard.finish(first);
  });

  const second = beginReload(guard, 'second');
  const secondResult = fast.promise.then((value) => {
    guard.commit(second, second.filterSnapshot, () => committed.push(value));
    guard.finish(second);
  });

  assert.equal(second.epoch > first.epoch, true);
  assert.equal(first.signal.aborted, true);

  fast.resolve('second-response');
  await secondResult;
  slow.resolve('first-response');
  await firstResult;

  assert.deepEqual(committed, ['second-response']);
});

test('a reload aborts stale load-more and stale append cannot commit', () => {
  const guard = createCatalogRequestGuard();
  const firstFilter = { page: 1, limit: 20, q: 'first' };
  guard.setCommittedFilterSnapshot(firstFilter);

  const append = guard.beginAppend({
    filterSnapshot: firstFilter,
    requestSnapshot: { apiParams: { ...firstFilter, page: 2 } },
  });
  const reload = beginReload(guard, 'second');
  let appended = false;

  assert.equal(append.signal.aborted, true);
  assert.equal(reload.signal.aborted, false);
  assert.equal(guard.commit(append, firstFilter, () => { appended = true; }), false);
  assert.equal(appended, false);
});

test('load-more neither starts against uncommitted filters nor cancels active reload', () => {
  const guard = createCatalogRequestGuard();
  const initialFilter = { page: 1, limit: 20, q: 'initial' };
  guard.setCommittedFilterSnapshot(initialFilter);

  const mismatchedAppend = guard.beginAppend({
    filterSnapshot: { ...initialFilter, q: 'typed-but-not-loaded' },
    requestSnapshot: { apiParams: { page: 2, limit: 20, q: 'typed-but-not-loaded' } },
  });
  assert.equal(mismatchedAppend, null);

  const reload = beginReload(guard, 'next');
  const appendDuringReload = guard.beginAppend({
    filterSnapshot: reload.filterSnapshot,
    requestSnapshot: { apiParams: { ...reload.filterSnapshot, page: 2 } },
  });

  assert.equal(appendDuringReload, null);
  assert.equal(reload.signal.aborted, false);
  assert.equal(guard.isCurrent(reload, reload.filterSnapshot), true);
});

test('a response is ignored when live filters changed before the next reload began', () => {
  const guard = createCatalogRequestGuard();
  const filter = { page: 1, limit: 20, q: 'old' };
  guard.setCommittedFilterSnapshot(filter);
  const append = guard.beginAppend({
    filterSnapshot: filter,
    requestSnapshot: { apiParams: { ...filter, page: 2 } },
  });
  let appended = false;

  const changedLiveFilter = { ...filter, q: 'new' };
  assert.equal(guard.commit(append, changedLiveFilter, () => { appended = true; }), false);
  assert.equal(appended, false);
});
