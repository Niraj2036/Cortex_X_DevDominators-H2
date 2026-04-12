"use client";

import { useCortexStore } from "@/store/useCortexStore";
import { Brain, Activity, ToggleLeft, ToggleRight } from "lucide-react";
import { motion } from "framer-motion";

const PHASE_LABELS: Record<string, { label: string; color: string }> = {
  INGESTION: { label: "DATA INTAKE", color: "bg-slate-600" },
  VISION_LAYER: { label: "OCR PROCESSING", color: "bg-amber-600" },
  TRIAGE: { label: "TRIAGE", color: "bg-cyan-600" },
  COURTROOM: { label: "LIVE DEBATE", color: "bg-red-600" },
  VERDICT: { label: "VERDICT", color: "bg-emerald-600" },
};

export default function Header() {
  const phase = useCortexStore((s) => s.phase);
  const demoMode = useCortexStore((s) => s.demoMode);
  const toggleDemoMode = useCortexStore((s) => s.toggleDemoMode);
  const sessionId = useCortexStore((s) => s.sessionId);

  const phaseInfo = PHASE_LABELS[phase] || PHASE_LABELS.INGESTION;

  return (
    <header className="sticky top-0 z-50 border-b border-slate-800/80 bg-slate-950/90 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-[1920px] items-center justify-between px-6">
        {/* Logo */}
        <div className="flex items-center gap-3">
          <div className="relative">
            <Brain className="h-8 w-8 text-cyan-400" />
            <div className="absolute -inset-1 animate-pulse rounded-full bg-cyan-400/20 blur-md" />
          </div>
          <div className="flex items-baseline gap-0.5">
            <span className="text-lg font-bold tracking-tight text-slate-200">
              OMNI_CORTEX
            </span>
            <span className="text-lg font-black text-cyan-400">X</span>
          </div>
          <span className="ml-2 hidden text-xs text-slate-500 sm:inline">
            Medical Diagnostic AI
          </span>
        </div>

        {/* Center: Phase Badge + Pulse */}
        <div className="flex items-center gap-3">
          <Activity className="h-4 w-4 text-slate-500" />
          <motion.div
            key={phase}
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className={`rounded-full px-4 py-1 text-xs font-semibold uppercase tracking-wider text-white ${phaseInfo.color}`}
          >
            {phaseInfo.label}
          </motion.div>
          {sessionId && (
            <span className="hidden text-xs font-mono text-slate-600 lg:inline">
              SID: {sessionId}
            </span>
          )}
        </div>

        {/* Right: Demo Toggle */}
        <button
          onClick={toggleDemoMode}
          className="flex items-center gap-2 rounded-lg border border-slate-700/50 px-3 py-1.5 text-xs transition-all hover:border-slate-600 hover:bg-slate-800/50"
        >
          {demoMode ? (
            <ToggleRight className="h-5 w-5 text-cyan-400" />
          ) : (
            <ToggleLeft className="h-5 w-5 text-slate-500" />
          )}
          <span className={demoMode ? "text-cyan-400" : "text-slate-500"}>
            Demo Mode
          </span>
        </button>
      </div>
    </header>
  );
}
