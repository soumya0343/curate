// frontend/src/contexts/CartContext.test.tsx
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { CartProvider, useCart } from "./CartContext";
import type { ProductRef } from "../types";

const product: ProductRef = {
  id: "p1", title: "Test Product", price: 100,
  image_url: "img.jpg", product_url: "https://example.com",
};

function renderCart() {
  return renderHook(() => useCart(), { wrapper: CartProvider });
}

describe("CartContext", () => {
  beforeEach(() => { localStorage.clear(); });

  it("addToCart adds a new item with quantity 1", () => {
    const { result } = renderCart();
    act(() => result.current.addToCart(product));
    expect(result.current.items).toEqual([{ ...product, quantity: 1 }]);
    expect(result.current.count).toBe(1);
  });

  it("addToCart on an existing item increments quantity instead of duplicating", () => {
    const { result } = renderCart();
    act(() => result.current.addToCart(product));
    act(() => result.current.addToCart(product));
    expect(result.current.items).toEqual([{ ...product, quantity: 2 }]);
    expect(result.current.count).toBe(2);
  });

  it("remove drops the item", () => {
    const { result } = renderCart();
    act(() => result.current.addToCart(product));
    act(() => result.current.remove("p1"));
    expect(result.current.items).toEqual([]);
  });

  it("update can change an item directly", () => {
    const { result } = renderCart();
    act(() => result.current.addToCart(product));
    act(() => result.current.update("p1", (item) => ({ ...item, quantity: 5 })));
    expect(result.current.items[0].quantity).toBe(5);
  });

  it("clear empties the cart", () => {
    const { result } = renderCart();
    act(() => result.current.addToCart(product));
    act(() => result.current.clear());
    expect(result.current.items).toEqual([]);
    expect(result.current.count).toBe(0);
  });

  it("useCart throws outside a CartProvider", () => {
    expect(() => renderHook(() => useCart())).toThrow("useCart must be used within a CartProvider");
  });
});
