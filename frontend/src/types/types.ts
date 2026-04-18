// ─── Omni_CortexX Frontend Type Definitions ────────────────────────
// Mirrors backend Pydantic models from app/graph/state.py + app/schemas/*

export type Phase =
  | "INGESTION"
  | "VISION_LAYER"
  | "TRIAGE"
  | "COURTROOM"
  | "VERDICT";

export type Urgency = "critical" | "high" | "medium" | "low";

// ── Triage ──────────────────────────────────────────────────────────

export interface Hypothesis {
  diagnosis: string;
  confidence: number; // 0-1
  supporting_evidence: string[];
  source_model: string;
  source_pass: number;
}

// ── Debate ──────────────────────────────────────────────────────────

export interface DebateMessage {
  agent_role: string;
  agent_id: string;
  agent_name?: string;
  agent_emoji?: string;
  content: string;
  round_number: number;
  timestamp: string;
  tool_calls?: Record<string, unknown>[];
  evidence_refs?: string[];
}

// ── Missing Data ────────────────────────────────────────────────────

export interface MissingDataItem {
  test_name: string;
  reason: string;
  urgency: Urgency;
  impact_on_diagnosis: string;
}

// ── Verdict / Diagnosis ─────────────────────────────────────────────

export interface DiagnosisResult {
  primary_diagnosis: string;
  confidence_pct: number; // 0-100
  differential_list: DifferentialItem[];
  supporting_evidence: string[];
  contradictory_evidence: string[];
  missing_investigations: string[];
  recommended_next_tests: string[];
  emergency_escalation: boolean;
  scribe_summary: string;
}

export interface DifferentialItem {
  diagnosis: string;
  confidence: number;
  [key: string]: unknown;
}

// ── WebSocket Events ────────────────────────────────────────────────

export interface WSEvent {
  type: string;
  data?: Record<string, unknown>;
  session_id?: string;
  timestamp?: string;
  // Flattened fields used by various event types
  phase?: string;
  node?: string;
  round?: number;
  error?: string;
  request_id?: string;
  [key: string]: unknown;
}

// ── API Responses ───────────────────────────────────────────────────

export interface OCRExtractionResponse {
  session_id: string;
  document_type: string;
  extractions: Record<string, unknown>[];
  patient_data_merged: Record<string, unknown>;
}

export interface DiagnosisResponse {
  session_id: string;
  request_id: string;
  status: "complete" | "halted" | "error";
  diagnosis: DiagnosisResult | null;
  debate_rounds: number;
  hypotheses_considered: number;
  missing_data: MissingDataItem[];
  halt_reason: string | null;
  errors: string[];
}

// ── Agent Display Config ────────────────────────────────────────────

export interface AgentConfig {
  id: string;
  name: string;
  role: string;
  color: string;        // Tailwind class or hex
  accentHex: string;    // Raw hex for glow effects
  icon: string;         // lucide-react icon name
}

export const AGENT_CONFIGS: AgentConfig[] = [
  {
    id: "cortex",
    name: "CORTEX",
    role: "Consensus Engine",
    color: "text-slate-300",
    accentHex: "#94a3b8",
    icon: "Brain",
  },
  {
    id: "cardiac_advocate",
    name: "Cardiac Advocate",
    role: "Advocate",
    color: "text-cyan-400",
    accentHex: "#06b6d4",
    icon: "Heart",
  },
  {
    id: "pulmonary_advocate",
    name: "Pulmonary Advocate",
    role: "Advocate",
    color: "text-blue-400",
    accentHex: "#60a5fa",
    icon: "Wind",
  },
  {
    id: "gi_advocate",
    name: "GI Advocate",
    role: "Advocate",
    color: "text-violet-400",
    accentHex: "#a78bfa",
    icon: "Pill",
  },
  {
    id: "skeptic",
    name: "Skeptic",
    role: "Skeptic",
    color: "text-red-400",
    accentHex: "#ef4444",
    icon: "ShieldAlert",
  },
  {
    id: "inquisitor",
    name: "Inquisitor",
    role: "Inquisitor",
    color: "text-amber-400",
    accentHex: "#f59e0b",
    icon: "Search",
  },
];
