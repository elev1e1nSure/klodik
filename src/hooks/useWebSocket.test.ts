import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useWebSocket } from "./useWebSocket";

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  static CLOSED = 3;
  url: string;
  readyState: number = 0;
  onopen: ((e: Event) => void) | null = null;
  onclose: ((e: CloseEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  sent: string[] = [];

  constructor(url: string) {
    this.url = url;
    this.readyState = 1;
    MockWebSocket.instances.push(this);
    setTimeout(() => {
      if (this.onopen) this.onopen(new Event("open"));
    }, 10);
  }

  get OPEN() {
    return 1;
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.readyState = 3;
    if (this.onclose) this.onclose(new CloseEvent("close"));
  }

  static clear() {
    MockWebSocket.instances = [];
  }
}

// @ts-expect-error override global WebSocket for tests
globalThis.WebSocket = MockWebSocket;

describe("useWebSocket", () => {
  beforeEach(() => MockWebSocket.clear());
  afterEach(() => MockWebSocket.clear());

  it("connects and sets connected to true", async () => {
    const { result } = renderHook(() => useWebSocket("ws://test"));
    await waitFor(() => expect(result.current.connected).toBe(true));
    expect(result.current.status).toBe("idle");
  });

  it("receives status updates", async () => {
    const { result } = renderHook(() => useWebSocket("ws://test"));
    await waitFor(() => expect(result.current.connected).toBe(true));

    const ws = MockWebSocket.instances[0];
    ws.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({ type: "status", content: "working" }),
      })
    );

    await waitFor(() => expect(result.current.status).toBe("working"));
  });

  it("receives messages", async () => {
    const { result } = renderHook(() => useWebSocket("ws://test"));
    await waitFor(() => expect(result.current.connected).toBe(true));

    const ws = MockWebSocket.instances[0];
    ws.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({ type: "message", content: "hello" }),
      })
    );

    await waitFor(() => expect(result.current.lastMessage).toBe("hello"));
  });

  it("sendTask sends JSON payload", async () => {
    const { result } = renderHook(() => useWebSocket("ws://test"));
    await waitFor(() => expect(result.current.connected).toBe(true));

    result.current.sendTask("do something");

    const ws = MockWebSocket.instances[0];
    expect(ws.sent).toHaveLength(1);
    const payload = JSON.parse(ws.sent[0]);
    expect(payload).toEqual({ type: "task", content: "do something" });
  });

  it("ignores invalid JSON messages", async () => {
    const { result } = renderHook(() => useWebSocket("ws://test"));
    await waitFor(() => expect(result.current.connected).toBe(true));

    const ws = MockWebSocket.instances[0];
    ws.onmessage?.(
      new MessageEvent("message", { data: "not json" })
    );

    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(result.current.lastMessage).toBe("");
  });

  it("sets connected to false on close", async () => {
    const { result } = renderHook(() => useWebSocket("ws://test"));
    await waitFor(() => expect(result.current.connected).toBe(true));

    const ws = MockWebSocket.instances[0];
    ws.onclose?.(new CloseEvent("close"));

    await waitFor(() => expect(result.current.connected).toBe(false));
  });

  it("sets connected to false on error", async () => {
    const { result } = renderHook(() => useWebSocket("ws://test"));
    await waitFor(() => expect(result.current.connected).toBe(true));

    const ws = MockWebSocket.instances[0];
    ws.onerror?.(new Event("error"));

    await waitFor(() => expect(result.current.connected).toBe(false));
  });
});
