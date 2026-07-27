// frontend/src/pages/CartPage.tsx
import { useNavigate } from "react-router-dom";
import { useCart } from "../contexts/CartContext";

const INR = new Intl.NumberFormat("en-IN", {
  style: "currency", currency: "INR", maximumFractionDigits: 0,
});

export function CartPage() {
  const { items, remove, update } = useCart();
  const navigate = useNavigate();
  const subtotal = items.reduce((sum, item) => sum + item.price * item.quantity, 0);

  if (items.length === 0) {
    return (
      <main className="mx-auto max-w-7xl px-4 py-10 lg:px-8">
        <h1 className="font-serif text-3xl font-medium text-primary">Cart</h1>
        <p className="mt-4 text-sm text-primary/50">Your cart is empty.</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-10 lg:px-8">
      <h1 className="font-serif text-3xl font-medium text-primary">Cart</h1>
      <ul className="mt-6 flex flex-col gap-4">
        {items.map((item) => (
          <li key={item.id} className="flex items-center gap-4 rounded-xl border border-primary/10 bg-white p-4">
            <img src={item.image_url} alt="" className="h-16 w-16 rounded-lg object-contain bg-surface" />
            <div className="min-w-0 flex-1">
              <p className="line-clamp-1 text-sm font-medium text-primary">{item.title}</p>
              <p className="text-sm text-primary/60">{INR.format(item.price)} × {item.quantity}</p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => update(item.id, (i) => ({ ...i, quantity: Math.max(1, i.quantity - 1) }))}
                className="h-7 w-7 rounded-full border border-primary/10 text-primary/60 transition hover:border-primary/25"
              >
                −
              </button>
              <span className="w-6 text-center text-sm">{item.quantity}</span>
              <button
                type="button"
                onClick={() => update(item.id, (i) => ({ ...i, quantity: i.quantity + 1 }))}
                className="h-7 w-7 rounded-full border border-primary/10 text-primary/60 transition hover:border-primary/25"
              >
                +
              </button>
            </div>
            <button
              type="button"
              onClick={() => remove(item.id)}
              aria-label="Remove from cart"
              className="text-primary/40 transition hover:text-primary"
            >
              ✕
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-6 flex items-center justify-between border-t border-primary/10 pt-4">
        <span className="text-sm text-primary/60">Subtotal</span>
        <span className="text-lg font-semibold text-primary">{INR.format(subtotal)}</span>
      </div>
      <button
        type="button"
        onClick={() => navigate("/checkout", { state: { items } })}
        className="mt-6 w-full rounded-full bg-primary px-6 py-3 text-sm font-medium text-white transition hover:bg-primary/90"
      >
        Proceed to Checkout
      </button>
    </main>
  );
}
