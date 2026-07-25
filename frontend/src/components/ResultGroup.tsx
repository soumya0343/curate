import type { ResultGroup as Group } from "../types";
import { ProductCard } from "./ProductCard";

export function ResultGroup({ group }: { group: Group }) {
  return (
    <section className="mb-8">
      <h2 className="mb-3 text-lg font-semibold text-slate-900">{group.label}</h2>
      {group.recommendations.length === 0 ? (
        // Empty groups are shown, never hidden — an honest gap reads better than
        // a silently missing section (spec 5, Stage 5).
        <p className="rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-500">
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
