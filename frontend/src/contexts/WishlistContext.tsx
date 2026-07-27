// frontend/src/contexts/WishlistContext.tsx
import { createContext, useCallback, useContext, type ReactNode } from "react";
import { useLocalStorageList } from "../hooks/useLocalStorageList";
import type { ProductRef, WishlistItem } from "../types";

interface WishlistContextValue {
  items: WishlistItem[];
  toggle: (product: ProductRef) => void;
  has: (id: string) => boolean;
  count: number;
}

const WishlistContext = createContext<WishlistContextValue | null>(null);

export function WishlistProvider({ children }: { children: ReactNode }) {
  const { items, add, remove, has } = useLocalStorageList<WishlistItem>("curate.wishlist");

  const toggle = useCallback((product: ProductRef) => {
    if (has(product.id)) remove(product.id);
    else add(product);
  }, [has, add, remove]);

  return (
    <WishlistContext.Provider value={{ items, toggle, has, count: items.length }}>
      {children}
    </WishlistContext.Provider>
  );
}

export function useWishlist(): WishlistContextValue {
  const ctx = useContext(WishlistContext);
  if (!ctx) throw new Error("useWishlist must be used within a WishlistProvider");
  return ctx;
}
