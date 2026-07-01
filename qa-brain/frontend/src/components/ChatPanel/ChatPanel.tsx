import { useState, useRef, useEffect } from "react";
import type { Message } from "../../lib/types";
import { MessageBubble } from "./MessageBubble";
import { AgentStatusBar } from "./AgentStatusBar";

interface ChatPanelProps {
  messages: Message[];
  activeAgent: string | null;
  onSend: (content: string) => void;
}

export function ChatPanel({ messages, activeAgent, onSend }: ChatPanelProps) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    onSend(input.trim());
    setInput("");
  };

  return (
    <div className="flex flex-col h-full bg-slate-50 rounded-lg border">
      <div className="px-4 py-3 border-b bg-white rounded-t-lg">
        <h2 className="font-semibold text-slate-800">QA Brain</h2>
        <p className="text-xs text-slate-500">ลอง: "Generate test cases for PROJ-123"</p>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-1">
        {messages.length === 0 && (
          <p className="text-center text-slate-400 text-sm mt-8">
            พิมพ์ Story ID หรือ Sprint ID เพื่อเริ่มต้น
          </p>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        <div ref={bottomRef} />
      </div>

      <AgentStatusBar activeAgent={activeAgent} />

      <form onSubmit={handleSubmit} className="p-3 border-t bg-white rounded-b-lg flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="เช่น Generate test cases for PROJ-123"
          className="flex-1 border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-300"
        />
        <button
          type="submit"
          disabled={!input.trim() || !!activeAgent}
          className="bg-slate-800 text-white px-4 py-2 rounded text-sm font-medium hover:bg-slate-700 disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}
