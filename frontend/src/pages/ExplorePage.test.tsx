import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ExplorePage } from "./ExplorePage";
import { CartProvider } from "../contexts/CartContext";
import { WishlistProvider } from "../contexts/WishlistContext";

afterEach(() => vi.unstubAllGlobals());

function stubFetchSequence(responses: unknown[]) {
  const fn = vi.fn();
  for (const body of responses) fn.mockResolvedValueOnce({ ok: true, json: async () => body });
  vi.stubGlobal("fetch", fn);
}

function renderExplore() {
  return render(
    <MemoryRouter>
      <CartProvider>
        <WishlistProvider>
          <ExplorePage />
        </WishlistProvider>
      </CartProvider>
    </MemoryRouter>,
  );
}

const productA = {
  id: "a", title: "Product A", domain: null, category: "Cat", subcategory: null,
  price: 100, currency: "INR", price_tier: "budget", rating: 4, reviews: 5,
  image_url: "a.jpg", product_url: "https://a",
};
const productB = {
  id: "b", title: "Product B", domain: null, category: "Cat", subcategory: null,
  price: 200, currency: "INR", price_tier: "mid", rating: 4, reviews: 5,
  image_url: "b.jpg", product_url: "https://b",
};

describe("ExplorePage", () => {
  it("loads and renders the first page on mount", async () => {
    stubFetchSequence([{ total: 2, page: 1, page_size: 1, pages: 2, items: [productA] }]);
    renderExplore();
    await waitFor(() => expect(screen.getByText("Product A")).toBeTruthy());
  });

  it("Load more appends the next page instead of replacing the first", async () => {
    stubFetchSequence([
      { total: 2, page: 1, page_size: 1, pages: 2, items: [productA] },
      { total: 2, page: 2, page_size: 1, pages: 2, items: [productB] },
    ]);
    renderExplore();
    await waitFor(() => expect(screen.getByText("Product A")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /load more/i }));
    await waitFor(() => expect(screen.getByText("Product B")).toBeTruthy());
    expect(screen.getByText("Product A")).toBeTruthy();
  });
});
