"use client";

import { useCallback, useRef } from "react";
import { useCortexStore } from "@/store/useCortexStore";
import type { Hypothesis, DebateMessage, MissingDataItem, DiagnosisResult } from "@/types/types";

// ─── Mock Data ──────────────────────────────────────────────────────

const MOCK_OCR_JSON = `{
  "patient_summary": {
    "age": 58,
    "sex": "male",
    "chief_complaint": "Acute chest pain radiating to left arm",
    "vital_signs": {
      "bp": "165/95",
      "hr": 112,
      "spo2": 93,
      "temp_c": 37.1,
      "rr": 22
    }
  },
  "ecg_findings": {
    "st_elevation": ["II", "III", "aVF"],
    "st_depression": ["I", "aVL"],
    "rhythm": "sinus_tachycardia",
    "rate": 112
  },
  "lab_values": {
    "troponin_ng_ml": 2.45,
    "bnp_pg_ml": 890,
    "creatinine_mg_dl": 1.1,
    "d_dimer_ug_ml": 0.42
  },
  "confidence": 0.92
}`;

const MOCK_HYPOTHESES: Hypothesis[] = [
  {
    diagnosis: "Acute Myocardial Infarction (STEMI)",
    confidence: 0.82,
    supporting_evidence: [
      "ST elevation in inferior leads (II, III, aVF)",
      "Elevated troponin at 2.45 ng/mL (10x upper limit)",
      "Chest pain radiating to left arm with diaphoresis",
      "Sinus tachycardia at 112 bpm",
      "BNP elevated at 890 pg/mL suggesting cardiac stress",
    ],
    source_model: "Qwen/Qwen2.5-72B-Instruct",
    source_pass: 1,
  },
  {
    diagnosis: "Pulmonary Embolism",
    confidence: 0.12,
    supporting_evidence: [
      "Tachycardia and tachypnea present",
      "SpO2 decreased at 93%",
      "D-dimer mildly elevated at 0.42 μg/mL",
    ],
    source_model: "meta-llama/Llama-3.1-70B-Instruct",
    source_pass: 1,
  },
  {
    diagnosis: "Acute Gastroesophageal Reflux",
    confidence: 0.06,
    supporting_evidence: [
      "Chest pain can mimic cardiac presentation",
      "No prior cardiac history documented",
    ],
    source_model: "google/gemma-4-31B-it",
    source_pass: 2,
  },
];

