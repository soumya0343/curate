import type { ProductSummary } from "../types";
import { toProductRef } from "../lib/productRef";
import { ProductCardActions } from "./ProductCardActions";

const INR = new Intl.NumberFormat("en-IN", {
  style: "currency", currency: "INR", maximumFractionDigits: 0,
});

export function CatalogueProductCard({ item }: { item: ProductSummary }) {
  return (
    <div className="flex flex-col rounded-xl border border-primary/10 bg-white p-4 transition hover:border-primary/25 hover:shadow-sm">
      <a
        href={item.product_url ?? undefined}
        target="_blank"
        rel="noreferrer noopener"
        className="flex gap-4"
      >
        <img
          src={item.image_url ?? ""}
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
            <span className="rounded-full bg-primary/5 px-2 py-0.5 text-[11px] font-medium capitalize text-primary/50">
              {item.price_tier}
            </span>
          </div>
        </div>
      </a>
      <ProductCardActions product={toProductRef(item)} />
    </div>
  );
}
