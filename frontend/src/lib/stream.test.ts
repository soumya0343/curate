import { describe, expect, it } from "vitest";
import { parseSseFrames } from "./api";

describe("parseSseFrames", () => {
  it("parses a single complete frame", () => {
    const frames = parseSseFrames('event: understood\ndata: {"a":1}\n\n');
    expect(frames).toEqual([{ event: "understood", data: { a: 1 } }]);
  });

  it("parses several frames in one chunk", () => {
    const frames = parseSseFrames(
      'event: searching\ndata: {"candidates":12}\n\nevent: done\ndata: {}\n\n');
    expect(frames.map((f) => f.event)).toEqual(["searching", "done"]);
  });

  it("ignores an incomplete trailing frame", () => {
    expect(parseSseFrames('event: understood\ndata: {"a":1}')).toEqual([]);
  });

  it("skips frames with unparseable data rather than throwing", () => {
    const frames = parseSseFrames("event: results\ndata: {oops\n\nevent: done\ndata: {}\n\n");
    expect(frames.map((f) => f.event)).toEqual(["done"]);
  });
});
