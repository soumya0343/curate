import type { Recommendation } from "../types";

const INR = new Intl.NumberFormat("en-IN", {
  style: "currency", currency: "INR", maximumFractionDigits: 0,
});

export function ProductCard({ item }: { item: Recommendation }) {
  return (
    <a
      href={item.product_url}
      target="_blank"
      rel="noreferrer noopener"
      className="flex gap-4 rounded-lg border border-slate-200 bg-white p-4 transition hover:border-slate-400"
    >
      <img
        src={item.image_url}
        alt=""
        loading="lazy"
        className="h-24 w-24 shrink-0 rounded object-contain"
      />
      <div className="min-w-0">
        <h3 className="line-clamp-2 text-sm font-medium text-slate-900">{item.title}</h3>
        <div className="mt-1 flex items-center gap-2 text-sm">
          <span className="font-semibold">{INR.format(item.price)}</span>
          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs capitalize text-slate-600">
            {item.price_tier}
          </span>
          {item.reviews > 0 && (
            <span className="text-xs text-slate-500">
              {item.rating.toFixed(1)} ({item.reviews.toLocaleString("en-IN")})
            </span>
          )}
        </div>
        <p className="mt-2 text-sm text-slate-600">{item.reason}</p>
      </div>
    </a>
  );
}
