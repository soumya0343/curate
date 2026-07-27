import type { MouseEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useCart } from "../contexts/CartContext";
import { useWishlist } from "../contexts/WishlistContext";
import type { ProductRef } from "../types";

export function ProductCardActions({ product }: { product: ProductRef }) {
  const { addToCart } = useCart();
  const { toggle, has } = useWishlist();
  const navigate = useNavigate();
  const inWishlist = has(product.id);

  const stop = (e: MouseEvent) => { e.preventDefault(); e.stopPropagation(); };

  return (
    <div className="mt-3 flex items-center gap-2" onClick={stop}>
      <button
        type="button"
        onClick={(e) => { stop(e); toggle(product); }}
        aria-pressed={inWishlist}
        aria-label={inWishlist ? "Remove from wishlist" : "Add to wishlist"}
        className={`rounded-full border px-2.5 py-1.5 text-sm transition ${
          inWishlist
            ? "border-gold-300 bg-gold-50 text-gold-500"
            : "border-primary/10 text-primary/40 hover:text-primary"
        }`}
      >
        {inWishlist ? "♥" : "♡"}
      </button>
      <button
        type="button"
        onClick={(e) => { stop(e); addToCart(product); }}
        className="rounded-full border border-primary/10 px-3 py-1.5 text-xs font-medium text-primary/70 transition hover:border-primary/25"
      >
        Add to Cart
      </button>
      <button
        type="button"
        onClick={(e) => { stop(e); navigate("/checkout", { state: { item: { ...product, quantity: 1 } } }); }}
        className="rounded-full bg-primary px-3 py-1.5 text-xs font-medium text-white transition hover:bg-primary/90"
      >
        Buy Now
      </button>
    </div>
  );
}
