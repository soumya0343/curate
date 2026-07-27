import { useCallback, useEffect, useRef, useState } from "react";
import { ApiFailure, listCatalogue, listCategories } from "../lib/api";
import type { ProductSummary } from "../types";
import { CatalogueProductCard } from "../components/CatalogueProductCard";

const PRICE_TIERS = ["budget", "mid", "premium", "luxury"];
const SORT_OPTIONS = [
  { value: "rating", label: "Top Rated" },
  { value: "reviews", label: "Most Reviewed" },
  { value: "price", label: "Price" },
  { value: "quality_score", label: "Quality" },
];

export function ExplorePage() {
  const [items, setItems] = useState<ProductSummary[]>([]);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [priceTier, setPriceTier] = useState("");
  const [sortBy, setSortBy] = useState("rating");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [categories, setCategories] = useState<{ category: string; count: number }[]>([]);

  const searchTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    listCategories().then(setCategories);
  }, []);

  const loadPage = useCallback(async (targetPage: number, append = false) => {
    setStatus("loading");
    try {
      const data = await listCatalogue({
        page: targetPage,
        search: search || undefined,
        category: category || undefined,
        price_tier: priceTier || undefined,
        sort_by: sortBy,
        order,
      });
      setItems((prev) => (append ? [...prev, ...data.items] : data.items));
      setPages(data.pages);
      setPage(data.page);
      setTotal(data.total);
      setStatus("idle");
    } catch (err) {
      setError(err instanceof ApiFailure ? err.message : "Something went wrong.");
      setStatus("error");
    }
  }, [search, category, priceTier, sortBy, order]);

  // Reset to page 1 when filters change
  useEffect(() => {
    if (searchTimeout.current) clearTimeout(searchTimeout.current);
    searchTimeout.current = setTimeout(() => loadPage(1, false), search ? 300 : 0);
    return () => { if (searchTimeout.current) clearTimeout(searchTimeout.current); };
  }, [loadPage, search]);

  return (
    <main className="mx-auto max-w-7xl px-4 py-10 lg:px-8">
      <div className="flex items-baseline justify-between">
        <h1 className="font-serif text-3xl font-medium text-primary">Explore</h1>
        {total > 0 && (
          <span className="text-sm text-primary/40">{total.toLocaleString()} products</span>
        )}
      </div>

      {/* Filters */}
      <div className="mt-5 flex flex-wrap gap-3">
        <input
          type="search"
          placeholder="Search products…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-9 min-w-[200px] flex-1 rounded-full border border-primary/15 bg-white px-4 text-sm text-primary placeholder:text-primary/30 focus:outline-none focus:ring-1 focus:ring-primary/20"
        />
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="h-9 rounded-full border border-primary/15 bg-white px-4 text-sm text-primary/70 focus:outline-none"
        >
          <option value="">All Categories</option>
          {categories.map((c) => (
            <option key={c.category} value={c.category}>{c.category} ({c.count})</option>
          ))}
        </select>
        <select
          value={priceTier}
          onChange={(e) => setPriceTier(e.target.value)}
          className="h-9 rounded-full border border-primary/15 bg-white px-4 text-sm text-primary/70 focus:outline-none"
        >
          <option value="">All Prices</option>
          {PRICE_TIERS.map((t) => (
            <option key={t} value={t} className="capitalize">{t}</option>
          ))}
        </select>
        <select
          value={`${sortBy}:${order}`}
          onChange={(e) => {
            const [s, o] = e.target.value.split(":");
            setSortBy(s);
            setOrder(o as "asc" | "desc");
          }}
          className="h-9 rounded-full border border-primary/15 bg-white px-4 text-sm text-primary/70 focus:outline-none"
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={`${opt.value}:desc`} value={`${opt.value}:desc`}>{opt.label} ↓</option>
          ))}
          <option value="price:asc">Price ↑</option>
        </select>
      </div>

      {status === "error" && <p className="mt-4 text-sm text-red-700">{error}</p>}

      {status === "loading" && items.length === 0 && (
        <div className="mt-16 text-center text-sm text-primary/30">Loading…</div>
      )}

      {status !== "loading" && items.length === 0 && (
        <div className="mt-16 text-center text-sm text-primary/30">No products found.</div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item) => <CatalogueProductCard key={item.id} item={item} />)}
      </div>

      {page < pages && (
        <button
          type="button"
          onClick={() => loadPage(page + 1, true)}
          disabled={status === "loading"}
          className="mx-auto mt-8 block rounded-full border border-primary/10 px-6 py-2 text-sm text-primary/70 transition hover:border-primary/25 disabled:opacity-50"
        >
          {status === "loading" ? "Loading…" : "Load more"}
        </button>
      )}
    </main>
  );
}
