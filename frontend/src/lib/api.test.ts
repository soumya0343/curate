import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiFailure, listCatalogue, recommend } from "./api";

afterEach(() => vi.unstubAllGlobals());

function stubFetch(status: number, body: unknown) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: status < 400,
    status,
    json: async () => body,
  }));
}

describe("recommend", () => {
  it("returns the parsed response on success", async () => {
    stubFetch(200, { session_id: "abc", groups: [], assumptions: [], relaxations: [] });
    const result = await recommend("trekking gear");
    expect(result.session_id).toBe("abc");
  });

  it("sends the session id when one is supplied", async () => {
    stubFetch(200, { session_id: "abc", groups: [] });
    await recommend("cheaper", "sess-1");
    const [, init] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(JSON.parse(init.body as string).session_id).toBe("sess-1");
  });

  it("throws ApiFailure carrying the error code", async () => {
    stubFetch(400, { error: { code: "INVALID_QUERY", message: "no", retryable: false } });
    await expect(recommend("")).rejects.toThrow(ApiFailure);
    await expect(recommend("")).rejects.toMatchObject({ code: "INVALID_QUERY" });
  });
});

describe("listCatalogue", () => {
  it("requests the given page and page size", async () => {
    stubFetch(200, { total: 0, page: 2, page_size: 20, pages: 1, items: [] });
    await listCatalogue(2, 20);
    const [url] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toContain("page=2");
    expect(url).toContain("page_size=20");
  });

  it("returns the parsed response on success", async () => {
    stubFetch(200, { total: 1, page: 1, page_size: 20, pages: 1, items: [{ id: "p1" }] });
    const result = await listCatalogue(1);
    expect(result.items).toHaveLength(1);
  });

  it("throws ApiFailure on a non-ok response", async () => {
    stubFetch(503, { error: { code: "CATALOGUE_UNAVAILABLE", message: "down", retryable: true } });
    await expect(listCatalogue(1)).rejects.toThrow(ApiFailure);
  });
});
