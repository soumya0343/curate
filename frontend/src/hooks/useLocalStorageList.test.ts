import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useLocalStorageList } from "./useLocalStorageList";

interface Item { id: string; label: string; }

describe("useLocalStorageList", () => {
  beforeEach(() => { localStorage.clear(); });

  it("starts empty when nothing is stored", () => {
    const { result } = renderHook(() => useLocalStorageList<Item>("test.key"));
    expect(result.current.items).toEqual([]);
  });

  it("adds an item and persists it to localStorage", () => {
    const { result } = renderHook(() => useLocalStorageList<Item>("test.key"));
    act(() => result.current.add({ id: "1", label: "one" }));
    expect(result.current.items).toEqual([{ id: "1", label: "one" }]);
    expect(JSON.parse(localStorage.getItem("test.key")!)).toEqual([{ id: "1", label: "one" }]);
  });

  it("does not add a duplicate id", () => {
    const { result } = renderHook(() => useLocalStorageList<Item>("test.key"));
    act(() => result.current.add({ id: "1", label: "one" }));
    act(() => result.current.add({ id: "1", label: "one-again" }));
    expect(result.current.items).toEqual([{ id: "1", label: "one" }]);
  });

  it("removes an item by id", () => {
    const { result } = renderHook(() => useLocalStorageList<Item>("test.key"));
    act(() => result.current.add({ id: "1", label: "one" }));
    act(() => result.current.remove("1"));
    expect(result.current.items).toEqual([]);
  });

  it("has() reflects membership", () => {
    const { result } = renderHook(() => useLocalStorageList<Item>("test.key"));
    expect(result.current.has("1")).toBe(false);
    act(() => result.current.add({ id: "1", label: "one" }));
    expect(result.current.has("1")).toBe(true);
  });

  it("update() transforms an existing item", () => {
    const { result } = renderHook(() => useLocalStorageList<Item>("test.key"));
    act(() => result.current.add({ id: "1", label: "one" }));
    act(() => result.current.update("1", (item) => ({ ...item, label: "changed" })));
    expect(result.current.items).toEqual([{ id: "1", label: "changed" }]);
  });

  it("clear() empties the list", () => {
    const { result } = renderHook(() => useLocalStorageList<Item>("test.key"));
    act(() => result.current.add({ id: "1", label: "one" }));
    act(() => result.current.clear());
    expect(result.current.items).toEqual([]);
  });

  it("survives a reload: a fresh hook instance reads what a prior instance persisted", () => {
    const first = renderHook(() => useLocalStorageList<Item>("test.key"));
    act(() => first.result.current.add({ id: "1", label: "one" }));
    first.unmount();

    const second = renderHook(() => useLocalStorageList<Item>("test.key"));
    expect(second.result.current.items).toEqual([{ id: "1", label: "one" }]);
  });
});
