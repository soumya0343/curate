// frontend/src/pages/WishlistPage.tsx
import { useNavigate } from "react-router-dom";
import { useCart } from "../contexts/CartContext";
import { useWishlist } from "../contexts/WishlistContext";

const INR = new Intl.NumberFormat("en-IN", {
  style: "currency", currency: "INR", maximumFractionDigits: 0,
});

export function WishlistPage() {
  const { items, toggle } = useWishlist();
  const { addToCart } = useCart();
  const navigate = useNavigate();

  if (items.length === 0) {
    return (
      <main className="mx-auto max-w-7xl px-4 py-10 lg:px-8">
        <h1 className="font-serif text-3xl font-medium text-primary">Wishlist</h1>
        <p className="mt-4 text-sm text-primary/50">Nothing saved yet.</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-10 lg:px-8">
      <h1 className="font-serif text-3xl font-medium text-primary">Wishlist</h1>
      <ul className="mt-6 flex flex-col gap-4">
        {items.map((item) => (
          <li key={item.id} className="flex items-center gap-4 rounded-xl border border-primary/10 bg-white p-4">
            <img src={item.image_url} alt="" className="h-16 w-16 rounded-lg object-contain bg-surface" />
            <div className="min-w-0 flex-1">
              <p className="line-clamp-1 text-sm font-medium text-primary">{item.title}</p>
              <p className="text-sm text-primary/60">{INR.format(item.price)}</p>
            </div>
            <button
              type="button"
              onClick={() => addToCart(item)}
              className="rounded-full border border-primary/10 px-3 py-1.5 text-xs font-medium text-primary/70 transition hover:border-primary/25"
            >
              Add to Cart
            </button>
            <button
              type="button"
              onClick={() => navigate("/checkout", { state: { item: { ...item, quantity: 1 } } })}
              className="rounded-full bg-primary px-3 py-1.5 text-xs font-medium text-white transition hover:bg-primary/90"
            >
              Buy Now
            </button>
            <button
              type="button"
              onClick={() => toggle(item)}
              aria-label="Remove from wishlist"
              className="text-primary/40 transition hover:text-primary"
            >
              ✕
            </button>
          </li>
        ))}
      </ul>
    </main>
  );
}
