"use client";

import { motion } from "framer-motion";
import { Heart, Wind, Pill, ArrowRight, TrendingUp, Cpu } from "lucide-react";
import { useCortexStore } from "@/store/useCortexStore";
import { useDemoMode } from "@/hooks/useDemoMode";
import type { Hypothesis } from "@/types/types";

// ─── Icon map for hypothesis types ──────────────────────────────────

const HYPOTHESIS_ICONS: Record<string, { icon: typeof Heart; color: string; bgColor: string; borderColor: string }> = {
  "Acute Myocardial Infarction": {
    icon: Heart,
    color: "text-cyan-400",
    bgColor: "bg-cyan-400/10",
    borderColor: "border-l-cyan-400",
  },
  "Pulmonary Embolism": {
    icon: Wind,
    color: "text-blue-400",
    bgColor: "bg-blue-400/10",
    borderColor: "border-l-blue-400",
  },
  "Gastroesophageal Reflux": {
    icon: Pill,
    color: "text-violet-400",
    bgColor: "bg-violet-400/10",
    borderColor: "border-l-violet-400",
  },
};

function getCardStyle(diagnosis: string) {
  for (const [key, style] of Object.entries(HYPOTHESIS_ICONS)) {
    if (diagnosis.toLowerCase().includes(key.toLowerCase().split(" ")[0].toLowerCase())) {
      return style;
    }
  }
  // default
  return {
    icon: TrendingUp,
    color: "text-slate-400",
    bgColor: "bg-slate-400/10",
    borderColor: "border-l-slate-400",
  };
}

// ─── Hypothesis Card ────────────────────────────────────────────────

function HypothesisCard({
  hypothesis,
  index,
}: {
  hypothesis: Hypothesis;
  index: number;
}) {
  const style = getCardStyle(hypothesis.diagnosis);
  const IconComponent = style.icon;
  const confidencePct = Math.round(hypothesis.confidence * 100);

  return (
    <motion.div
      initial={{ opacity: 0, y: 30 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.15, duration: 0.5 }}
      className={`group relative overflow-hidden rounded-2xl border border-slate-700/50 border-l-4 ${style.borderColor} bg-slate-900/60 transition-all hover:border-slate-600/60 hover:bg-slate-800/40`}
    >
      {/* Header */}
      <div className="flex items-start justify-between p-5 pb-3">
        <div className="flex items-center gap-3">
          <div className={`rounded-xl p-2.5 ${style.bgColor}`}>
            <IconComponent className={`h-6 w-6 ${style.color}`} />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-200 leading-tight">
              {hypothesis.diagnosis.split("(")[0].trim()}
            </h3>
            {hypothesis.diagnosis.includes("(") && (
              <span className="text-xs text-slate-500">
                ({hypothesis.diagnosis.split("(")[1]}
              </span>
            )}
          </div>
        </div>

        {/* Confidence Badge */}
        <div
          className={`flex items-center gap-1 rounded-full px-3 py-1 text-sm font-bold ${
            confidencePct >= 70
              ? "bg-emerald-500/10 text-emerald-400"
              : confidencePct >= 30
              ? "bg-amber-500/10 text-amber-400"
              : "bg-slate-500/10 text-slate-400"
          }`}
        >
          {confidencePct}%
        </div>
      </div>

      {/* Evidence List */}
      <div className="px-5 pb-4">
        <div className="space-y-2">
          {hypothesis.supporting_evidence.map((ev, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.15 + i * 0.05 + 0.3 }}
              className="flex items-start gap-2 text-sm"
            >
              <div className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                confidencePct >= 70 ? "bg-cyan-400" : "bg-slate-500"
              }`} />
              <span className="text-slate-400 leading-relaxed">{ev}</span>
            </motion.div>
          ))}
        </div>
      </div>

      {/* Footer: Source model */}
      <div className="border-t border-slate-800/60 px-5 py-3">
        <div className="flex items-center gap-2 text-xs text-slate-600">
          <Cpu className="h-3 w-3" />
          <span>{hypothesis.source_model}</span>
          <span className="text-slate-700">•</span>
          <span>Pass {hypothesis.source_pass}</span>
        </div>
      </div>

      {/* Hover glow */}
      <div className="pointer-events-none absolute inset-0 rounded-2xl opacity-0 transition-opacity group-hover:opacity-100"
        style={{
          background: `radial-gradient(400px circle at 50% 0%, ${
            style.color.includes("cyan") ? "rgba(6,182,212,0.06)" :
            style.color.includes("blue") ? "rgba(96,165,250,0.06)" :
            "rgba(167,139,250,0.06)"
          }, transparent)`,
        }}
      />
    </motion.div>
  );
}

// ─── Triage View ────────────────────────────────────────────────────

export default function Triage() {
  const hypotheses = useCortexStore((s) => s.hypotheses);
  const demoMode = useCortexStore((s) => s.demoMode);
  const { startCourtroom } = useDemoMode();
  const setPhase = useCortexStore((s) => s.setPhase);

  const handleEnterCourtroom = () => {
    if (demoMode) {
      startCourtroom();
    } else {
      setPhase("COURTROOM");
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="mx-auto max-w-6xl p-6"
    >
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8 text-center"
      >
        <h2 className="text-2xl font-bold text-slate-100">
          Multi-Model Triage Complete
        </h2>
        <p className="mt-2 text-sm text-slate-400">
          {hypotheses.length} hypotheses generated from 6-model swarm analysis.
          Review initial evidence before entering the courtroom.
        </p>
      </motion.div>

      {/* Hypothesis Cards */}
      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {hypotheses.map((h, i) => (
          <HypothesisCard key={h.diagnosis} hypothesis={h} index={i} />
        ))}
      </div>

      {/* Enter Courtroom Button */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.6 }}
        className="mt-10 flex justify-center"
      >
        <motion.button
          onClick={handleEnterCourtroom}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          className="group flex items-center gap-3 rounded-xl bg-gradient-to-r from-red-600 to-red-500 px-8 py-4 text-base font-semibold text-white shadow-lg shadow-red-500/20 transition-shadow hover:shadow-red-500/30"
        >
          Enter Courtroom Debate
          <ArrowRight className="h-5 w-5 transition-transform group-hover:translate-x-1" />
        </motion.button>
      </motion.div>
    </motion.div>
  );
}
