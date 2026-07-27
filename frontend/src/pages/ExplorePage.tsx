import { useCallback, useEffect, useState } from "react";
import { ApiFailure, listCatalogue } from "../lib/api";
import type { ProductSummary } from "../types";
import { CatalogueProductCard } from "../components/CatalogueProductCard";

export function ExplorePage() {
  const [items, setItems] = useState<ProductSummary[]>([]);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  const loadPage = useCallback(async (targetPage: number) => {
    setStatus("loading");
    try {
      const data = await listCatalogue(targetPage);
      setItems((prev) => (targetPage === 1 ? data.items : [...prev, ...data.items]));
      setPages(data.pages);
      setPage(data.page);
      setStatus("idle");
    } catch (err) {
      setError(err instanceof ApiFailure ? err.message : "Something went wrong.");
      setStatus("error");
    }
  }, []);

  useEffect(() => { loadPage(1); }, [loadPage]);

  return (
    <main className="mx-auto max-w-7xl px-4 py-10 lg:px-8">
      <h1 className="font-serif text-3xl font-medium text-primary">Explore</h1>
      {status === "error" && <p className="mt-4 text-sm text-red-700">{error}</p>}
      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item) => <CatalogueProductCard key={item.id} item={item} />)}
      </div>
      {page < pages && (
        <button
          type="button"
          onClick={() => loadPage(page + 1)}
          disabled={status === "loading"}
          className="mx-auto mt-8 block rounded-full border border-primary/10 px-6 py-2 text-sm text-primary/70 transition hover:border-primary/25 disabled:opacity-50"
        >
          {status === "loading" ? "Loading…" : "Load more"}
        </button>
      )}
    </main>
  );
}
