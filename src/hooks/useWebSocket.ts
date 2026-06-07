import { useEffect, useRef, useState, useCallback } from "react";

export type AgentStatus = "idle" | "thinking" | "working";

interface WSMessage {
  type: "status" | "message" | "error";
  content: string;
}

export function useWebSocket(url: string) {
  const ws = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [status, setStatus] = useState<AgentStatus>("idle");
  const [lastMessage, setLastMessage] = useState<string>("");

  useEffect(() => {
    const socket = new WebSocket(url);
    ws.current = socket;

    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onerror = () => setConnected(false);

    socket.onmessage = (event) => {
      try {
        const data: WSMessage = JSON.parse(event.data);
        if (data.type === "status") {
          setStatus(data.content as AgentStatus);
        } else if (data.type === "message") {
          setLastMessage(data.content);
        }
      } catch {
        // ignore non-json
      }
    };

    return () => {
      socket.close();
    };
  }, [url]);

  const sendTask = useCallback(
    (task: string) => {
      if (ws.current && ws.current.readyState === WebSocket.OPEN) {
        ws.current.send(JSON.stringify({ type: "task", content: task }));
      }
    },
    []
  );

  return { connected, status, lastMessage, sendTask };
}
