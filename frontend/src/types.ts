// Mirrors backend/app/schemas/response.py. Keep field names identical.

export interface Assumption {
  field: string;
  value: string;
  reason: string;
  confidence: "low" | "medium" | "high";
  editable: boolean;
}

export interface Recommendation {
  product_id: string;
  title: string;
  price: number;
  price_tier: string;
  rating: number;
  reviews: number;
  image_url: string;
  product_url: string;
  reason: string;
}

export interface ResultGroup {
  label: string;
  recommendations: Recommendation[];
  empty_reason: string | null;
  fallback_note: string | null;
}

export interface RecommendResponse {
  session_id: string;
  intent: Record<string, unknown>;
  assumptions: Assumption[];
  clarifying_questions: string[];
  groups: ResultGroup[];
  relaxations: string[];
  timings_ms: Record<string, number>;
  awaiting_clarification: boolean;
}

export interface ApiError {
  error: { code: string; message: string; retryable: boolean };
}

export interface ProductRef {
  id: string;
  title: string;
  price: number;
  image_url: string;
  product_url: string;
}

export interface CartItem extends ProductRef {
  quantity: number;
}

export type WishlistItem = ProductRef;

export interface ProductSummary {
  id: string;
  title: string;
  domain: string | null;
  category: string;
  subcategory: string | null;
  price: number;
  currency: string;
  price_tier: string;
  rating: number;
  reviews: number;
  image_url: string | null;
  product_url: string | null;
}

export interface CatalogueResponse {
  total: number;
  page: number;
  page_size: number;
  pages: number;
  items: ProductSummary[];
}
