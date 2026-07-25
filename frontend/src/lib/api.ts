import type { ApiError, RecommendResponse } from "../types";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiFailure extends Error {
  code: string;
  retryable: boolean;

  constructor(code: string, message: string, retryable: boolean) {
    super(message);
    this.name = "ApiFailure";
    this.code = code;
    this.retryable = retryable;
  }
}

export async function recommend(
  query: string,
  sessionId?: string,
): Promise<RecommendResponse> {
  const response = await fetch(`${BASE}/api/recommend`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ query, session_id: sessionId ?? null }),
  });

  const body = await response.json();
  if (!response.ok) {
    const { error } = body as ApiError;
    throw new ApiFailure(
      error?.code ?? "INTERNAL",
      error?.message ?? "Something went wrong.",
      error?.retryable ?? false,
    );
  }
  return body as RecommendResponse;
}
