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
}

export interface RecommendResponse {
  session_id: string;
  intent: Record<string, unknown>;
  assumptions: Assumption[];
  clarifying_questions: string[];
  groups: ResultGroup[];
  relaxations: string[];
  timings_ms: Record<string, number>;
}

export interface ApiError {
  error: { code: string; message: string; retryable: boolean };
}
