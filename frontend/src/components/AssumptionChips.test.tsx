import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AssumptionChips } from "./AssumptionChips";

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
