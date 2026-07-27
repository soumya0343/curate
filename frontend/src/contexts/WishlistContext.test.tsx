// frontend/src/contexts/WishlistContext.test.tsx
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { WishlistProvider, useWishlist } from "./WishlistContext";
import type { ProductRef } from "../types";

const product: ProductRef = {
  id: "p1", title: "Test Product", price: 100,
  image_url: "img.jpg", product_url: "https://example.com",
};

function renderWishlist() {
  return renderHook(() => useWishlist(), { wrapper: WishlistProvider });
}

describe("WishlistContext", () => {
  beforeEach(() => { localStorage.clear(); });

  it("toggle adds the item when absent", () => {
    const { result } = renderWishlist();
    act(() => result.current.toggle(product));
    expect(result.current.items).toEqual([product]);
    expect(result.current.count).toBe(1);
  });

  it("toggle removes the item when present", () => {
    const { result } = renderWishlist();
    act(() => result.current.toggle(product));
    act(() => result.current.toggle(product));
    expect(result.current.items).toEqual([]);
    expect(result.current.count).toBe(0);
  });

  it("has reflects membership", () => {
    const { result } = renderWishlist();
    expect(result.current.has("p1")).toBe(false);
    act(() => result.current.toggle(product));
    expect(result.current.has("p1")).toBe(true);
  });

  it("useWishlist throws outside a WishlistProvider", () => {
    expect(() => renderHook(() => useWishlist())).toThrow("useWishlist must be used within a WishlistProvider");
  });
});
