"use client";

import { AnimatePresence } from "framer-motion";
import { useCortexStore } from "@/store/useCortexStore";
import Header from "@/components/Layout/Header";
import Dashboard from "@/components/Ingestion/Dashboard";
import VisionLayer from "@/components/Ingestion/VisionLayer";
import Triage from "@/components/Courtroom/Triage";
import LiveCourtroom from "@/components/Courtroom/LiveCourtroom";
import ConsensusDoc from "@/components/Verdict/ConsensusDoc";

export default function AppShell() {
  const phase = useCortexStore((s) => s.phase);

  return (
    <div className="flex min-h-screen flex-col bg-slate-950">
      <Header />
      <main className="flex-1 overflow-hidden">
        <AnimatePresence mode="wait">
          {phase === "INGESTION" && <Dashboard key="ingestion" />}
          {phase === "VISION_LAYER" && <VisionLayer key="vision" />}
          {phase === "TRIAGE" && <Triage key="triage" />}
          {phase === "COURTROOM" && <LiveCourtroom key="courtroom" />}
          {phase === "VERDICT" && <ConsensusDoc key="verdict" />}
        </AnimatePresence>
      </main>
    </div>
  );
}
