import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useRecommendation } from "./useRecommendation";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return { ...actual, recommend: vi.fn() };
});
const { recommend } = await import("../lib/api");

afterEach(() => vi.clearAllMocks());

const RESPONSE = {
  session_id: "sess-1", intent: {}, assumptions: [], clarifying_questions: [],
  groups: [{ label: "Backpack", recommendations: [], empty_reason: "none" }],
  relaxations: [], timings_ms: {},
};

describe("useRecommendation", () => {
  it("starts idle", () => {
    const { result } = renderHook(() => useRecommendation());
    expect(result.current.status).toBe("idle");
  });

  it("moves to ready and stores the response", async () => {
    vi.mocked(recommend).mockResolvedValue(RESPONSE as never);
    const { result } = renderHook(() => useRecommendation());
    await act(async () => { await result.current.submit("trekking gear"); });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.response?.groups[0].label).toBe("Backpack");
  });

  it("reuses the session id when refining", async () => {
    vi.mocked(recommend).mockResolvedValue(RESPONSE as never);
    const { result } = renderHook(() => useRecommendation());
    await act(async () => { await result.current.submit("trekking gear"); });
    await act(async () => { await result.current.refine("make it cheaper"); });
    expect(vi.mocked(recommend).mock.calls[1]).toEqual(["make it cheaper", "sess-1"]);
  });

  it("captures errors without crashing", async () => {
    const { ApiFailure } = await import("../lib/api");
    vi.mocked(recommend).mockRejectedValue(new ApiFailure("RATE_LIMITED", "slow", true));
    const { result } = renderHook(() => useRecommendation());
    await act(async () => { await result.current.submit("x"); });
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error?.code).toBe("RATE_LIMITED");
  });
});
