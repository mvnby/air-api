function cloneSnapshotValue(value) {
  if (Array.isArray(value)) {
    return Object.freeze(value.map((item) => cloneSnapshotValue(item)));
  }

  if (value && typeof value === 'object') {
    const clone = {};
    Object.keys(value).forEach((key) => {
      clone[key] = cloneSnapshotValue(value[key]);
    });
    return Object.freeze(clone);
  }

  return value;
}

function normalizeForKey(value) {
  if (Array.isArray(value)) {
    return value.map((item) => normalizeForKey(item));
  }

  if (value && typeof value === 'object') {
    return Object.keys(value)
      .sort()
      .reduce((result, key) => {
        if (value[key] !== undefined) {
          result[key] = normalizeForKey(value[key]);
        }
        return result;
      }, {});
  }

  return value;
}

export function createImmutableQuerySnapshot(value) {
  return cloneSnapshotValue(value);
}

export function catalogQueryKey(value) {
  return JSON.stringify(normalizeForKey(value));
}

export function createCatalogRequestGuard() {
  let requestEpoch = 0;
  let filterGeneration = 0;
  let committedFilterKey = null;
  let activeReload = null;
  let activeAppend = null;

  const abortToken = (token) => {
    if (token && !token.signal.aborted) {
      token.controller.abort();
    }
  };

  const clearActiveRequests = () => {
    abortToken(activeReload);
    abortToken(activeAppend);
    activeReload = null;
    activeAppend = null;
  };

  const createToken = (kind, filterSnapshot, requestSnapshot) => {
    const controller = new AbortController();
    const immutableFilterSnapshot = createImmutableQuerySnapshot(filterSnapshot);

    return Object.freeze({
      kind,
      epoch: ++requestEpoch,
      filterGeneration,
      filterKey: catalogQueryKey(immutableFilterSnapshot),
      filterSnapshot: immutableFilterSnapshot,
      snapshot: createImmutableQuerySnapshot(requestSnapshot),
      controller,
      signal: controller.signal,
    });
  };

  const isCurrent = (token, currentFilterSnapshot = token?.filterSnapshot) => {
    if (!token || token.signal.aborted || token.filterGeneration !== filterGeneration) {
      return false;
    }

    if (catalogQueryKey(currentFilterSnapshot) !== token.filterKey) {
      return false;
    }

    if (token.kind === 'reload') {
      return activeReload === token;
    }

    return activeAppend === token
      && activeReload === null
      && committedFilterKey === token.filterKey;
  };

  return {
    setCommittedFilterSnapshot(filterSnapshot) {
      clearActiveRequests();
      filterGeneration += 1;
      committedFilterKey = catalogQueryKey(filterSnapshot);
    },

    beginReload({ filterSnapshot, requestSnapshot }) {
      clearActiveRequests();
      filterGeneration += 1;
      const token = createToken('reload', filterSnapshot, requestSnapshot);
      activeReload = token;
      return token;
    },

    beginAppend({ filterSnapshot, requestSnapshot }) {
      const filterKey = catalogQueryKey(filterSnapshot);
      if (activeReload || committedFilterKey === null || filterKey !== committedFilterKey) {
        return null;
      }

      abortToken(activeAppend);
      activeAppend = createToken('append', filterSnapshot, requestSnapshot);
      return activeAppend;
    },

    isCurrent,

    commit(token, currentFilterSnapshot, apply) {
      if (!isCurrent(token, currentFilterSnapshot)) {
        return false;
      }

      apply(token.snapshot);
      if (token.kind === 'reload') {
        committedFilterKey = token.filterKey;
      }
      return true;
    },

    finish(token) {
      if (token?.kind === 'reload' && activeReload === token) {
        activeReload = null;
        return true;
      }
      if (token?.kind === 'append' && activeAppend === token) {
        activeAppend = null;
        return true;
      }
      return false;
    },

    invalidate() {
      clearActiveRequests();
      filterGeneration += 1;
    },
  };
}
