import { useState } from "react";
import { ChatPanel } from "../components/ChatPanel/ChatPanel";
import { TestCasePanel } from "../components/TestCasePanel/TestCasePanel";
import { ScriptsPanel } from "../components/ScriptsPanel/ScriptsPanel";
import { useAgentChat } from "../hooks/useAgentChat";

const SESSION_ID = crypto.randomUUID();
const PROJECT_ID = "proj-001";

type RightPanel = "test-cases" | "scripts";

export default function Dashboard() {
  const { messages, activeAgent, sendMessage, testCases, releaseScore, scripts } = useAgentChat(SESSION_ID, PROJECT_ID);
  const [rightPanel, setRightPanel] = useState<RightPanel>("test-cases");

  return (
    <div className="h-screen flex flex-col bg-slate-100">
      <header className="px-6 py-3 bg-white border-b flex items-center gap-3">
        <div className="h-8 w-8 rounded bg-slate-800 flex items-center justify-center">
          <span className="text-white text-xs font-bold">QA</span>
        </div>
        <span className="font-semibold text-slate-800">QA Brain</span>
        <span className="text-xs text-slate-400 ml-auto">AI-Powered Quality Engineering</span>
      </header>

      <main className="flex-1 grid grid-cols-2 gap-4 p-4 overflow-hidden">
        <ChatPanel messages={messages} activeAgent={activeAgent} onSend={sendMessage} />

        <div className="flex flex-col h-full min-h-0 gap-2">
          <div className="flex gap-1">
            <button
              onClick={() => setRightPanel("test-cases")}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                rightPanel === "test-cases" ? "bg-slate-800 text-white" : "bg-white border text-slate-600 hover:bg-slate-50"
              }`}
            >
              Test Cases ({testCases.length})
            </button>
            <button
              onClick={() => setRightPanel("scripts")}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                rightPanel === "scripts" ? "bg-slate-800 text-white" : "bg-white border text-slate-600 hover:bg-slate-50"
              }`}
            >
              Scripts ({scripts.length})
            </button>
          </div>

          <div className="flex-1 min-h-0">
            {rightPanel === "test-cases" ? (
              <TestCasePanel testCases={testCases} releaseScore={releaseScore} />
            ) : (
              <ScriptsPanel scripts={scripts} />
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
