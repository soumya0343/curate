import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useRecommendation } from "./useRecommendation";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return { ...actual, recommendStream: vi.fn() };
});
const { recommendStream, ApiFailure } = await import("../lib/api");

afterEach(() => vi.clearAllMocks());

type Handlers = Parameters<typeof recommendStream>[2];

function mockStream(run: (query: string, sessionId: string | undefined, handlers: Handlers) => void) {
  vi.mocked(recommendStream).mockImplementation(async (query, sessionId, handlers) => {
    run(query, sessionId, handlers);
  });
}

const RESULTS_DATA = {
  groups: [{ label: "Backpack", recommendations: [], empty_reason: "none", fallback_note: null }],
  relaxations: [],
};

describe("useRecommendation", () => {
  it("starts idle", () => {
    const { result } = renderHook(() => useRecommendation());
    expect(result.current.status).toBe("idle");
  });

  it("moves to ready and stores the response", async () => {
    mockStream((_q, _sid, handlers) => {
      handlers.onUnderstood?.({ session_id: "sess-1", assumptions: [], clarifying_questions: [] });
      handlers.onResults?.(RESULTS_DATA);
    });
    const { result } = renderHook(() => useRecommendation());
    await act(async () => { await result.current.submit("trekking gear"); });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.response?.groups[0].label).toBe("Backpack");
    expect(result.current.queries).toEqual(["trekking gear"]);
  });

  it("reuses the session id when refining, and keeps the query trail", async () => {
    mockStream((_q, _sid, handlers) => {
      handlers.onUnderstood?.({ session_id: "sess-1", assumptions: [], clarifying_questions: [] });
      handlers.onResults?.(RESULTS_DATA);
    });
    const { result } = renderHook(() => useRecommendation());
    await act(async () => { await result.current.submit("trekking gear"); });
    await act(async () => { await result.current.refine("make it cheaper"); });

    expect(result.current.queries).toEqual(["trekking gear", "make it cheaper"]);
    const secondCall = vi.mocked(recommendStream).mock.calls[1];
    expect(secondCall[1]).toBe("sess-1");
  });

  it("clears the query trail when starting a fresh submit", async () => {
    mockStream((_q, _sid, handlers) => {
      handlers.onUnderstood?.({ session_id: "sess-1", assumptions: [], clarifying_questions: [] });
      handlers.onResults?.(RESULTS_DATA);
    });
    const { result } = renderHook(() => useRecommendation());
    await act(async () => { await result.current.submit("trekking gear"); });
    await act(async () => { await result.current.submit("something else"); });

    expect(result.current.queries).toEqual(["something else"]);
  });

  it("captures errors without crashing", async () => {
    mockStream((_q, _sid, handlers) => {
      handlers.onError?.(new ApiFailure("RATE_LIMITED", "slow", true));
    });
    const { result } = renderHook(() => useRecommendation());
    await act(async () => { await result.current.submit("x"); });
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error?.code).toBe("RATE_LIMITED");
  });
});
