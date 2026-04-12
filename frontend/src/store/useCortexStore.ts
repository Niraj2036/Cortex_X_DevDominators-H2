import { create } from "zustand";
import type {
  Phase,
  Hypothesis,
  DebateMessage,
  MissingDataItem,
  DiagnosisResult,
} from "@/types/types";

// ─── Store State ────────────────────────────────────────────────────

interface CortexState {
  // Phase machine
  phase: Phase;
  setPhase: (phase: Phase) => void;

  // Session
  sessionId: string;
  setSessionId: (id: string) => void;

  // Demo mode
  demoMode: boolean;
  toggleDemoMode: () => void;

  // Ingestion
  patientSummary: string;
  setPatientSummary: (text: string) => void;
  uploadedFiles: File[];
  setUploadedFiles: (files: File[]) => void;
  fileLabels: string;
  setFileLabels: (labels: string) => void;

  // OCR
  ocrResult: Record<string, unknown> | null;
  setOcrResult: (result: Record<string, unknown>) => void;

  // Triage
  hypotheses: Hypothesis[];
  setHypotheses: (h: Hypothesis[]) => void;

  // Courtroom
  debateMessages: DebateMessage[];
  addMessage: (msg: DebateMessage) => void;
  setDebateMessages: (msgs: DebateMessage[]) => void;
  activeAgent: string | null;
  setActiveAgent: (id: string | null) => void;
  currentRound: number;
  setCurrentRound: (r: number) => void;

  // Scores
  scores: Record<string, number>;
  updateScores: (s: Record<string, number>) => void;

  // Missing data / uncertainty
  missingData: MissingDataItem[];
  setMissingData: (items: MissingDataItem[]) => void;

  // Verdict
  verdict: DiagnosisResult | null;
  setVerdict: (v: DiagnosisResult) => void;

  // Error
  error: string | null;
  setError: (e: string | null) => void;

  // Loading
  isLoading: boolean;
  setIsLoading: (l: boolean) => void;

  // Reset
  reset: () => void;
}

// ─── Initial State ──────────────────────────────────────────────────

const initialState = {
  phase: "INGESTION" as Phase,
  sessionId: "",
  demoMode: true, // Default to demo mode so UI works immediately
  patientSummary: "",
  uploadedFiles: [] as File[],
  fileLabels: "",
  ocrResult: null,
  hypotheses: [] as Hypothesis[],
  debateMessages: [] as DebateMessage[],
  activeAgent: null as string | null,
  currentRound: 0,
  scores: {} as Record<string, number>,
  missingData: [] as MissingDataItem[],
  verdict: null as DiagnosisResult | null,
  error: null as string | null,
  isLoading: false,
};

// ─── Store ──────────────────────────────────────────────────────────

export const useCortexStore = create<CortexState>((set) => ({
  ...initialState,

  setPhase: (phase) => set({ phase }),
  setSessionId: (sessionId) => set({ sessionId }),
  toggleDemoMode: () => set((s) => ({ demoMode: !s.demoMode })),

  setPatientSummary: (patientSummary) => set({ patientSummary }),
  setUploadedFiles: (uploadedFiles) => set({ uploadedFiles }),
  setFileLabels: (fileLabels) => set({ fileLabels }),

  setOcrResult: (ocrResult) => set({ ocrResult }),

  setHypotheses: (hypotheses) => set({ hypotheses }),

  addMessage: (msg) =>
    set((s) => ({ debateMessages: [...s.debateMessages, msg] })),
  setDebateMessages: (debateMessages) => set({ debateMessages }),
  setActiveAgent: (activeAgent) => set({ activeAgent }),
  setCurrentRound: (currentRound) => set({ currentRound }),

  updateScores: (scores) => set({ scores }),

  setMissingData: (missingData) => set({ missingData }),

  setVerdict: (verdict) => set({ verdict }),

  setError: (error) => set({ error }),
  setIsLoading: (isLoading) => set({ isLoading }),

  reset: () => set(initialState),
}));
