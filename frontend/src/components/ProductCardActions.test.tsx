import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProductCardActions } from "./ProductCardActions";
import { CartProvider } from "../contexts/CartContext";
import { WishlistProvider } from "../contexts/WishlistContext";
import type { ProductRef } from "../types";

const navigateMock = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

const product: ProductRef = {
  id: "p1", title: "Test Product", price: 100,
  image_url: "img.jpg", product_url: "https://example.com",
};

function renderActions() {
  return render(
    <MemoryRouter>
      <CartProvider>
        <WishlistProvider>
          <ProductCardActions product={product} />
        </WishlistProvider>
      </CartProvider>
    </MemoryRouter>,
  );
}

describe("ProductCardActions", () => {
  beforeEach(() => { localStorage.clear(); });

  it("toggles the wishlist button's label and pressed state", () => {
    renderActions();
    const wishlistButton = screen.getByRole("button", { name: /add to wishlist/i });
    fireEvent.click(wishlistButton);
    expect(screen.getByRole("button", { name: /remove from wishlist/i })).toBeTruthy();
  });

  it("Buy Now navigates to /checkout with a single-item quantity of 1", () => {
    renderActions();
    fireEvent.click(screen.getByRole("button", { name: /buy now/i }));
    expect(navigateMock).toHaveBeenCalledWith("/checkout", {
      state: { item: { ...product, quantity: 1 } },
    });
  });
});
