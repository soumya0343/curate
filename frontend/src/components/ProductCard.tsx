import type { Recommendation } from "../types";
import { toProductRef } from "../lib/productRef";
import { ProductCardActions } from "./ProductCardActions";

const INR = new Intl.NumberFormat("en-IN", {
  style: "currency", currency: "INR", maximumFractionDigits: 0,
});

// Tiers with verified facts (from price/budget constraints) get gold styling;
// inferred suggestions get the default muted treatment.
const VERIFIED_TIERS = new Set(["budget", "mid-range"]);

export function ProductCard({ item }: { item: Recommendation }) {
  const isVerifiedTier = VERIFIED_TIERS.has(item.price_tier);

  return (
    <div className="group flex flex-col rounded-xl border border-primary/10 bg-white p-4 transition hover:border-primary/25 hover:shadow-sm">
      <a
        href={item.product_url}
        target="_blank"
        rel="noreferrer noopener"
        className="flex gap-4"
      >
        <img
          src={item.image_url}
          alt=""
          loading="lazy"
          className="h-24 w-24 shrink-0 rounded-lg object-contain bg-surface"
        />
        <div className="min-w-0 flex flex-col">
          <h3 className="line-clamp-2 text-sm font-medium text-primary leading-snug">
            {item.title}
          </h3>
          <div className="mt-1.5 flex items-center gap-2 text-sm">
            <span className="font-semibold text-primary">{INR.format(item.price)}</span>
            <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium capitalize ${
              isVerifiedTier
                ? "bg-gold-100 text-gold-500"
                : "bg-primary/5 text-primary/50"
            }`}>
              {item.price_tier}
            </span>
            {item.reviews > 0 && (
              <span className="text-xs text-primary/40">
                {item.rating.toFixed(1)} · {item.reviews.toLocaleString("en-IN")} reviews
              </span>
            )}
          </div>
          <p className="mt-2 text-xs text-primary/60 leading-relaxed line-clamp-2">
            {item.reason}
          </p>
        </div>
      </a>
      <ProductCardActions product={toProductRef(item)} />
    </div>
  );
}
