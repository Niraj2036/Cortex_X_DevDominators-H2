"use client";

import { useEffect, useState, useRef } from "react";
import { motion } from "framer-motion";
import { Terminal, CheckCircle2, Loader2 } from "lucide-react";
import { useCortexStore } from "@/store/useCortexStore";

// ─── Terminal Steps ─────────────────────────────────────────────────

const STEPS = [
  { text: "Initializing Gemini 2.5 Pro OCR pipeline...", duration: 600 },
  { text: "Scanning uploaded documents...", duration: 800 },
  { text: "Extracting ECG waveform data...", duration: 700 },
  { text: "Parsing lab report values...", duration: 600 },
  { text: "Cross-referencing clinical notes...", duration: 500 },
  { text: "Building patient context vector...", duration: 400 },
  { text: "Extraction complete. Initializing triage swarm...", duration: 300 },
];

const MOCK_JSON = `{
  "patient_summary": {
    "age": 58,
    "sex": "male",
    "chief_complaint": "Acute chest pain radiating to left arm"
  },
  "ecg_findings": {
    "st_elevation": ["II", "III", "aVF"],
    "rhythm": "sinus_tachycardia",
    "rate": 112
  },
  "lab_values": {
    "troponin_ng_ml": 2.45,
    "bnp_pg_ml": 890,
    "d_dimer_ug_ml": 0.42
  },
  "confidence": 0.92
}`;

export default function VisionLayer() {
  const [completedSteps, setCompletedSteps] = useState<number[]>([]);
  const [activeStep, setActiveStep] = useState(0);
  const [typedJson, setTypedJson] = useState("");
  const [showJson, setShowJson] = useState(false);
  const phase = useCortexStore((s) => s.phase);
  const jsonCharIndex = useRef(0);

  // Animate steps one by one
  useEffect(() => {
    if (phase !== "VISION_LAYER") return;

    let totalDelay = 0;
    const timers: NodeJS.Timeout[] = [];

    STEPS.forEach((step, i) => {
      // Set active
      const tActive = setTimeout(() => {
        setActiveStep(i);
      }, totalDelay);
      timers.push(tActive);

      totalDelay += step.duration;

      // Set complete
      const tComplete = setTimeout(() => {
        setCompletedSteps((prev) => [...prev, i]);
      }, totalDelay);
      timers.push(tComplete);

      totalDelay += 100;
    });

    // After all steps, show JSON typing
    const tJson = setTimeout(() => {
      setShowJson(true);
    }, totalDelay + 200);
    timers.push(tJson);

    return () => timers.forEach(clearTimeout);
  }, [phase]);

  // JSON typing effect
  useEffect(() => {
    if (!showJson) return;

    jsonCharIndex.current = 0;
    const interval = setInterval(() => {
      jsonCharIndex.current += 2; // type 2 chars at a time for speed
      if (jsonCharIndex.current >= MOCK_JSON.length) {
        setTypedJson(MOCK_JSON);
        clearInterval(interval);
      } else {
        setTypedJson(MOCK_JSON.slice(0, jsonCharIndex.current));
      }
    }, 15);

    return () => clearInterval(interval);
  }, [showJson]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
      className="mx-auto flex max-w-4xl flex-col items-center justify-center p-6"
      style={{ minHeight: "calc(100vh - 4rem)" }}
    >
      {/* Terminal Window */}
      <div className="w-full overflow-hidden rounded-2xl border border-slate-700/50 bg-slate-950/80 shadow-2xl shadow-cyan-500/5">
        {/* Terminal Header */}
        <div className="flex items-center gap-3 border-b border-slate-800 bg-slate-900/80 px-4 py-3">
          <div className="flex gap-2">
            <div className="h-3 w-3 rounded-full bg-red-500/80" />
            <div className="h-3 w-3 rounded-full bg-amber-500/80" />
            <div className="h-3 w-3 rounded-full bg-emerald-500/80" />
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <Terminal className="h-3.5 w-3.5" />
            omni_cortex_vision — gemini-2.5-pro
          </div>
        </div>

        {/* Terminal Body */}
        <div className="p-6 font-mono text-sm leading-relaxed">
          {/* Animated Steps */}
          {STEPS.map((step, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -10 }}
              animate={
                i <= activeStep
                  ? { opacity: 1, x: 0 }
                  : { opacity: 0, x: -10 }
              }
              transition={{ duration: 0.3 }}
              className="mb-2 flex items-center gap-3"
            >
              {completedSteps.includes(i) ? (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
              ) : i === activeStep ? (
                <Loader2 className="h-4 w-4 shrink-0 animate-spin text-cyan-400" />
              ) : (
                <div className="h-4 w-4 shrink-0" />
              )}
              <span
                className={
                  completedSteps.includes(i)
                    ? "text-emerald-400"
                    : i === activeStep
                    ? "text-cyan-400"
                    : "text-slate-600"
                }
              >
                {step.text}
              </span>
            </motion.div>
          ))}

          {/* JSON Output */}
          {showJson && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="mt-6"
            >
              <div className="mb-2 text-xs text-slate-500">
                ── extracted_patient_data.json ──────────────────
              </div>
              <pre className="overflow-x-auto rounded-xl bg-slate-900/60 p-4 text-emerald-400/90">
                {typedJson}
                <span className="animate-pulse text-cyan-400">▊</span>
              </pre>
            </motion.div>
          )}

          {/* Progress Bar */}
          <div className="mt-6">
            <div className="mb-2 flex items-center justify-between text-xs text-slate-500">
              <span>Processing progress</span>
              <span>
                {Math.min(
                  100,
                  Math.round(
                    ((completedSteps.length) / STEPS.length) * 100
                  )
                )}
                %
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
              <motion.div
                className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-emerald-500"
                animate={{
                  width: `${Math.min(
                    100,
                    (completedSteps.length / STEPS.length) * 100
                  )}%`,
                }}
                transition={{ duration: 0.5 }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Subtitle */}
      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5 }}
        className="mt-6 text-center text-sm text-slate-500"
      >
        Gemini 2.5 Pro is extracting structured clinical data from your
        documents...
      </motion.p>
    </motion.div>
  );
}
