"use client";

import { useState, useRef, useEffect } from "react";

interface ToolCallLog {
  tool: string;
  input: unknown;
  output: unknown;
  error?: string;
}

interface ChatResponse {
  answer: string;
  toolCalls: ToolCallLog[];
  mcpClientKind: "real" | "mock";
  error?: string;
}

interface ChatMessage {
  role: "user" | "agent";
  text: string;
  toolCalls?: ToolCallLog[];
  mcpClientKind?: "real" | "mock";
  isError?: boolean;
}

const EXAMPLE_QUESTIONS = [
  "현재 가장 최근 데이터는 뭐야?",
  "최근 7일간 megabox 리뷰 평균 평점이 어떻게 돼?",
  "최근 일주일 평균 평점과 그 이전 일주일 평균을 비교해줘.",
  "지금 DB에 어떤 사이트 데이터가 있어?",
];

export default function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function send(question: string) {
    const text = question.trim();
    if (!text || loading) return;

    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      const data: ChatResponse = await res.json();

      if (!res.ok || data.error) {
        setMessages((prev) => [
          ...prev,
          { role: "agent", text: data.error || "오류가 발생했습니다.", isError: true },
        ]);
        return;
      }

      setMessages((prev) => [
        ...prev,
        {
          role: "agent",
          text: data.answer,
          toolCalls: data.toolCalls,
          mcpClientKind: data.mcpClientKind,
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "agent", text: "네트워크 오류로 답변을 받지 못했습니다.", isError: true },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col h-full max-w-3xl w-full mx-auto p-4 gap-4">
      <header className="border-b border-black/10 pb-3">
        <h1 className="text-lg font-semibold">Data Analysis Agent</h1>
        <p className="text-sm text-black/60">
          megabox / naver / kinolights 영화 리뷰 DB를 MCP Tool로 조회·분석합니다.
        </p>
      </header>

      <div className="flex-1 overflow-y-auto flex flex-col gap-4 min-h-[300px]">
        {messages.length === 0 && (
          <div className="flex flex-col gap-2 text-sm text-black/60">
            <p>이런 질문을 해보세요:</p>
            <div className="flex flex-col gap-1.5">
              {EXAMPLE_QUESTIONS.map((q) => (
                <button
                  key={q}
                  onClick={() => send(q)}
                  className="text-left rounded-md border border-black/10 px-3 py-2 hover:bg-black/5 transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${
                m.role === "user"
                  ? "bg-blue-600 text-white"
                  : m.isError
                    ? "bg-red-50 text-red-700 border border-red-200"
                    : "bg-black/5"
              }`}
            >
              <div>{m.text}</div>
              {m.role === "agent" && m.toolCalls && m.toolCalls.length > 0 && (
                <details className="mt-2 text-xs text-black/60">
                  <summary className="cursor-pointer select-none">
                    MCP Tool 호출 {m.toolCalls.length}건
                    {m.mcpClientKind && (
                      <span
                        className={`ml-2 rounded px-1.5 py-0.5 ${
                          m.mcpClientKind === "real"
                            ? "bg-green-100 text-green-700"
                            : "bg-yellow-100 text-yellow-700"
                        }`}
                      >
                        {m.mcpClientKind === "real" ? "실제 MCP 서버" : "Mock 데이터 (개발용)"}
                      </span>
                    )}
                  </summary>
                  <ul className="mt-1 flex flex-col gap-1">
                    {m.toolCalls.map((tc, j) => (
                      <li key={j} className="rounded bg-white/60 border border-black/10 p-1.5">
                        <div className="font-mono">
                          {tc.tool}({JSON.stringify(tc.input)})
                        </div>
                        {tc.error ? (
                          <div className="text-red-600">error: {tc.error}</div>
                        ) : (
                          <div className="truncate">→ {JSON.stringify(tc.output)}</div>
                        )}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          </div>
        ))}

        {loading && <div className="text-sm text-black/40">Agent가 MCP로 데이터를 조회하는 중...</div>}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="flex gap-2 border-t border-black/10 pt-3"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="질문을 입력하세요..."
          className="flex-1 rounded-md border border-black/15 px-3 py-2 text-sm outline-none focus:border-blue-500"
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="rounded-md bg-blue-600 text-white px-4 py-2 text-sm disabled:opacity-40"
        >
          전송
        </button>
      </form>
    </div>
  );
}
