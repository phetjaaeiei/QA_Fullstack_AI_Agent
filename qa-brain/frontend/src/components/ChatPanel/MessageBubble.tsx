import type { Message } from "../../lib/types";

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3`}>
      <div
        className={`max-w-[80%] rounded-lg px-4 py-2 text-sm whitespace-pre-wrap ${
          isUser
            ? "bg-slate-800 text-white"
            : "bg-white border border-slate-200 text-slate-800"
        }`}
      >
        {message.content}
        {message.link && (
          <div className="mt-2">
            <a
              href={message.link.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block text-xs font-medium text-blue-600 hover:text-blue-800 underline"
            >
              {message.link.label} ↗
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
