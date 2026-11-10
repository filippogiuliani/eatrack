// Shared state: session (user, family, children), food catalog and notifications
import { get } from './api.js';

export const app = $state({
  categories: [],
  foods: [],
  toast: null,
  me: null, // response of /api/me
  childId: null,
});

const CHILD_KEY = 'eatrack.child';
const readLocal = (k) => { try { return localStorage.getItem(k); } catch { return null; } };
const writeLocal = (k, v) => { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } };

export function activeChildren() {
  return (app.me?.children ?? []).filter((c) => !c.archived);
}
export function currentChild() {
  return app.me?.children?.find((c) => c.id === app.childId) ?? null;
}
export function chooseChild(id) {
  app.childId = id;
  writeLocal(CHILD_KEY, String(id));
}

export async function loadMe() {
  app.me = await get('/me');
  const active = activeChildren();
  if (!active.some((c) => c.id === app.childId)) {
    const saved = Number(readLocal(CHILD_KEY));
    app.childId = (active.find((c) => c.id === saved) ?? active[0])?.id ?? null;
  }
  return app.me;
}

export function category(id) {
  return app.categories.find((c) => c.id === id) ?? { key: '?' };
}
export function food(id) {
  return app.foods.find((f) => f.id === id);
}

export async function loadCatalog() {
  const q = app.childId ? `?child=${app.childId}` : '';
  const [categories, foods] = await Promise.all([get('/categories'), get('/foods' + q)]);
  app.categories = categories;
  app.foods = foods;
}

let timer;
export function toast(message, kind = 'ok') {
  app.toast = { message, kind, id: Date.now() };
  clearTimeout(timer);
  timer = setTimeout(() => (app.toast = null), kind === 'error' ? 5000 : 2600);
}
export const showError = (e) => toast(e?.message || String(e), 'error');
