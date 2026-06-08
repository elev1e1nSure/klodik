import { useEffect, useRef, useState, useCallback } from "react";

export type AgentStatus = "idle" | "thinking" | "working";

interface StatusMessage {
  type: "status";
  content: AgentStatus;
}

interface TextMessage {
  type: "message";
  content: string;
}

interface ErrorMessage {
  type: "error";
  content: string;
}

type WSMessage = StatusMessage | TextMessage | ErrorMessage;

const MAX_RECONNECT_ATTEMPTS = 5;
const BASE_RECONNECT_DELAY_MS = 1000;

function parseMessage(data: unknown): WSMessage | null {
  if (typeof data !== "string") return null;
  try {
    const parsed = JSON.parse(data) as WSMessage;
    if (
      parsed &&
      typeof parsed.type === "string" &&
      typeof parsed.content === "string" &&
      ["status", "message", "error"].includes(parsed.type)
    ) {
      return parsed;
    }
  } catch {
    // ignore invalid JSON
  }
  return null;
}

/**
 * Hook that manages a WebSocket connection to the sidecar agent.
 *
 * Features:
 * - Automatic reconnect with exponential backoff (max 5 attempts)
 * - Typed message handling (status / message / error)
 * - Cleanup on unmount
 */
export function useWebSocket(url: string) {
  const ws = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [connected, setConnected] = useState(false);
  const [status, setStatus] = useState<AgentStatus>("idle");
  const [lastMessage, setLastMessage] = useState<string>("");
  const [lastError, setLastError] = useState<string>("");

  const connect = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }

    try {
      const socket = new WebSocket(url);
      ws.current = socket;

      socket.onopen = () => {
        reconnectAttempts.current = 0;
        setConnected(true);
        setLastError("");
      };

      socket.onclose = () => {
        setConnected(false);
        ws.current = null;
        if (reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
          const delay =
            BASE_RECONNECT_DELAY_MS * 2 ** reconnectAttempts.current;
          reconnectAttempts.current += 1;
          reconnectTimer.current = setTimeout(connect, delay);
        }
      };

      socket.onerror = () => {
        setConnected(false);
        // onclose will trigger reconnect logic
      };

      socket.onmessage = (event) => {
        const data = parseMessage(event.data);
        if (!data) return;
        if (data.type === "status") {
          setStatus(data.content);
        } else if (data.type === "message") {
          setLastMessage(data.content);
        } else if (data.type === "error") {
          setLastError(data.content);
        }
      };
    } catch (err) {
      setLastError(`WebSocket connection failed: ${String(err)}`);
    }
  }, [url]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
      }
      if (ws.current) {
        ws.current.close();
        ws.current = null;
      }
    };
  }, [connect]);

  const sendTask = useCallback(
    (task: string) => {
      if (ws.current && ws.current.readyState === WebSocket.OPEN) {
        ws.current.send(JSON.stringify({ type: "task", content: task }));
      }
    },
    []
  );

  return { connected, status, lastMessage, lastError, sendTask };
}
