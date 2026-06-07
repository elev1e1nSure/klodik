import { useState, useEffect } from "react";
import { Send } from "lucide-react";
import { useWebSocket } from "../hooks/useWebSocket";
import { DotLottieReact } from "@lottiefiles/dotlottie-react";

interface AgentProps {
  wsUrl?: string;
}

export default function Agent({ wsUrl = "ws://localhost:8765/ws" }: AgentProps) {
  const [task, setTask] = useState("");
  const [displayMessage, setDisplayMessage] = useState("");
  const [fadeOut, setFadeOut] = useState(true);
  const { connected, status, lastMessage, sendTask } = useWebSocket(wsUrl);

  useEffect(() => {
    if (lastMessage) {
      console.log("[Agent] lastMessage:", lastMessage);
      setFadeOut(false);
      setDisplayMessage(lastMessage);
      const duration = Math.min(8000, Math.max(2500, lastMessage.length * 80));
      const fadeTimer = setTimeout(() => setFadeOut(true), duration);
      const clearTimer = setTimeout(() => setDisplayMessage(""), duration + 500);
      return () => {
        clearTimeout(fadeTimer);
        clearTimeout(clearTimer);
      };
    }
  }, [lastMessage]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!task.trim() || !connected || status !== "idle") return;
    sendTask(task);
    setTask("");
  };

  return (
    <div
      className="select-none flex flex-col items-center w-full h-full justify-center"
      data-tauri-drag-region
    >
      {/* Input bubble */}
      <form onSubmit={handleSubmit} className="mb-2 relative w-[200px]" data-tauri-no-drag>
        <div className="flex items-center gap-2 px-4 py-2.5 rounded-full bg-gradient-to-b from-[#3d3834] to-[#2a2723]">
          <textarea
            value={task}
            onChange={(e) => setTask(e.target.value)}
            placeholder="What can I help you with today?"
            className="flex-1 text-sm text-[#9f9c95] bg-transparent resize-none outline-none placeholder-gray-400 no-scrollbar"
            rows={1}
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
            disabled={!connected || status !== "idle" || !task.trim()}
            className="flex items-center justify-center w-7 h-7 bg-gray-600 rounded-full disabled:opacity-40 shrink-0"
          >
            <Send size={16} strokeWidth={2.5} className="text-white" />
          </button>
        </div>
      </form>

      {/* Response bubble */}
      <div
        className={`rounded-lg bg-gray-800/90 text-[#9f9c95] text-xs max-w-[220px] leading-relaxed overflow-hidden transition-all duration-500 ease-out ${fadeOut ? "max-h-0 opacity-0 mb-0 py-0 px-0" : "max-h-48 opacity-100 mb-2 py-2 px-3"}`}
      >
        {displayMessage}
      </div>

      {/* Sprite */}
      <div className="relative w-[128px] h-[128px] flex-shrink-0" style={{ transform: "translateZ(0)" }}>
        <div className={`absolute inset-0 ${status !== "idle" ? "opacity-100" : "opacity-0"}`}>
          <DotLottieReact
            src="/claude_animated.lottie"
            autoplay
            loop
            style={{ width: "128px", height: "128px" }}
            className="block"
          />
        </div>
        <div className={`absolute inset-0 flex items-center justify-center ${status === "idle" ? "opacity-100" : "opacity-0"}`}>
          <img
            src="/claude.png"
            alt="Claude Agent"
            className="absolute w-[128px] h-[128px]"
            style={{ top: 0, left: 0 }}
            draggable={false}
          />
        </div>
      </div>
    </div>
  );
}
