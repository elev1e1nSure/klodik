import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "./App";

vi.mock("./components/Agent", () => ({
  default: () => <div data-testid="agent-mock">Agent</div>,
}));

describe("App", () => {
  it("renders Agent component", () => {
    render(<App />);
    expect(screen.getByTestId("agent-mock")).toBeInTheDocument();
  });
});
