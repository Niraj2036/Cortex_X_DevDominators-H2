"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Send,
  Paperclip,
  RotateCcw,
  Wifi,
  WifiOff,
  CheckCheck,
  Zap,
} from "lucide-react";
import {
  useWebSocketChat,
  type ChatMessage,
} from "@/hooks/useWebSocketChat";

// ── Agent color map ─────────────────────────────────────────────────

const AGENT_COLORS: Record<string, string> = {
  user: "#06b6d4",
  system: "#64748b",
  gemini: "#38bdf8",
  triage: "#06b6d4",
  advocate: "#60a5fa",
  skeptic: "#f59e0b",
  inquisitor: "#a78bfa",
  cortex: "#c084fc",
  scribe: "#34d399",
  peer_rating: "#818cf8",
};

// ── Time formatter ──────────────────────────────────────────────────

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

// ── Message Bubble ──────────────────────────────────────────────────

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.type === "user";
  const isSystem = msg.type === "system" && msg.agentRole === "system";
  const color = msg.agentColor || AGENT_COLORS[msg.agentRole || "system"] || "#64748b";

  // System messages render as centered notices
  if (isSystem) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex justify-center my-3"
      >
        <div className="rounded-lg bg-slate-800/60 px-4 py-2 text-xs text-slate-400 border border-slate-700/40">
          {msg.agentEmoji} {msg.content}
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      className={`flex gap-3 my-2 ${isUser ? "flex-row-reverse" : "flex-row"}`}
    >
      {/* Avatar */}
      <div
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-lg"
        style={{
          backgroundColor: `${color}15`,
          border: `2px solid ${color}40`,
        }}
      >
        {msg.agentEmoji || "🤖"}
      </div>

      {/* Bubble */}
      <div
        className={`max-w-[75%] ${isUser ? "items-end" : "items-start"}`}
      >
        {/* Agent name */}
        {!isUser && (
          <div
            className="mb-1 text-xs font-semibold pl-1"
            style={{ color }}
          >
            {msg.agentName}
          </div>
        )}

        {/* Content */}
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
            isUser
              ? "bg-cyan-600/20 border border-cyan-500/30 text-cyan-50 rounded-br-md"
              : "bg-slate-800/70 border border-slate-700/50 text-slate-200 rounded-bl-md"
          }`}
          style={
            !isUser
              ? { borderLeftColor: `${color}50`, borderLeftWidth: "3px" }
              : undefined
          }
        >
          {/* Render content with newlines and basic formatting */}
          {msg.content.split("\n").map((line, i) => {
            // Bold: **text**
            const parts = line.split(/(\*\*[^*]+\*\*)/g);
            return (
              <div key={i} className={i > 0 ? "mt-1" : ""}>
                {parts.map((part, j) => {
                  if (part.startsWith("**") && part.endsWith("**")) {
                    return (
                      <span key={j} className="font-semibold text-white">
                        {part.slice(2, -2)}
                      </span>
                    );
                  }
                  return <span key={j}>{part}</span>;
                })}
              </div>
            );
          })}
        </div>

        {/* Timestamp */}
        <div
          className={`mt-1 flex items-center gap-1 text-[10px] text-slate-500 ${
            isUser ? "justify-end pr-1" : "pl-1"
          }`}
        >
          {formatTime(msg.timestamp)}
          {isUser && <CheckCheck className="h-3 w-3 text-cyan-400" />}
        </div>
      </div>
    </motion.div>
  );
}

// ── Typing Indicator ────────────────────────────────────────────────

function TypingDots({ agents }: { agents: string[] }) {
  if (agents.length === 0) return null;

  const label =
    agents.length === 1
      ? `${agents[0]} is analyzing...`
      : `${agents.join(", ")} are analyzing...`;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      className="flex items-center gap-3 my-2 ml-12"
    >
      <div className="flex items-center gap-2 rounded-2xl bg-slate-800/60 border border-slate-700/40 px-4 py-3">
        <div className="flex gap-1">
          {[0, 1, 2].map((i) => (
            <motion.div
              key={i}
              className="h-2 w-2 rounded-full bg-slate-400"
              animate={{ y: [0, -5, 0] }}
              transition={{
                repeat: Infinity,
                duration: 0.6,
                delay: i * 0.15,
              }}
            />
          ))}
        </div>
        <span className="text-xs text-slate-400">{label}</span>
      </div>
    </motion.div>
  );
}

// ── Main Chat View ──────────────────────────────────────────────────

export default function ChatView() {
  const [inputText, setInputText] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const {
    messages,
    typingAgents,
    isConnected,
    isComplete,
    sessionId,
    sendDiagnosis,
    reset,
  } = useWebSocketChat();

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, typingAgents]);

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = "auto";
      ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`;
    }
  }, [inputText]);

  const handleSend = () => {
    const text = inputText.trim();
    if (!text || isConnected) return;
    sendDiagnosis(text);
    setInputText("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Get currently typing agent names
  const typingNames = Object.values(typingAgents)
    .filter((a) => a.isTyping)
    .map((a) => a.name);

  const hasStarted = messages.length > 0;

  return (
    <div className="flex h-screen flex-col bg-slate-950">
      {/* ── Header ──────────────────────────────────────────────── */}
      <header className="flex items-center justify-between border-b border-slate-800/60 bg-slate-900/80 px-5 py-3 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-cyan-500/10 text-lg">
            🧠
          </div>
          <div>
            <h1 className="text-sm font-bold text-white tracking-wide">
              OMNI_CORTEX<span className="text-cyan-400">X</span>
            </h1>
            <p className="text-[11px] text-slate-400">
              {sessionId
                ? `Session: ${sessionId}`
                : "Multi-Agent Diagnostic Chat"}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Connection status */}
          <div className="flex items-center gap-1.5">
            {isConnected ? (
              <>
                <Wifi className="h-3.5 w-3.5 text-emerald-400" />
                <span className="text-[11px] text-emerald-400 font-medium">
                  Live
                </span>
              </>
            ) : isComplete ? (
              <>
                <CheckCheck className="h-3.5 w-3.5 text-cyan-400" />
                <span className="text-[11px] text-cyan-400 font-medium">
                  Complete
                </span>
              </>
            ) : (
              <>
                <WifiOff className="h-3.5 w-3.5 text-slate-500" />
                <span className="text-[11px] text-slate-500">Offline</span>
              </>
            )}
          </div>

          {/* New case button */}
          {hasStarted && (
            <button
              onClick={reset}
              className="flex items-center gap-1.5 rounded-lg bg-slate-800/60 px-3 py-1.5 text-xs text-slate-400 transition hover:bg-slate-700/60 hover:text-white border border-slate-700/40"
            >
              <RotateCcw className="h-3 w-3" />
              New Case
            </button>
          )}
        </div>
      </header>

      {/* ── Messages Area ───────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-4 py-4 custom-scrollbar">
        {!hasStarted ? (
          /* Empty state */
          <div className="flex h-full flex-col items-center justify-center text-center">
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: "spring", stiffness: 200 }}
              className="mb-6 rounded-full bg-cyan-500/10 p-6"
            >
              <Zap className="h-12 w-12 text-cyan-400" />
            </motion.div>
            <h2 className="text-xl font-bold text-white mb-2">
              Start a Diagnostic Session
            </h2>
            <p className="max-w-md text-sm text-slate-400 mb-6">
              Paste the patient&apos;s clinical data below — symptoms, lab
              results, imaging findings, medical history — and watch our
              AI agents debate in real time.
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {[
                "🔬 Triage Engine",
                "🛡️ Advocates",
                "⚡ Skeptic",
                "🔍 Inquisitor",
                "🧠 Cortex",
                "📋 Scribe",
              ].map((agent) => (
                <span
                  key={agent}
                  className="rounded-full bg-slate-800/60 border border-slate-700/40 px-3 py-1 text-xs text-slate-400"
                >
                  {agent}
                </span>
              ))}
            </div>
          </div>
        ) : (
          /* Message list */
          <div className="mx-auto max-w-3xl">
            {/* Session start notice */}
            <div className="text-center my-4">
              <span className="rounded-lg bg-slate-800/60 px-4 py-1.5 text-[11px] text-slate-500 border border-slate-700/30">
                🔒 Clinical data is processed locally and not stored
              </span>
            </div>

            <AnimatePresence>
              {messages.map((msg) => (
                <MessageBubble key={msg.id} msg={msg} />
              ))}
            </AnimatePresence>

            {/* Typing indicator */}
            <AnimatePresence>
              {typingNames.length > 0 && (
                <TypingDots agents={typingNames} />
              )}
            </AnimatePresence>

            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* ── Input Bar ───────────────────────────────────────────── */}
      <div className="border-t border-slate-800/60 bg-slate-900/80 px-4 py-3 backdrop-blur-md">
        <div className="mx-auto flex max-w-3xl items-end gap-3">
          {/* Attach button (placeholder for now) */}
          <button
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-slate-400 transition hover:bg-slate-800 hover:text-white"
            title="Attach files (coming soon)"
          >
            <Paperclip className="h-5 w-5" />
          </button>

          {/* Text area */}
          <div className="relative flex-1">
            <textarea
              ref={textareaRef}
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                isConnected
                  ? "Agents are working..."
                  : isComplete
                  ? "Session complete — click New Case to start again"
                  : "Paste patient data... (symptoms, labs, imaging, history)"
              }
              disabled={isConnected || isComplete}
              rows={1}
              className="w-full resize-none rounded-2xl border border-slate-700/50 bg-slate-800/60 px-4 py-2.5 text-sm text-slate-200 placeholder-slate-500 outline-none transition focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>

          {/* Send button */}
          <button
            onClick={handleSend}
            disabled={!inputText.trim() || isConnected || isComplete}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-cyan-600 text-white transition hover:bg-cyan-500 disabled:opacity-40 disabled:cursor-not-allowed disabled:bg-slate-700"
          >
            <Send className="h-5 w-5" />
          </button>
        </div>

        <div className="mx-auto max-w-3xl mt-2 text-center text-[10px] text-slate-600">
          Press Enter to send • Shift+Enter for new line
        </div>
      </div>
    </div>
  );
}
