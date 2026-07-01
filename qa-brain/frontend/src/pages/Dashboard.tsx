import { ChatPanel } from "../components/ChatPanel/ChatPanel";
import { TestCasePanel } from "../components/TestCasePanel/TestCasePanel";
import { useAgentChat } from "../hooks/useAgentChat";

const SESSION_ID = crypto.randomUUID();
const PROJECT_ID = "proj-001";

export default function Dashboard() {
  const { messages, activeAgent, sendMessage, testCases, releaseScore } = useAgentChat(SESSION_ID, PROJECT_ID);

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
        <TestCasePanel testCases={testCases} releaseScore={releaseScore} />
      </main>
    </div>
  );
}
