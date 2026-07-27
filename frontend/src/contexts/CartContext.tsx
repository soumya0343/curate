// frontend/src/contexts/CartContext.tsx
import { createContext, useCallback, useContext, type ReactNode } from "react";
import { useLocalStorageList } from "../hooks/useLocalStorageList";
import type { CartItem, ProductRef } from "../types";

interface CartContextValue {
  items: CartItem[];
  addToCart: (product: ProductRef) => void;
  remove: (id: string) => void;
  update: (id: string, updater: (item: CartItem) => CartItem) => void;
  clear: () => void;
  count: number;
}

const CartContext = createContext<CartContextValue | null>(null);

export function CartProvider({ children }: { children: ReactNode }) {
  const { items, add, remove, has, clear, update } = useLocalStorageList<CartItem>("curate.cart");

  const addToCart = useCallback((product: ProductRef) => {
    if (has(product.id)) {
      update(product.id, (item) => ({ ...item, quantity: item.quantity + 1 }));
    } else {
      add({ ...product, quantity: 1 });
    }
  }, [has, update, add]);

  const count = items.reduce((sum, item) => sum + item.quantity, 0);

  return (
    <CartContext.Provider value={{ items, addToCart, remove, update, clear, count }}>
      {children}
    </CartContext.Provider>
  );
}

export function useCart(): CartContextValue {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart must be used within a CartProvider");
  return ctx;
}
