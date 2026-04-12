"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  RotateCcw,
  BarChart3,
  Stethoscope,
  Shield,
  FileWarning,
  ChevronRight,
  Siren,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { useCortexStore } from "@/store/useCortexStore";

// ─── Tab Component ──────────────────────────────────────────────────

function TabButton({
  active,
  icon: Icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: typeof CheckCircle2;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium transition-all ${
        active
          ? "bg-slate-800 text-white shadow-lg"
          : "text-slate-400 hover:bg-slate-800/40 hover:text-slate-300"
      }`}
    >
      <Icon className="h-4 w-4" />
      {label}
    </button>
  );
}

// ─── Score Chart ────────────────────────────────────────────────────

const BAR_COLORS = ["#06b6d4", "#60a5fa", "#a78bfa", "#94a3b8"];

function ScoreChart({ data }: { data: { name: string; score: number }[] }) {
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ left: 20, right: 20 }}>
          <XAxis type="number" domain={[0, 100]} tick={{ fill: "#64748b", fontSize: 12 }} axisLine={false} tickLine={false} />
          <YAxis type="category" dataKey="name" tick={{ fill: "#94a3b8", fontSize: 13, fontWeight: 500 }} axisLine={false} tickLine={false} width={180} />
          <Tooltip
            contentStyle={{
              backgroundColor: "#1e293b",
              border: "1px solid #334155",
              borderRadius: "12px",
              color: "#e2e8f0",
              fontSize: "13px",
            }}
            formatter={(value) => [`${value}%`, "Confidence"]}
          />
          <Bar dataKey="score" radius={[0, 6, 6, 0]} barSize={24}>
            {data.map((_, i) => (
              <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Consensus Document ─────────────────────────────────────────────

export default function ConsensusDoc() {
  const [activeTab, setActiveTab] = useState<"supporting" | "dissenting">(
    "supporting"
  );
  const verdict = useCortexStore((s) => s.verdict);
  const reset = useCortexStore((s) => s.reset);

  if (!verdict) {
    return (
      <div className="flex h-full items-center justify-center text-slate-500">
        No verdict available.
      </div>
    );
  }

  const chartData =
    verdict.differential_list?.map((d) => ({
      name: d.diagnosis,
      score: Math.round((d.confidence || 0) * 100),
    })) || [];

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0 }}
      className="mx-auto max-w-4xl p-6"
    >
      {/* Success Header */}
      <motion.div
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ type: "spring", stiffness: 200, delay: 0.1 }}
        className="mb-8 text-center"
      >
        <div className="relative mx-auto mb-6 inline-flex">
          <div className="rounded-full bg-emerald-500/10 p-5">
            <CheckCircle2 className="h-16 w-16 text-emerald-400" />
          </div>
          <div className="absolute -inset-2 animate-pulse rounded-full bg-emerald-400/10 blur-xl" />
        </div>

        <motion.h1
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-400"
        >
          Consensus Reached
        </motion.h1>

        <motion.h2
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="mt-3 text-3xl font-bold text-slate-100"
        >
          {verdict.primary_diagnosis}
        </motion.h2>

        {/* Confidence */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.5 }}
          className="mt-4 inline-flex items-center gap-2 rounded-full bg-emerald-500/10 px-6 py-2 text-lg font-bold text-emerald-400"
        >
          {verdict.confidence_pct}% Confidence
        </motion.div>

        {/* Emergency flag */}
        {verdict.emergency_escalation && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.6 }}
            className="mt-4 inline-flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm font-semibold text-red-400"
          >
            <Siren className="h-4 w-4" />
            EMERGENCY ESCALATION RECOMMENDED
          </motion.div>
        )}
      </motion.div>

      {/* Scribe Summary */}
      {verdict.scribe_summary && (
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6 }}
          className="mb-6 rounded-2xl border border-slate-700/50 bg-slate-900/60 p-6"
        >
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-400">
            <Stethoscope className="h-4 w-4" />
            Clinical Summary
          </div>
          <p className="text-sm leading-relaxed text-slate-300">
            {verdict.scribe_summary}
          </p>
        </motion.div>
      )}

      {/* Tabs */}
      <motion.div
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.7 }}
      >
        <div className="mb-4 flex gap-2 rounded-xl bg-slate-900/40 p-1">
          <TabButton
            active={activeTab === "supporting"}
            icon={CheckCircle2}
            label="Supporting Evidence"
            onClick={() => setActiveTab("supporting")}
          />
          <TabButton
            active={activeTab === "dissenting"}
            icon={XCircle}
            label="Dissenting Opinions"
            onClick={() => setActiveTab("dissenting")}
          />
        </div>

        {/* Tab Content */}
        <div className="rounded-2xl border border-slate-700/50 bg-slate-900/60 p-6">
          {activeTab === "supporting" ? (
            <div className="space-y-3">
              {verdict.supporting_evidence.map((ev, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.05 }}
                  className="flex items-start gap-3"
                >
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
                  <span className="text-sm text-slate-300 leading-relaxed">
                    {ev}
                  </span>
                </motion.div>
              ))}
            </div>
          ) : (
            <div className="space-y-3">
              {verdict.contradictory_evidence.length === 0 ? (
                <p className="text-sm text-slate-500 italic">
                  No significant dissenting opinions recorded.
                </p>
              ) : (
                verdict.contradictory_evidence.map((ev, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.05 }}
                    className="flex items-start gap-3"
                  >
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
                    <span className="text-sm text-slate-300 leading-relaxed">
                      {ev}
                    </span>
                  </motion.div>
                ))
              )}
            </div>
          )}
        </div>
      </motion.div>

      {/* Final Scores Chart */}
      {chartData.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.8 }}
          className="mt-6 rounded-2xl border border-slate-700/50 bg-slate-900/60 p-6"
        >
          <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-400">
            <BarChart3 className="h-4 w-4" />
            Differential Diagnosis Scores
          </div>
          <ScoreChart data={chartData} />
        </motion.div>
      )}

      {/* Recommended Next Tests */}
      {verdict.recommended_next_tests.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.9 }}
          className="mt-6 rounded-2xl border border-slate-700/50 bg-slate-900/60 p-6"
        >
          <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-400">
            <FileWarning className="h-4 w-4" />
            Recommended Next Steps
          </div>
          <div className="space-y-2">
            {verdict.recommended_next_tests.map((test, i) => (
              <div key={i} className="flex items-center gap-2 text-sm text-slate-300">
                <ChevronRight className="h-3.5 w-3.5 text-cyan-400" />
                {test}
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* New Case Button */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.0 }}
        className="mt-8 flex justify-center"
      >
        <motion.button
          onClick={reset}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          className="flex items-center gap-2 rounded-xl border border-slate-700/50 bg-slate-800/60 px-8 py-3.5 text-sm font-semibold text-slate-300 transition-all hover:border-cyan-500/30 hover:bg-slate-800 hover:text-white"
        >
          <RotateCcw className="h-4 w-4" />
          New Case
        </motion.button>
      </motion.div>
    </motion.div>
  );
}
