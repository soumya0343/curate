import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import App from "./App";

describe("attribution", () => {
  it("names the source dataset and its licence on every page", () => {
    // ODC-By 4.3 requires this notice wherever results are shown publicly.
    // A licence obligation that only lives in a markdown file is not met.
    render(<App />);
    expect(screen.getByText(/Contains information from/i)).toBeTruthy();

    const licence = screen.getByRole("link", { name: /ODC Attribution License/i });
    expect(licence.getAttribute("href")).toBe(
      "https://opendatacommons.org/licenses/by/1-0/",
    );
  });
});
