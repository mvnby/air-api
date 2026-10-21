import { runGuardedNavigation, runGuardedUnload } from './unsaved-navigation-guard';

type Entry = { id: string; session: string; position: number };
export type ManagerHistoryTarget = Entry & { href: string };
type Snapshot = { href: string; state: Record<string, unknown>; entry: Entry | null };
const KEY = 'managerNavigation';
const href = () => `${window.location.pathname}${window.location.search}`;
const id = () => crypto.randomUUID();
const entry = (state: Record<string, unknown>): Entry | null => {
  const value = state[KEY] as Entry | undefined;
  return value && typeof value.id === 'string' && typeof value.session === 'string'
    && Number.isSafeInteger(value.position) ? value : null;
};
const snapshot = (): Snapshot => {
  const state = window.history.state || {};
  return { href: href(), state, entry: entry(state) };
};
const localHref = (value: string) => {
  const url = new URL(value, window.location.origin);
  if (url.origin !== window.location.origin || !/^\/manager(?:\/|$)/.test(url.pathname)) throw new Error('Недопустимый адрес перехода');
  return `${url.pathname}${url.search}`;
};
let controller: { accepted: Snapshot; accept: (location: string) => void; normalize: () => string } | null = null;
let pendingPop: Snapshot | null = null;
let restoring: string | null = null;
let destination: { target: ManagerHistoryTarget; href: string } | null = null;

export const currentManagerHistoryTarget = (): ManagerHistoryTarget => {
  let current = snapshot();
  if (!current.entry) {
    const metadata: Entry = { id: id(), session: id(), position: 0 };
    window.history.replaceState({ ...current.state, [KEY]: metadata }, '');
    current = snapshot();
  }
  return { ...current.entry!, href: current.href };
};

const commit = () => {
  if (!controller) return;
  controller.normalize();
  controller.accepted = snapshot();
  controller.accept(controller.accepted.href);
};

// App owns rendering; this service owns history changes and runs the save barrier once.
export const startManagerNavigation = (accept: (location: string) => void, normalize: () => string) => {
  pendingPop = null; restoring = null; destination = null;
  currentManagerHistoryTarget();
  const owner = { accepted: snapshot(), accept, normalize };
  controller = owner;
  const onPop = async () => {
    normalize();
    const target = snapshot();
    if (restoring && target.entry?.id === restoring) { restoring = null; return; }
    if (pendingPop) { pendingPop = target; return; }
    pendingPop = target;
    const previous = owner.accepted;
    await runGuardedNavigation(() => {
      const next = pendingPop!;
      const planned = destination;
      if (planned && planned.target.id === next.entry?.id) window.history.replaceState(next.state, '', planned.href);
      destination = null;
      commit();
    }, () => {
      const next = pendingPop!;
      destination = null;
      if (previous.entry && next.entry?.session === previous.entry.session && next.entry.position !== previous.entry.position) {
        restoring = previous.entry.id;
        window.history.go(previous.entry.position - next.entry.position);
      } else {
        // Older, untracked entries have no reliable traversal distance.
        window.history.replaceState(previous.state, '', previous.href);
      }
    });
    pendingPop = null;
  };
  window.addEventListener('popstate', onPop);
  return () => {
    window.removeEventListener('popstate', onPop);
    if (controller === owner) { controller = null; pendingPop = null; restoring = null; destination = null; }
  };
};

export const navigateManager = (value: string, state: Record<string, unknown> = {}, replace = false) => {
  const targetHref = localHref(value);
  if (pendingPop || restoring) return Promise.resolve(false);
  return runGuardedNavigation(() => {
    const current = currentManagerHistoryTarget();
    const metadata: Entry = replace ? current : { id: id(), session: current.session, position: current.position + 1 };
    window.history[replace ? 'replaceState' : 'pushState']({ ...state, [KEY]: metadata }, '', targetHref);
    commit();
  });
};

export const reloadManagerLocation = () => {
  if (pendingPop || restoring) return Promise.resolve(false);
  return runGuardedUnload(() => window.location.reload());
};

// Updating the viewed proposal must not remount the order or run its leave guard.
export const replaceManagerLocation = (value: string) => {
  window.history.replaceState(window.history.state, '', localHref(value));
  if (controller && entry(window.history.state || {})?.id === controller.accepted.entry?.id) controller.accepted = snapshot();
};

export const openManagerChild = (value: string) => navigateManager(value, { managerReturn: currentManagerHistoryTarget() });

export const goToManagerHistoryTarget = (target: ManagerHistoryTarget | undefined, value: string): boolean => {
  const current = currentManagerHistoryTarget();
  if (!target || target.session !== current.session || target.position >= current.position) return false;
  destination = { target, href: localHref(value) };
  window.history.go(target.position - current.position);
  return true;
};

export const returnToManager = (value: string) => {
  const targetHref = localHref(value);
  const target = window.history.state?.managerReturn as ManagerHistoryTarget | undefined;
  const comparable = (location: string) => {
    const url = new URL(location, window.location.origin);
    // The catalog adds the viewed proposal to the existing order entry on return.
    if (/^\/manager\/orders\/[1-9]\d*\/?$/.test(url.pathname)) url.searchParams.delete('proposalId');
    url.searchParams.sort();
    return `${url.pathname}${url.search}`;
  };
  if (target && comparable(target.href) === comparable(targetHref) && goToManagerHistoryTarget(target, targetHref)) return;
  return navigateManager(targetHref);
};
