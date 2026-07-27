import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AssumptionChips, statedFactChips } from "./AssumptionChips";

const ASSUMPTIONS = [{
  field: "climate", value: "cold-weather conditions likely",
  reason: "high-altitude trek in late October",
  confidence: "medium" as const, editable: true,
}];

describe("AssumptionChips", () => {
  it("shows each assumption with its confidence", () => {
    render(<AssumptionChips assumptions={ASSUMPTIONS} questions={[]} onAnswer={vi.fn()} />);
    expect(screen.getByText(/cold-weather conditions likely/)).toBeTruthy();
    expect(screen.getByText(/medium/i)).toBeTruthy();
  });

  it("renders nothing when there is nothing to show", () => {
    const { container } = render(
      <AssumptionChips assumptions={[]} questions={[]} onAnswer={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows the clarifying questions alongside, not instead of, results", () => {
    render(<AssumptionChips assumptions={ASSUMPTIONS}
                            questions={["What's your budget?", "Any brand preference?"]}
                            onAnswer={vi.fn()} />);
    expect(screen.getByText("What's your budget?")).toBeTruthy();
    expect(screen.getByText("Any brand preference?")).toBeTruthy();
    expect(screen.getByText(/cold-weather/)).toBeTruthy();
  });

  it("submits an answer to the clarifying questions", async () => {
    const onAnswer = vi.fn();
    render(<AssumptionChips assumptions={[]} questions={["What's your budget?"]}
                            onAnswer={onAnswer} />);
    await userEvent.type(screen.getByPlaceholderText(/answer/i), "under 5000");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));
    expect(onAnswer).toHaveBeenCalledWith("under 5000");
  });
});

describe("statedFactChips", () => {
  it("surfaces a stated gender as a chip", () => {
    const chips = statedFactChips({ gender: "women" }, new Set());
    expect(chips).toEqual([
      { field: "gender", value: "women", reason: "You told me this", confidence: "high", editable: false },
    ]);
  });

  it("does not chip a defaulted unisex gender - that's already shown as an assumption", () => {
    const chips = statedFactChips({ gender: "unisex" }, new Set());
    expect(chips.find((c) => c.field === "gender")).toBeUndefined();
  });

  it("formats budget and duration into readable chips", () => {
    const chips = statedFactChips({ budget_max: 5000, duration_days: 7 }, new Set());
    expect(chips).toContainEqual(expect.objectContaining({ field: "budget", value: "Under ₹5,000" }));
    expect(chips).toContainEqual(expect.objectContaining({ field: "duration", value: "7 days" }));
  });

  it("skips fields already shown as an assumption", () => {
    const chips = statedFactChips({ destination: "Manali" }, new Set(["destination"]));
    expect(chips).toEqual([]);
  });

  it("skips null/undefined intent fields", () => {
    const chips = statedFactChips({ activity: null, occasion: undefined }, new Set());
    expect(chips).toEqual([]);
  });
});
