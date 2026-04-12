"use client";

import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Brain,
  Heart,
  Wind,
  Pill,
  ShieldAlert,
  Search,
  AlertTriangle,
  MessageSquare,
} from "lucide-react";
import { useCortexStore } from "@/store/useCortexStore";
import type { DebateMessage } from "@/types/types";

// ─── Agent Config ───────────────────────────────────────────────────

interface AgentDisplay {
  id: string;
  name: string;
  role: string;
  icon: typeof Brain;
  color: string;
  accentHex: string;
  textClass: string;
  bgClass: string;
}

const AGENTS: AgentDisplay[] = [
  {
    id: "cortex",
    name: "CORTEX",
    role: "Consensus Engine",
    icon: Brain,
    color: "slate",
    accentHex: "#94a3b8",
    textClass: "text-slate-300",
    bgClass: "bg-slate-400/10",
  },
  {
    id: "cardiac_advocate",
    name: "Cardiac",
    role: "Advocate",
    icon: Heart,
    color: "cyan",
    accentHex: "#06b6d4",
    textClass: "text-cyan-400",
    bgClass: "bg-cyan-400/10",
  },
  {
    id: "pulmonary_advocate",
    name: "Pulmonary",
    role: "Advocate",
    icon: Wind,
    color: "blue",
    accentHex: "#60a5fa",
    textClass: "text-blue-400",
    bgClass: "bg-blue-400/10",
  },
  {
    id: "gi_advocate",
    name: "GI",
    role: "Advocate",
    icon: Pill,
    color: "violet",
    accentHex: "#a78bfa",
    textClass: "text-violet-400",
    bgClass: "bg-violet-400/10",
  },
  {
    id: "skeptic",
    name: "Skeptic",
    role: "Skeptic",
    icon: ShieldAlert,
    color: "red",
    accentHex: "#ef4444",
    textClass: "text-red-400",
    bgClass: "bg-red-400/10",
  },
  {
    id: "inquisitor",
    name: "Inquisitor",
    role: "Inquisitor",
    icon: Search,
    color: "amber",
    accentHex: "#f59e0b",
    textClass: "text-amber-400",
    bgClass: "bg-amber-400/10",
  },
];

const FALLBACK_AGENT: AgentDisplay = {
  id: "system",
  name: "System",
  role: "System",
  icon: Brain,
  color: "slate",
  accentHex: "#94a3b8",
  textClass: "text-slate-400",
  bgClass: "bg-slate-400/10",
};

function getAgent(id: string, name?: string, role?: string): AgentDisplay {
  const existing = AGENTS.find((a) => a.id === id);
  if (existing) return existing;

  // Dynamically generate agent info for dynamic advocates
  let icon = Brain;
  let color = "slate";
  let hex = "#94a3b8";

  if (id.includes("advocate")) {
    icon = Heart; // Generic advocate icon
    color = "cyan";
    hex = "#06b6d4";
  } else if (id.includes("skeptic")) {
    icon = ShieldAlert;
    color = "red";
    hex = "#ef4444";
  }

  return {
    id,
    name: name || id,
    role: role || (id.includes("advocate") ? "Advocate" : "Agent"),
    icon,
    color,
    accentHex: hex,
    textClass: `text-${color}-400`,
    bgClass: `bg-${color}-400/10`,
  };
}

// ─── Left Sidebar: Agent List ───────────────────────────────────────

