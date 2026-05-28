"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { UserButton } from "@clerk/nextjs";
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Loader2,
  Plus,
  Send,
  Trash2,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { streamQuery } from "@/lib/api";
import type { SourceInfo } from "@/lib/types";
import {
  createSession,
  deleteSession,
  getSessions,
  updateSession,
} from "@/lib/sessions";
import type { Message, Session } from "@/lib/sessions";

interface UIMessage extends Message {
  status?: string;
  isStreaming?: boolean;
}

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function ConfidenceBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const cls =
    score >= 0.8
      ? "text-green-400 bg-green-900/30 border-green-800"
      : score >= 0.5
        ? "text-yellow-400 bg-yellow-900/30 border-yellow-800"
        : "text-red-400 bg-red-900/30 border-red-800";
  return (
    <span
      className={`inline-flex items-center text-[11px] px-1.5 py-0.5 rounded border font-mono ${cls}`}
    >
      {pct}% confidence
    </span>
  );
}

function SourcePanel({ sources }: { sources: SourceInfo[] }) {
  const [open, setOpen] = useState(false);
  if (!sources.length) return null;
  return (
    <div className="mt-3 border border-[#1E1E2E] rounded-md overflow-hidden">
      <button
        onClick={() => setOpen((p) => !p)}
        className="w-full flex items-center justify-between px-3 py-2 text-xs text-zinc-500 hover:text-zinc-300 hover:bg-[#12121A] transition-colors"
      >
        <span>
          {sources.length} source{sources.length > 1 ? "s" : ""}
        </span>
        {open ? (
          <ChevronUp className="w-3.5 h-3.5" />
        ) : (
          <ChevronDown className="w-3.5 h-3.5" />
        )}
      </button>
      {open && (
        <div className="divide-y divide-[#1E1E2E]">
          {sources.map((src, i) => (
            <div key={i} className="px-3 py-2.5 bg-[#0D0D14]">
              <div className="flex items-center justify-between gap-2 mb-1">
                <span className="text-xs text-zinc-300 font-medium truncate max-w-[60%]">
                  {src.doc_title}
                </span>
                <div className="flex items-center gap-1.5 shrink-0">
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#1E1E2E] text-zinc-400 font-mono">
                    {src.element_type}
                  </span>
                  <span className="text-[10px] text-zinc-500 font-mono">
                    {Math.round(src.relevance_score * 100)}%
                  </span>
                </div>
              </div>
              <div className="w-full h-1 bg-[#1E1E2E] rounded-full mb-2">
                <div
                  className="h-1 bg-blue-600 rounded-full"
                  style={{ width: `${Math.round(src.relevance_score * 100)}%` }}
                />
              </div>
              <p className="text-[11px] text-zinc-500 leading-relaxed line-clamp-2">
                {src.snippet}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StatusIndicator({ status }: { status: string }) {
  return (
    <div className="flex items-center gap-2 text-xs text-zinc-500 py-1">
      <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />
      <span>{status}</span>
    </div>
  );
}

function MessageItem({ msg }: { msg: UIMessage }) {
  const isUser = msg.role === "user";
  const latencySec =
    msg.latencyMs !== undefined ? (msg.latencyMs / 1000).toFixed(1) : null;

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] px-4 py-2.5 rounded-2xl rounded-tr-sm bg-blue-600/20 border border-blue-500/20 text-sm text-zinc-100 leading-relaxed">
          {msg.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] space-y-1">
        <div className="px-4 py-3 rounded-2xl rounded-tl-sm bg-[#12121A] border border-[#1E1E2E] text-sm text-zinc-200 leading-relaxed whitespace-pre-wrap">
          {msg.isStreaming && !msg.content && msg.status ? (
            <StatusIndicator status={msg.status} />
          ) : (
            <>
              {msg.status && !msg.content && (
                <StatusIndicator status={msg.status} />
              )}
              {msg.content && (
                <span>
                  {msg.content}
                  {msg.isStreaming && (
                    <span className="inline-block w-0.5 h-4 bg-blue-400 ml-0.5 animate-pulse align-text-bottom" />
                  )}
                </span>
              )}
            </>
          )}
        </div>

        {!msg.isStreaming && (
          <div className="px-1 flex flex-wrap items-center gap-x-3 gap-y-1">
            {msg.confidence !== undefined && (
              <ConfidenceBadge score={msg.confidence} />
            )}
            {latencySec && (
              <span className="text-[11px] text-zinc-600 font-mono">
                {msg.cacheHit ? "cache hit · " : ""}
                {latencySec}s
              </span>
            )}
            {msg.traceId && (
              <a
                href={`https://smith.langchain.com/public/${msg.traceId}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-[11px] text-zinc-600 hover:text-blue-400 transition-colors"
              >
                View trace
                <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>
        )}

        {!msg.isStreaming && msg.sources && msg.sources.length > 0 && (
          <div className="px-1">
            <SourcePanel sources={msg.sources} />
          </div>
        )}
      </div>
    </div>
  );
}

function Sidebar({
  sessions,
  currentId,
  onSelect,
  onNew,
  onDelete,
  collapsed,
  onToggle,
}: {
  sessions: Session[];
  currentId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  collapsed: boolean;
  onToggle: () => void;
}) {
  return (
    <aside
      className={`flex flex-col border-r border-[#1E1E2E] bg-[#0D0D14] transition-all duration-200 ${
        collapsed ? "w-12" : "w-64"
      } shrink-0`}
    >
      <div className="flex items-center justify-between p-3 border-b border-[#1E1E2E]">
        {!collapsed && (
          <button
            onClick={onNew}
            className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-100 px-2 py-1.5 rounded hover:bg-[#1E1E2E] transition-colors flex-1"
          >
            <Plus className="w-3.5 h-3.5" />
            New Chat
          </button>
        )}
        <button
          onClick={onToggle}
          className="p-1.5 rounded hover:bg-[#1E1E2E] text-zinc-500 hover:text-zinc-300 transition-colors ml-auto"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? (
            <ChevronRight className="w-4 h-4" />
          ) : (
            <ChevronLeft className="w-4 h-4" />
          )}
        </button>
      </div>

      {collapsed ? (
        <div className="flex flex-col items-center py-2 gap-1">
          <button
            onClick={onNew}
            className="p-2 rounded hover:bg-[#1E1E2E] text-zinc-500 hover:text-zinc-300 transition-colors"
            aria-label="New Chat"
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>
      ) : (
        <nav className="flex-1 overflow-y-auto py-2 min-h-0">
          {sessions.length === 0 && (
            <p className="text-xs text-zinc-600 px-4 py-3">No sessions yet</p>
          )}
          {sessions.map((s) => (
            <div
              key={s.id}
              className={`group flex items-center gap-1 px-2 py-1.5 mx-2 rounded cursor-pointer transition-colors ${
                s.id === currentId
                  ? "bg-[#1E1E2E] text-zinc-100"
                  : "text-zinc-500 hover:text-zinc-300 hover:bg-[#12121A]"
              }`}
              onClick={() => onSelect(s.id)}
            >
              <span className="text-xs truncate flex-1">{s.title}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(s.id);
                }}
                className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:text-red-400 transition-all"
                aria-label="Delete session"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))}
        </nav>
      )}
    </aside>
  );
}

export default function ChatPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    const stored = getSessions();
    setSessions(stored);
    if (stored.length > 0) {
      setCurrentSessionId(stored[0].id);
      setMessages(stored[0].messages as UIMessage[]);
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  function handleNewChat() {
    const session = createSession();
    setSessions(getSessions());
    setCurrentSessionId(session.id);
    setMessages([]);
    setConnectionError(null);
    inputRef.current?.focus();
  }

  function handleSelectSession(id: string) {
    const session = sessions.find((s) => s.id === id);
    if (!session) return;
    setCurrentSessionId(id);
    setMessages(session.messages as UIMessage[]);
    setConnectionError(null);
  }

  function handleDeleteSession(id: string) {
    deleteSession(id);
    const updated = getSessions();
    setSessions(updated);
    if (id === currentSessionId) {
      if (updated.length > 0) {
        setCurrentSessionId(updated[0].id);
        setMessages(updated[0].messages as UIMessage[]);
      } else {
        setCurrentSessionId(null);
        setMessages([]);
      }
    }
  }

  function persistMessages(sessionId: string, msgs: UIMessage[]) {
    const clean: Message[] = msgs
      .filter((m) => !m.isStreaming || m.content)
      .map(({ status: _s, isStreaming: _i, ...rest }) => rest);
    updateSession(sessionId, clean);
    setSessions(getSessions());
  }

  async function handleSubmit() {
    if (!input.trim() || isStreaming) return;

    setConnectionError(null);

    let sessionId = currentSessionId;
    if (!sessionId) {
      const s = createSession();
      sessionId = s.id;
      setCurrentSessionId(sessionId);
      setSessions(getSessions());
    }

    const userMsg: UIMessage = {
      id: generateId(),
      role: "user",
      content: input.trim(),
      timestamp: Date.now(),
    };

    const assistantId = generateId();
    const assistantMsg: UIMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      sources: [],
      timestamp: Date.now(),
      status: "Connecting...",
      isStreaming: true,
    };

    const nextMessages = [...messages, userMsg, assistantMsg];
    setMessages(nextMessages);
    setInput("");
    setIsStreaming(true);

    let accumulated = "";
    const accumulatedSources: SourceInfo[] = [];

    abortRef.current = streamQuery(input.trim(), {
      onStatus(status) {
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, status } : m))
        );
      },
      onSource(source) {
        accumulatedSources.push(source);
      },
      onToken(token) {
        accumulated += token;
        const snap = accumulated;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: snap, status: undefined }
              : m
          )
        );
      },
      onDone(meta) {
        const finalSources =
          meta.sources && meta.sources.length > 0
            ? meta.sources
            : accumulatedSources;
        setMessages((prev) => {
          const updated = prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  content: accumulated || m.content,
                  sources: finalSources,
                  confidence: meta.confidence,
                  traceId: meta.trace_id,
                  latencyMs: meta.latency_ms,
                  cacheHit: meta.cache_hit,
                  isStreaming: false,
                  status: undefined,
                }
              : m
          );
          if (sessionId) persistMessages(sessionId, updated);
          return updated;
        });
        setIsStreaming(false);
        abortRef.current = null;
      },
      onError(message) {
        setMessages((prev) => {
          const updated = prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  content: accumulated || "",
                  isStreaming: false,
                  status: undefined,
                }
              : m
          );
          if (sessionId) persistMessages(sessionId, updated);
          return updated;
        });
        setConnectionError(message);
        setIsStreaming(false);
        abortRef.current = null;
      },
    });
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSubmit();
    }
  }

  function handleAbort() {
    abortRef.current?.abort();
    abortRef.current = null;
    setIsStreaming(false);
    setMessages((prev) =>
      prev.map((m) =>
        m.isStreaming ? { ...m, isStreaming: false, status: undefined } : m
      )
    );
  }

  return (
    <div className="flex flex-col h-screen bg-[#0A0A0F] text-zinc-100 overflow-hidden">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-[#1E1E2E] bg-[#0D0D14] shrink-0 z-10">
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-zinc-300">
            Harness Engineering RAG
          </span>
        </div>
        <div className="flex items-center gap-3">
          <a
            href="https://smith.langchain.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors flex items-center gap-1"
          >
            LangSmith
            <ExternalLink className="w-3 h-3" />
          </a>
          <UserButton
            appearance={{
              elements: {
                avatarBox: "w-7 h-7",
              },
            }}
          />
        </div>
      </header>

      {/* Body */}
      <div className="flex flex-1 min-h-0">
        <Sidebar
          sessions={sessions}
          currentId={currentSessionId}
          onSelect={handleSelectSession}
          onNew={handleNewChat}
          onDelete={handleDeleteSession}
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed((p) => !p)}
        />

        {/* Chat area */}
        <main className="flex flex-col flex-1 min-w-0">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4 min-h-0">
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full text-center">
                <p className="text-zinc-600 text-sm mb-2">
                  No messages yet. Ask something to get started.
                </p>
                <p className="text-zinc-700 text-xs">
                  Try: &quot;What is a wiring harness?&quot;
                </p>
              </div>
            )}

            {messages.map((msg) => (
              <MessageItem key={msg.id} msg={msg} />
            ))}

            {connectionError && (
              <div className="flex items-center gap-2 text-xs text-red-400 border border-red-900/40 bg-red-900/10 rounded-lg px-4 py-3">
                <span>Connection error: {connectionError}</span>
                <button
                  onClick={() => setConnectionError(null)}
                  className="ml-auto text-zinc-500 hover:text-zinc-300"
                >
                  Dismiss
                </button>
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div className="shrink-0 border-t border-[#1E1E2E] bg-[#0D0D14] px-4 py-3">
            <div className="max-w-3xl mx-auto flex items-end gap-2">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isStreaming}
                rows={1}
                placeholder="Ask about harness engineering..."
                className="flex-1 resize-none bg-[#12121A] border border-[#1E1E2E] rounded-xl px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-zinc-600 transition-colors disabled:opacity-50 max-h-40 overflow-y-auto leading-relaxed"
                style={{
                  height: "auto",
                  minHeight: "42px",
                }}
                onInput={(e) => {
                  const el = e.currentTarget;
                  el.style.height = "auto";
                  el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
                }}
              />
              {isStreaming ? (
                <button
                  onClick={handleAbort}
                  className="shrink-0 w-9 h-9 rounded-xl bg-[#1E1E2E] hover:bg-zinc-700 border border-zinc-700 flex items-center justify-center transition-colors"
                  aria-label="Stop streaming"
                >
                  <span className="w-3 h-3 bg-zinc-400 rounded-sm" />
                </button>
              ) : (
                <button
                  onClick={() => void handleSubmit()}
                  disabled={!input.trim() || isStreaming}
                  className="shrink-0 w-9 h-9 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center transition-colors"
                  aria-label="Send message"
                >
                  <Send className="w-4 h-4" />
                </button>
              )}
            </div>
            <p className="text-center text-[10px] text-zinc-700 mt-2 max-w-3xl mx-auto">
              Shift+Enter for newline · Enter to send
            </p>
          </div>
        </main>
      </div>
    </div>
  );
}
