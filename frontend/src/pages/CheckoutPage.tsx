// frontend/src/pages/CheckoutPage.tsx
import { useLocation, useNavigate } from "react-router-dom";
import { useCart } from "../contexts/CartContext";
import type { CartItem } from "../types";
import { useEffect } from "react";

const INR = new Intl.NumberFormat("en-IN", {
  style: "currency", currency: "INR", maximumFractionDigits: 0,
});

export function CheckoutPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { clear } = useCart();

  // Accept either single-item (from Buy Now) or multi-item (from Cart)
  const item = location.state?.item as CartItem | undefined;
  const items = location.state?.items as CartItem[] | undefined;
  const checkoutItems = item ? [item] : items ?? [];

  useEffect(() => {
    if (checkoutItems.length === 0) navigate("/");
  }, [checkoutItems.length, navigate]);

  const subtotal = checkoutItems.reduce((sum, it) => sum + it.price * it.quantity, 0);

  const handlePlaceOrder = () => {
    clear();
    alert("Order placed successfully!");
    navigate("/");
  };

  if (checkoutItems.length === 0) return null;

  return (
    <main className="mx-auto max-w-3xl px-4 py-10 lg:px-8">
      <h1 className="font-serif text-3xl font-medium text-primary">Checkout</h1>
      <div className="mt-6 rounded-xl border border-primary/10 bg-white p-6">
        <h2 className="text-lg font-medium text-primary mb-4">Order Summary</h2>
        <ul className="flex flex-col gap-3">
          {checkoutItems.map((it) => (
            <li key={it.id} className="flex items-center gap-4 pb-3 border-b border-primary/5 last:border-0">
              <img src={it.image_url} alt="" className="h-12 w-12 rounded-lg object-contain bg-surface" />
              <div className="min-w-0 flex-1">
                <p className="line-clamp-1 text-sm font-medium text-primary">{it.title}</p>
                <p className="text-xs text-primary/50">Qty: {it.quantity}</p>
              </div>
              <span className="text-sm font-semibold text-primary">{INR.format(it.price * it.quantity)}</span>
            </li>
          ))}
        </ul>
        <div className="mt-4 flex items-center justify-between pt-4 border-t border-primary/10">
          <span className="text-sm text-primary/60">Total</span>
          <span className="text-xl font-bold text-primary">{INR.format(subtotal)}</span>
        </div>
      </div>
      <button
        type="button"
        onClick={handlePlaceOrder}
        className="mt-6 w-full rounded-full bg-primary px-6 py-3 text-sm font-medium text-white transition hover:bg-primary/90"
      >
        Place Order
      </button>
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="mt-3 w-full rounded-full border border-primary/10 px-6 py-3 text-sm font-medium text-primary/70 transition hover:border-primary/25"
      >
        Back
      </button>
    </main>
  );
}