function AgentSidebar() {
  const activeAgent = useCortexStore((s) => s.activeAgent);
  const messages = useCortexStore((s) => s.debateMessages);

  // Dynamically compile active agents from the chat feed
  const seenIds = new Set<string>();
  const dynamicAgents: ReturnType<typeof getAgent>[] = [];

  // Always keep Cortex and Triage explicitly at the top
  dynamicAgents.push(getAgent("cortex"));
  dynamicAgents.push(getAgent("triage"));
  seenIds.add("cortex");
  seenIds.add("triage");

  for (const m of messages) {
    const mId = m.agent_id || "system";
    if (mId === "system" || seenIds.has(mId)) continue;
    seenIds.add(mId);
    dynamicAgents.push(getAgent(mId, (m as any).agent_name, (m as any).agent_role));
  }

  return (
    <div className="flex w-64 shrink-0 flex-col border-r border-slate-800/60 bg-slate-950/50 p-4">
      <h3 className="mb-4 text-xs font-semibold uppercase tracking-wider text-slate-500">
        Active Agents
      </h3>
      <div className="space-y-2 overflow-y-auto custom-scrollbar pr-1 pb-4">
        {dynamicAgents.map((agent) => {
          const isActive = activeAgent === agent.id;
          const Icon = agent.icon;
          return (
            <motion.div
              layout
              key={agent.id}
              animate={isActive ? { scale: [1, 1.02, 1] } : {}}
              transition={isActive ? { repeat: Infinity, duration: 2 } : {}}
              className={`relative flex items-center gap-3 rounded-xl px-3 py-3 transition-all ${
                isActive
                  ? `${agent.bgClass} border border-${agent.color}-500/30`
                  : "border border-transparent hover:bg-slate-800/30"
              }`}
            >
              {/* Glow ring when active */}
              {isActive && (
                <div
                  className="absolute -inset-0.5 rounded-xl opacity-40 blur-sm"
                  style={{ background: agent.accentHex }}
                />
              )}

              <div className={`relative rounded-lg p-2 ${agent.bgClass}`}>
                <Icon className={`h-4 w-4 ${agent.textClass}`} />
              </div>
              <div className="relative">
                <div className={`text-sm font-semibold ${isActive ? agent.textClass : "text-slate-400"}`}>
                  {agent.name}
                </div>
                <div className="text-xs text-slate-600">{agent.role}</div>
              </div>

              {/* Active dot */}
              {isActive && (
                <div className="relative ml-auto">
                  <div className={`h-2 w-2 rounded-full`} style={{ background: agent.accentHex }} />
                  <div className={`absolute inset-0 h-2 w-2 animate-ping rounded-full`} style={{ background: agent.accentHex }} />
                </div>
              )}
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Center: Debate Feed ────────────────────────────────────────────

function DebateFeed() {
  const messages = useCortexStore((s) => s.debateMessages);
  const feedRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTo({
        top: feedRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [messages.length]);

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Feed Header */}
      <div className="flex items-center gap-3 border-b border-slate-800/60 px-6 py-4">
        <MessageSquare className="h-4 w-4 text-slate-500" />
        <span className="text-sm font-medium text-slate-400">
          Debate Transcript
        </span>
        <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-500">
          {messages.length} messages
        </span>
      </div>

      {/* Messages */}
      <div
        ref={feedRef}
        className="flex-1 overflow-y-auto px-6 py-4 custom-scrollbar"
      >
        <AnimatePresence mode="popLayout">
          {messages.length === 0 && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex h-full flex-col items-center justify-center text-slate-600"
            >
              <Brain className="h-12 w-12 mb-4 text-slate-700" />
              <p>Waiting for agents to speak...</p>
            </motion.div>
          )}

          {messages.map((msg, i) => (
            <MessageBubble key={i} message={msg} index={i} />
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}

function MessageBubble({
  message,
  index,
}: {
  message: DebateMessage;
  index: number;
}) {
  const agent = getAgent(message.agent_id, (message as any).agent_name, (message as any).agent_role);
  const Icon = agent.icon;
  const time = new Date(message.timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <motion.div
      initial={{ opacity: 0, y: 15, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.3 }}
      className="mb-4"
    >
      <div className="flex items-start gap-3">
        {/* Avatar */}
        <div className={`mt-1 shrink-0 rounded-xl p-2 ${agent.bgClass}`}>
          {(message as any).agent_emoji ? (
             <span className="text-lg">{(message as any).agent_emoji}</span>
          ) : (
             <Icon className={`h-4 w-4 ${agent.textClass}`} />
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-sm font-semibold ${agent.textClass}`}>
              {(message as any).agent_name || agent.name}
            </span>
            <span className="rounded-full bg-slate-800/80 px-2 py-0.5 text-[10px] uppercase text-slate-500">
              {(message as any).agent_role || agent.role}
            </span>
            <span className="text-xs text-slate-600 font-mono">{time}</span>
          </div>

          <div
            className={`rounded-xl rounded-tl-sm border px-4 py-3 text-sm leading-relaxed ${
              (message as any).agent_role === "skeptic"
                ? "border-amber-500/30 bg-amber-500/5 text-slate-200"
                : (message as any).agent_role === "inquisitor"
                ? "border-violet-500/30 bg-violet-500/5 text-slate-200"
                : (message as any).agent_role === "advocate"
                ? "border-cyan-500/20 bg-cyan-500/5 text-slate-200"
                : "border-slate-700/50 bg-slate-800/40 text-slate-300"
            }`}
          >
            {/* Split content by newlines for better formatting */}
            {message.content.split("\n").map((line, i) => {
              // render simple bolding
              const parts = line.split(/(\*\*[^*]+\*\*)/g);
              return (
                <p key={i} className={i > 0 ? "mt-2" : ""}>
                   {parts.map((part, j) => {
                     if (part.startsWith("**") && part.endsWith("**")) {
                        return <span key={j} className="font-semibold text-white">{part.slice(2, -2)}</span>;
                     }
                     return <span key={j}>{part}</span>;
                   })}
                </p>
              )
            })}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

// ─── Right Sidebar: Scores + Uncertainty ────────────────────────────

function ScoreSidebar() {
  const scores = useCortexStore((s) => s.scores);
  const scoreEntries = Object.entries(scores).sort((a, b) => b[1] - a[1]);

  const DYNAMIC_BAR_COLORS = [
    { bar: "bg-cyan-500", text: "text-cyan-400" },
    { bar: "bg-emerald-500", text: "text-emerald-400" },
    { bar: "bg-blue-500", text: "text-blue-400" },
    { bar: "bg-violet-500", text: "text-violet-400" },
    { bar: "bg-fuchsia-500", text: "text-fuchsia-400" },
    { bar: "bg-amber-500", text: "text-amber-400" },
    { bar: "bg-rose-500", text: "text-rose-400" },
  ];

  return (
    <div className="flex w-72 shrink-0 flex-col border-l border-slate-800/60 bg-slate-950/50 p-4">
      {/* Live Scores */}
      <h3 className="mb-4 text-xs font-semibold uppercase tracking-wider text-slate-500">
        Round-wise Peer Ratings
      </h3>

      <div className="space-y-4">
        {scoreEntries.map(([key, value], idx) => {
          const colors = DYNAMIC_BAR_COLORS[idx % DYNAMIC_BAR_COLORS.length];
          const label = key.charAt(0).toUpperCase() + key.slice(1);
          return (
            <div key={key}>
              <div className="mb-1.5 flex items-center justify-between">
                <span className={`text-sm font-medium ${colors.text}`}>
                  {label}
                </span>
                <motion.span
                  key={value}
                  initial={{ scale: 1.3, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  className={`text-sm font-bold ${colors.text}`}
                >
                  {value}%
                </motion.span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
                <motion.div
                  className={`h-full rounded-full ${colors.bar}`}
                  animate={{ width: `${value}%` }}
                  transition={{ duration: 0.8, ease: "easeOut" }}
                />
              </div>
            </div>
          );
        })}

        {scoreEntries.length === 0 && (
          <p className="text-xs text-slate-600 italic">
            Scores will appear as agents debate...
          </p>
        )}
      </div>
    </div>
  );
}

// ─── Live Courtroom (3-pane layout) ─────────────────────────────────

export default function LiveCourtroom() {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="flex"
      style={{ height: "calc(100vh - 4rem)" }}
    >
      <AgentSidebar />
      <DebateFeed />
      <ScoreSidebar />
    </motion.div>
  );
}
