// frontend/src/lib/productRef.ts
import type { ProductRef, ProductSummary, Recommendation } from "../types";

export function toProductRef(source: Recommendation | ProductSummary): ProductRef {
  const id = "product_id" in source ? source.product_id : source.id;
  return {
    id,
    title: source.title,
    price: source.price,
    image_url: source.image_url ?? "",
    product_url: source.product_url ?? "",
  };
}
