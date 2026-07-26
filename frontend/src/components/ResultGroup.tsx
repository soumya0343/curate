import type { ResultGroup as Group } from "../types";
import { ProductCard } from "./ProductCard";

export function ResultGroup({ group }: { group: Group }) {
  return (
    <section className="mb-10">
      <h2 className="mb-4 font-serif text-xl font-medium text-primary">{group.label}</h2>
      {group.recommendations.length === 0 ? (
        <p className="rounded-xl border border-dashed border-primary/15 p-4 text-sm text-primary/40">
          {group.empty_reason}
        </p>
      ) : (
        <div className="grid gap-3">
          {group.recommendations.map((item) => (
            <ProductCard key={item.product_id} item={item} />
          ))}
        </div>
      )}
    </section>
  );
}