const MOCK_DEBATE_MESSAGES: DebateMessage[] = [
  {
    agent_role: "Consensus Engine",
    agent_id: "cortex",
    content:
      "Initiating diagnostic debate. Three hypotheses have been seeded from triage. Advocates, present your evidence. Round 1 begins now.",
    round_number: 1,
    timestamp: new Date().toISOString(),
  },
  {
    agent_role: "Advocate",
    agent_id: "cardiac_advocate",
    content:
      "The ECG findings are highly specific for inferior STEMI. ST elevation in leads II, III, and aVF with reciprocal changes in I and aVL is a classic pattern for right coronary artery occlusion. Combined with troponin at 2.45 ng/mL — over 10 times the upper limit of normal — this represents a definitive acute myocardial infarction. Time-to-balloon is critical; every minute of delay reduces myocardial salvage.",
    round_number: 1,
    timestamp: new Date().toISOString(),
    evidence_refs: ["Harrison's Principles of Internal Medicine, Ch. 269", "ACC/AHA STEMI Guidelines 2023"],
  },
  {
    agent_role: "Advocate",
    agent_id: "pulmonary_advocate",
    content:
      "While I acknowledge the ECG findings favor a cardiac etiology, the tachypnea (RR 22) and hypoxemia (SpO2 93%) warrant consideration of pulmonary embolism. The D-dimer, although only mildly elevated at 0.42, does not fully rule out PE in a high-risk patient. A CT pulmonary angiography should be considered.",
    round_number: 1,
    timestamp: new Date().toISOString(),
  },
  {
    agent_role: "Advocate",
    agent_id: "gi_advocate",
    content:
      "Gastroesophageal reflux can present with substernal chest pain that mimics cardiac events. However, I concede that the objective findings — troponin elevation, ECG changes, and hemodynamic instability — make a primary GI etiology extremely unlikely in this case. I defer to the cardiac hypothesis.",
    round_number: 1,
    timestamp: new Date().toISOString(),
  },
  {
    agent_role: "Skeptic",
    agent_id: "skeptic",
    content:
      "⚠️ OBJECTION to Pulmonary Advocate: D-dimer at 0.42 μg/mL is below the age-adjusted threshold (0.58 for a 58-year-old). Per the PERC rule, this patient does not meet criteria for PE workup. The ECG pattern is NOT consistent with right heart strain — no S1Q3T3, no right axis deviation. I'm applying a -15% confidence penalty to the PE hypothesis.\n\n✓ Cardiac Advocate evidence verified: Troponin and ECG findings are internally consistent and well-cited.",
    round_number: 1,
    timestamp: new Date().toISOString(),
  },
  {
    agent_role: "Inquisitor",
    agent_id: "inquisitor",
    content:
      "Critical data gap assessment: No baseline ECG available for comparison. While current findings strongly suggest new-onset STEMI, a prior ECG would help exclude chronic ST changes (e.g., Brugada pattern, LVH). Additionally, no echocardiogram data is available to assess wall motion abnormalities. RECOMMENDATION: Proceed with current data — urgency of intervention outweighs data completeness concerns.",
    round_number: 1,
    timestamp: new Date().toISOString(),
  },
  {
    agent_role: "Consensus Engine",
    agent_id: "cortex",
    content:
      "Round 1 scores updated. Cardiac hypothesis dominant at 85%. The GI Advocate has conceded. The Skeptic's penalty reduces PE to 5%. Checking consensus threshold... Confidence exceeds 85% threshold. Initiating final consensus.",
    round_number: 1,
    timestamp: new Date().toISOString(),
  },
];

const MOCK_SCORES_PROGRESSION = [
  { cardiac: 78, pulmonary: 15, gi: 7 },
  { cardiac: 82, pulmonary: 12, gi: 6 },
  { cardiac: 85, pulmonary: 10, gi: 5 },
  { cardiac: 85, pulmonary: 8, gi: 5 },   // after skeptic
  { cardiac: 88, pulmonary: 5, gi: 2 },
  { cardiac: 91, pulmonary: 5, gi: 2 },
  { cardiac: 92, pulmonary: 5, gi: 3 },
];

const MOCK_MISSING_DATA: MissingDataItem[] = [
  {
    test_name: "Baseline ECG",
    reason: "No prior ECG for comparison to rule out chronic ST changes",
    urgency: "low",
    impact_on_diagnosis: "Would confirm new-onset vs. chronic ST elevation",
  },
  {
    test_name: "Echocardiogram",
    reason: "Wall motion abnormalities would confirm ischemic territory",
    urgency: "medium",
    impact_on_diagnosis: "Localizes infarct and assesses LV function",
  },
];

