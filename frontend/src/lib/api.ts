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

export interface SseFrame {
  event: string;
  data: unknown;
}

/** Parse complete SSE frames from a buffer. Incomplete trailing frames are ignored
 *  so the caller can retain the remainder for the next chunk. */
export function parseSseFrames(buffer: string): SseFrame[] {
  const frames: SseFrame[] = [];
  const blocks = buffer.split("\n\n");
  // A buffer that doesn't end with the blank-line separator has an incomplete
  // trailing frame — drop it so the caller can retain the remainder.
  if (!buffer.endsWith("\n\n")) blocks.pop();
  for (const block of blocks) {
    const eventLine = block.match(/^event:\s*(.+)$/m);
    const dataLine = block.match(/^data:\s*(.+)$/m);
    if (!eventLine || !dataLine) continue;
    try {
      frames.push({ event: eventLine[1].trim(), data: JSON.parse(dataLine[1]) });
    } catch {
      // Malformed payload — skip this frame rather than failing the stream.
    }
  }
  return frames;
}

export interface StreamHandlers {
  onUnderstood?: (data: any) => void;
  onSearching?: (data: any) => void;
  onResults?: (data: any) => void;
  onDone?: (data: any) => void;
  onError?: (error: ApiFailure) => void;
}

/** POST + fetch streaming. Native EventSource is GET-only, and the request body
 *  carries a natural-language query plus session state (spec 7.1). */
export async function recommendStream(
  query: string,
  sessionId: string | undefined,
  handlers: StreamHandlers,
): Promise<void> {
  const response = await fetch(`${BASE}/api/recommend/stream`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ query, session_id: sessionId ?? null }),
  });

  if (!response.ok || !response.body) {
    handlers.onError?.(new ApiFailure("INTERNAL", "Stream failed to start.", true));
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lastBoundary = buffer.lastIndexOf("\n\n");
    if (lastBoundary === -1) continue;
    const complete = buffer.slice(0, lastBoundary + 2);
    buffer = buffer.slice(lastBoundary + 2);

    for (const frame of parseSseFrames(complete)) {
      const data = frame.data as any;
      if (frame.event === "understood") handlers.onUnderstood?.(data);
      else if (frame.event === "searching") handlers.onSearching?.(data);
      else if (frame.event === "results") handlers.onResults?.(data);
      else if (frame.event === "done") handlers.onDone?.(data);
      else if (frame.event === "error") {
        handlers.onError?.(new ApiFailure(
          data.error?.code ?? "INTERNAL",
          data.error?.message ?? "Something went wrong.",
          data.error?.retryable ?? false));
      }
    }
  }
}
