// Node 25+ ships its own native `localStorage` global (the stable Web Storage
// API), active before Vitest's jsdom environment even sets up. Vitest's
// jsdom-global copy step skips any key already present on `global` rather than
// overriding it, so Node's stub - which lacks `.clear()` unless
// `--localstorage-file` points at a real file - wins instead of jsdom's.
// Symptom: `TypeError: localStorage.clear is not a function` in every test
// that touches it (useLocalStorageList, CartContext, WishlistContext, and
// anything built on them).
//
// Fixed by unconditionally replacing `globalThis.localStorage` with a small
// in-memory implementation, rather than depending on jsdom's copy winning a
// race with Node's.
class MemoryStorage implements Storage {
  private store = new Map<string, string>();

  get length(): number {
    return this.store.size;
  }

  clear(): void {
    this.store.clear();
  }

  getItem(key: string): string | null {
    return this.store.has(key) ? this.store.get(key)! : null;
  }

  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null;
  }

  removeItem(key: string): void {
    this.store.delete(key);
  }

  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
}

Object.defineProperty(globalThis, "localStorage", {
  value: new MemoryStorage(),
  configurable: true,
  writable: true,
});
