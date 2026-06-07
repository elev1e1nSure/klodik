import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import Agent from "./Agent";
import { useWebSocket } from "../hooks/useWebSocket";

const mockSendTask = vi.fn();

vi.mock("../hooks/useWebSocket", () => ({
  useWebSocket: vi.fn((_url: string) => ({
    connected: true,
    status: "idle",
    lastMessage: "",
    sendTask: mockSendTask,
  })),
}));

vi.mock("lucide-react", () => ({
  Send: vi.fn(() => <svg data-testid="send-icon" />),
}));

vi.mock("@lottiefiles/dotlottie-react", () => ({
  DotLottieReact: vi.fn(() => <div data-testid="lottie-player" />),
}));

describe("Agent", () => {
  beforeEach(() => {
    mockSendTask.mockClear();
  });

  it("renders textarea and send button", () => {
    render(<Agent wsUrl="ws://test" />);
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /send/i })).toBeInTheDocument();
  });

  it("submits task on button click", () => {
    render(<Agent wsUrl="ws://test" />);
    const textarea = screen.getByRole("textbox");
    const button = screen.getByRole("button", { name: /send/i });

    fireEvent.change(textarea, { target: { value: "create a file" } });
    fireEvent.click(button);

    expect(mockSendTask).toHaveBeenCalledWith("create a file");
  });

  it("submits task on Enter key", () => {
    render(<Agent wsUrl="ws://test" />);
    const textarea = screen.getByRole("textbox");

    fireEvent.change(textarea, { target: { value: "run script" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });

    expect(mockSendTask).toHaveBeenCalledWith("run script");
  });

  it("does not submit when input is empty", () => {
    render(<Agent wsUrl="ws://test" />);
    const button = screen.getByRole("button", { name: /send/i });

    fireEvent.click(button);
    expect(mockSendTask).not.toHaveBeenCalled();
  });

  it("does not submit via form when input is empty", () => {
    const { container } = render(<Agent wsUrl="ws://test" />);
    const form = container.querySelector("form");
    fireEvent.submit(form!);
    expect(mockSendTask).not.toHaveBeenCalled();
  });

  it("does not submit via form when not idle", () => {
    const localSendTask = vi.fn();
    vi.mocked(useWebSocket).mockImplementationOnce(() => ({
      connected: true,
      status: "thinking",
      lastMessage: "",
      sendTask: localSendTask,
    }));
    const { container } = render(<Agent wsUrl="ws://test" />);
    const textarea = screen.getByRole("textbox");
    fireEvent.change(textarea, { target: { value: "task" } });
    const form = container.querySelector("form");
    fireEvent.submit(form!);
    expect(localSendTask).not.toHaveBeenCalled();
  });

  it("renders sprite image when idle", () => {
    render(<Agent wsUrl="ws://test" />);
    const img = screen.getByAltText("Claude Agent");
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute("src", "/claude.png");
  });

  it("renders lottie player when working", () => {
    vi.mocked(useWebSocket).mockReturnValueOnce({
      connected: true,
      status: "working",
      lastMessage: "",
      sendTask: mockSendTask,
    } as ReturnType<typeof useWebSocket>);
    render(<Agent wsUrl="ws://test" />);
    expect(screen.getByTestId("lottie-player")).toBeInTheDocument();
  });

  it("renders thinking animation when thinking", () => {
    vi.mocked(useWebSocket).mockReturnValueOnce({
      connected: true,
      status: "thinking",
      lastMessage: "",
      sendTask: mockSendTask,
    } as ReturnType<typeof useWebSocket>);
    render(<Agent wsUrl="ws://test" />);
    const img = screen.getByAltText("Claude Agent");
    expect(img).toHaveClass("animate-agent-thinking");
  });

  it("renders response bubble when lastMessage is set", () => {
    vi.mocked(useWebSocket).mockReturnValueOnce({
      connected: true,
      status: "idle",
      lastMessage: "hello user",
      sendTask: mockSendTask,
    } as ReturnType<typeof useWebSocket>);
    render(<Agent wsUrl="ws://test" />);
    expect(screen.getByText("hello user")).toBeInTheDocument();
  });
});