const MOCK_VERDICT: DiagnosisResult = {
  primary_diagnosis: "Acute ST-Elevation Myocardial Infarction (Inferior STEMI)",
  confidence_pct: 92,
  differential_list: [
    { diagnosis: "Acute Myocardial Infarction (STEMI)", confidence: 0.92 },
    { diagnosis: "Pulmonary Embolism", confidence: 0.05 },
    { diagnosis: "Acute Gastroesophageal Reflux", confidence: 0.03 },
  ],
  supporting_evidence: [
    "ST elevation in leads II, III, aVF with reciprocal depression in I, aVL",
    "Troponin I elevated at 2.45 ng/mL (reference <0.04 ng/mL)",
    "Acute onset chest pain with radiation to left arm and diaphoresis",
    "Sinus tachycardia suggestive of sympathetic activation",
    "BNP 890 pg/mL indicating myocardial stress",
    "Hemodynamic profile consistent with cardiogenic shock risk",
  ],
  contradictory_evidence: [
    "Mildly elevated D-dimer could suggest alternative pathology (ruled out by Skeptic)",
    "No baseline ECG available for definitive comparison",
  ],
  missing_investigations: [
    "Baseline/prior ECG for comparison",
    "Transthoracic echocardiogram",
    "Serial troponin measurements (6h, 12h)",
  ],
  recommended_next_tests: [
    "Emergent cardiac catheterization with PCI",
    "Continuous telemetry monitoring",
    "Bedside echocardiogram",
    "Repeat troponin at 6 and 12 hours",
    "Check PT/INR and aPTT pre-procedure",
  ],
  emergency_escalation: true,
  scribe_summary:
    "58-year-old male presenting with acute inferior STEMI confirmed by classic ECG pattern (ST elevation II, III, aVF) and markedly elevated troponin (2.45 ng/mL). Multi-agent diagnostic debate achieved 92% consensus after 1 round. Immediate cardiac catheterization with PCI recommended. Emergency escalation activated.",
};

// ─── Demo Mode Hook ─────────────────────────────────────────────────

export function useDemoMode() {
  const timersRef = useRef<NodeJS.Timeout[]>([]);

  const {
    setPhase,
    setSessionId,
    setHypotheses,
    addMessage,
    updateScores,
    setActiveAgent,
    setCurrentRound,
    setMissingData,
    setVerdict,
    setOcrResult,
  } = useCortexStore();

  const clearTimers = useCallback(() => {
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
  }, []);

  const startDemo = useCallback(() => {
    clearTimers();

    // Generate demo session ID
    const demoSessionId = `demo_${Date.now().toString(36)}`;
    setSessionId(demoSessionId);

    // Phase 1 → VISION_LAYER (instant)
    setPhase("VISION_LAYER");

    // After vision layer animation (3s) → TRIAGE
    const t1 = setTimeout(() => {
      setOcrResult(JSON.parse(MOCK_OCR_JSON));
      setHypotheses(MOCK_HYPOTHESES);
      setPhase("TRIAGE");
    }, 4000);
    timersRef.current.push(t1);
  }, [clearTimers, setPhase, setSessionId, setHypotheses, setOcrResult]);

  const startCourtroom = useCallback(() => {
    clearTimers();
    setPhase("COURTROOM");
    setCurrentRound(1);

    // Stream debate messages at intervals
    MOCK_DEBATE_MESSAGES.forEach((msg, i) => {
      const delay = (i + 1) * 2000; // 2s between each message

      const t = setTimeout(() => {
        setActiveAgent(msg.agent_id);
        addMessage({
          ...msg,
          timestamp: new Date().toISOString(),
        });

        // Update scores along the way
        if (i < MOCK_SCORES_PROGRESSION.length) {
          updateScores(MOCK_SCORES_PROGRESSION[i]);
        }

        // Set missing data after inquisitor speaks
        if (msg.agent_id === "inquisitor") {
          setMissingData(MOCK_MISSING_DATA);
        }

        // After last message → verdict
        if (i === MOCK_DEBATE_MESSAGES.length - 1) {
          const tVerdict = setTimeout(() => {
            setActiveAgent(null);
            updateScores({ cardiac: 92, pulmonary: 5, gi: 3 });
            setVerdict(MOCK_VERDICT);
            setPhase("VERDICT");
          }, 2500);
          timersRef.current.push(tVerdict);
        }
      }, delay);

      timersRef.current.push(t);
    });
  }, [
    clearTimers,
    setPhase,
    setCurrentRound,
    addMessage,
    setActiveAgent,
    updateScores,
    setMissingData,
    setVerdict,
  ]);

  return { startDemo, startCourtroom, clearTimers, mockOcrJson: MOCK_OCR_JSON };
}
