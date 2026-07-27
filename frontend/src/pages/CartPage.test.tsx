// frontend/src/pages/CartPage.test.tsx
import { useEffect } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CartPage } from "./CartPage";
import { CartProvider, useCart } from "../contexts/CartContext";
import type { ProductRef } from "../types";

const navigateMock = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

const product: ProductRef = {
  id: "p1", title: "Test Product", price: 500,
  image_url: "img.jpg", product_url: "https://example.com",
};

function Seed() {
  const { addToCart } = useCart();
  useEffect(() => { addToCart(product); }, []);
  return null;
}

function renderCart(seed: boolean) {
  return render(
    <MemoryRouter>
      <CartProvider>
        {seed && <Seed />}
        <CartPage />
      </CartProvider>
    </MemoryRouter>,
  );
}

describe("CartPage", () => {
  // The vitest.setup.ts localStorage polyfill is one instance per test FILE,
  // not per test - without this, quantities from one test's Seed compound
  // into the next test's fresh CartProvider.
  beforeEach(() => { localStorage.clear(); });

  it("shows an empty state", () => {
    renderCart(false);
    expect(screen.getByText(/cart is empty/i)).toBeTruthy();
  });

  it("shows the item and its price", () => {
    renderCart(true);
    expect(screen.getByText("Test Product")).toBeTruthy();
    expect(screen.getByText(/₹500/)).toBeTruthy();
  });

  it("+ increases quantity and the subtotal", () => {
    renderCart(true);
    fireEvent.click(screen.getByRole("button", { name: "+" }));
    expect(screen.getByText(/₹1,000/)).toBeTruthy();
  });

  it("Proceed to Checkout navigates with the full cart", () => {
    renderCart(true);
    fireEvent.click(screen.getByRole("button", { name: /proceed to checkout/i }));
    expect(navigateMock).toHaveBeenCalledWith("/checkout", {
      state: { items: [{ ...product, quantity: 1 }] },
    });
  });
});
