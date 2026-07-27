import { useCallback, useEffect, useState } from "react";

export function useLocalStorageList<T extends { id: string }>(storageKey: string) {
  const [items, setItems] = useState<T[]>(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      return raw ? (JSON.parse(raw) as T[]) : [];
    } catch {
      return [];
    }
  });

  useEffect(() => {
    localStorage.setItem(storageKey, JSON.stringify(items));
  }, [storageKey, items]);

  const add = useCallback((item: T) => {
    setItems((prev) => (prev.some((existing) => existing.id === item.id) ? prev : [...prev, item]));
  }, []);

  const remove = useCallback((id: string) => {
    setItems((prev) => prev.filter((existing) => existing.id !== id));
  }, []);

  const has = useCallback(
    (id: string) => items.some((existing) => existing.id === id),
    [items],
  );

  const update = useCallback((id: string, updater: (item: T) => T) => {
    setItems((prev) => prev.map((existing) => (existing.id === id ? updater(existing) : existing)));
  }, []);

  const clear = useCallback(() => setItems([]), []);

  return { items, add, remove, has, update, clear };
}
