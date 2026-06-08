import { useState, useEffect } from "react";
import { Send } from "lucide-react";
import { useWebSocket } from "../hooks/useWebSocket";

interface AgentProps {
  wsUrl?: string;
}

const MIN_MESSAGE_DURATION_MS = 2500;
const MAX_MESSAGE_DURATION_MS = 8000;
const CHAR_DURATION_MS = 80;
const FADE_OUT_EXTRA_MS = 500;

export default function Agent({ wsUrl = "ws://localhost:8765/ws" }: AgentProps) {
  const [task, setTask] = useState("");
  const [displayMessage, setDisplayMessage] = useState("");
  const [fadeOut, setFadeOut] = useState(true);
  const { connected, status, lastMessage, lastError, sendTask } = useWebSocket(wsUrl);

  useEffect(() => {
    const content = lastError || lastMessage;
    if (!content) return;

    console.log("[Agent] display:", content);
    setFadeOut(false);
    setDisplayMessage(content);
    const duration = Math.min(
      MAX_MESSAGE_DURATION_MS,
      Math.max(MIN_MESSAGE_DURATION_MS, content.length * CHAR_DURATION_MS)
    );
    const fadeTimer = setTimeout(() => setFadeOut(true), duration);
    const clearTimer = setTimeout(() => setDisplayMessage(""), duration + FADE_OUT_EXTRA_MS);
    return () => {
      clearTimeout(fadeTimer);
      clearTimeout(clearTimer);
    };
  }, [lastMessage, lastError]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!task.trim() || !connected || status !== "idle") return;
    sendTask(task);
    setTask("");
  };

  const isWorking = status === "working";
  const isThinking = status === "thinking";
  const isBusy = isWorking || isThinking;

  return (
    <div
      className="select-none flex flex-col items-center w-full h-full justify-center cursor-grab active:cursor-grabbing"
      data-tauri-drag-region
    >
      {/* Response bubble */}
      <div
        aria-live="polite"
        className={`rounded-lg bg-gray-800/90 text-[#9f9c95] text-xs max-w-[286px] leading-relaxed overflow-hidden transition-all duration-500 ease-out ${fadeOut ? "max-h-0 opacity-0 mb-0 py-0 px-0" : "max-h-48 opacity-100 mb-2 py-2 px-3"}`}
      >
        {displayMessage}
      </div>

      {/* Input bubble */}
      <form onSubmit={handleSubmit} className="mb-2 relative w-[260px]" data-tauri-no-drag>
        <div className="flex items-center gap-2 px-4 py-2.5 rounded-full bg-gradient-to-b from-[#3d3834] to-[#2a2723]">
          <textarea
            value={task}
            onChange={(e) => setTask(e.target.value)}
            placeholder="Чем займёмся?"
            className="flex-1 text-sm text-[#9f9c95] bg-transparent resize-none outline-none placeholder-gray-400 no-scrollbar"
            rows={Math.min(5, Math.max(1, task.split("\n").length))}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e);
              }
            }}
          />
          <button
            type="submit"
            aria-label="Send"
            title={!connected ? "Disconnected" : isBusy ? "Agent is busy" : "Send task"}
            disabled={!connected || isBusy || !task.trim()}
            className="flex items-center justify-center w-7 h-7 bg-gray-600 rounded-full disabled:opacity-40 shrink-0"
          >
            <Send size={16} strokeWidth={2.5} className="text-white" />
          </button>
        </div>
      </form>

      {/* Sprite */}
      <div className="relative w-[166px] h-[166px]">
        <img
          src="/app-icon.png"
          alt="Клодик"
          className={`w-full h-full image-pixelated ${
            isWorking
              ? "animate-agent-working"
              : isThinking
                ? "animate-agent-thinking"
                : "animate-agent-idle"
          }`}
          draggable={false}
          data-tauri-drag-region
        />
      </div>
    </div>
  );
}
