import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { ProductCard } from "./ProductCard";
import { CartProvider, useCart } from "../contexts/CartContext";
import { WishlistProvider } from "../contexts/WishlistContext";
import type { Recommendation } from "../types";

const item: Recommendation = {
  product_id: "p1", title: "Test Product", price: 999, price_tier: "mid",
  rating: 4.5, reviews: 10, image_url: "img.jpg", product_url: "https://example.com",
  reason: "Because it's great.",
};

function CartCount() {
  const { count } = useCart();
  return <span data-testid="cart-count">{count}</span>;
}

function renderCard() {
  return render(
    <MemoryRouter>
      <CartProvider>
        <WishlistProvider>
          <CartCount />
          <ProductCard item={item} />
        </WishlistProvider>
      </CartProvider>
    </MemoryRouter>,
  );
}

describe("ProductCard", () => {
  beforeEach(() => { localStorage.clear(); });

  it("still renders the title, price and outbound link as before", () => {
    renderCard();
    expect(screen.getByText("Test Product")).toBeTruthy();
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe("https://example.com");
  });

  it("Add to Cart updates the cart without touching the outbound link", () => {
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: /add to cart/i }));
    expect(screen.getByTestId("cart-count").textContent).toBe("1");
    // Still exactly one link on the card (the outbound one) — the actions are buttons.
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });
});
