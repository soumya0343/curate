// frontend/src/pages/WishlistPage.test.tsx
import { useEffect } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { WishlistPage } from "./WishlistPage";
import { CartProvider, useCart } from "../contexts/CartContext";
import { WishlistProvider, useWishlist } from "../contexts/WishlistContext";
import type { ProductRef } from "../types";

const product: ProductRef = {
  id: "p1", title: "Test Product", price: 500,
  image_url: "img.jpg", product_url: "https://example.com",
};

function Seed() {
  const { toggle } = useWishlist();
  useEffect(() => { toggle(product); }, []);
  return null;
}

function CartCount() {
  const { count } = useCart();
  return <span data-testid="cart-count">{count}</span>;
}

function renderWishlist(seed: boolean) {
  return render(
    <MemoryRouter>
      <CartProvider>
        <WishlistProvider>
          {seed && <Seed />}
          <CartCount />
          <WishlistPage />
        </WishlistProvider>
      </CartProvider>
    </MemoryRouter>,
  );
}

describe("WishlistPage", () => {
  beforeEach(() => { localStorage.clear(); });

  it("shows an empty state with nothing saved", () => {
    renderWishlist(false);
    expect(screen.getByText(/nothing saved yet/i)).toBeTruthy();
  });

  it("lists a saved item and can add it to the cart", () => {
    renderWishlist(true);
    expect(screen.getByText("Test Product")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /add to cart/i }));
    expect(screen.getByTestId("cart-count").textContent).toBe("1");
  });

  it("removes an item from the wishlist", () => {
    renderWishlist(true);
    fireEvent.click(screen.getByRole("button", { name: /remove from wishlist/i }));
    expect(screen.getByText(/nothing saved yet/i)).toBeTruthy();
  });
});
