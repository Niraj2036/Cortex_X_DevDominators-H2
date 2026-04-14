# Omni_CortexX

**A Society of Arguing AI Agents That Diagnose Patients By Simulating Alternate Realities**

[![Watch the Demo Video](https://img.shields.io/badge/📺_Watch_Demo_Video-blue?style=for-the-badge)](https://drive.google.com/file/d/1iDTL0hivs9I0j5S7D19Ehs94nYqFWMPJ/view?usp=sharing)

---

## 1. Executive Summary

Most clinical AI systems behave like single-shot answer engines: one model, one prediction, low transparency. That is risky in real diagnostic settings where missing data, uncertain findings, and conflicting evidence are common.

**Omni_CortexX** is built as a multi-agent diagnostic courtroom, not a one-pass chatbot. A doctor can upload mixed clinical evidence (images, PDFs, and text history). We first convert all raw data into structured medical context using Gemini 2.5 Flash, then run a debate-based diagnosis protocol where multiple open-source LLMs independently reason, challenge each other, and iteratively refine hypotheses.

The system is designed for:

*   **High recall of possibilities:** Multiple models generate broad differential hypotheses.
*   **Concurrent execution:** Ingestion and model calls are parallelized to reduce turnaround time.
*   **Traceable reasoning:** Every debate round, score, penalty, and remark is logged.
*   **Epistemic humility:** If critical data is missing or consensus quality is weak, the system halts and asks for more reports instead of forcing a diagnosis.

---

## 2. Unique Selling Propositions (USPs)

*   **True Multimodal Intake from Clinicians:** Supports mixed uploads including ECG images, scanned PDFs, and rich patient text (history, symptoms, prior conditions, medications, etc.).
*   **Gemini-First Clinical Structuring Layer:** Gemini 2.5 Flash is used twice in the ingestion pipeline: first to infer findings per file, then to normalize all findings into one consistent structured payload.
*   **Open-Source Multi-Model Reasoning via Featherless:** Diagnosis generation runs on a fleet of open-source models instead of a single proprietary endpoint.
*   **Concurrency-Aware LLM Scheduler:** Requests are queued and dispatched based on model size limits and key-level throughput constraints.
*   **Courtroom-Style Iterative Deliberation:** Advocates, Skeptic, Inquisitor, Simulator, Scribe, and Cortex-X collaborate across multiple rounds with explicit scoring and elimination logic.
*   **Fail-Safe by Design:** Missing critical data can pause the workflow and request additional reports before proceeding.

---

## 3. Detailed Architecture & User Flow

### Phase 1: Multimodal Clinical Intake (Doctor Input Layer)
**Trigger:** A clinician uploads any combination of:

*   Medical images (for example ECG traces)
*   PDFs/reports/lab documents
*   Text fields (patient details, complaint timeline, history, etc.)

**Design Goal:** Doctors should provide evidence in native clinical form, not manually structured JSON.

### Phase 2: Gemini 2.5 Flash Inference + Structuring Layer
This stage runs before the debate engine.

**Step A: File-Level Inference**

*   Each uploaded file is processed with Gemini 2.5 Flash.
*   The model extracts a concise medical inference per artifact.

**Step B: Unified Clinical Structuring**

*   All file-level inferences + patient text are merged.
*   Gemini 2.5 Flash is called again to produce one normalized structured representation.

**Output (Global Input Payload):**
```json
{
  "patient_text_summary": "Patient arrived in ED with chest pain radiating to the left arm...",
  "reports": [
    {
      "name": "Initial ECG",
      "type": "image",
      "extracted_inference": "Non-specific ST-T wave changes, no acute ischemia."
    },
    {
      "name": "Troponin Lab",
      "type": "pdf",
      "extracted_inference": "Troponin slightly elevated at 0.05 ng/mL."
    }
  ]
}
```

### Phase 3: Featherless Multi-Model Hypothesis Generation
Gemini's role ends after structuring. Then Featherless inference begins.

**Model Fleet (Open Source):**

*   `deepseek-ai/DeepSeek-V3-0324`
*   `google/gemma-4-31B-it`
*   `Qwen/Qwen2.5-72B-Instruct`
*   `deepseek-ai/DeepSeek-V3.2`
*   `Qwen/Qwen3-32B`
*   `google/gemma-4-26B-A4B`

**Generation Strategy:**

*   The same structured payload is sent to each model **twice**.
*   Responses are deduplicated to collect **unique diagnostic hypotheses**.

### Phase 4: Concurrency and Throughput Control
Because Featherless throughput depends on model size, the backend uses a queue-based dispatcher.

**Constraint Policy:**

*   Models **below 32B**: up to 2 concurrent requests per key.
*   Models **32B and above**: 1 concurrent request per key.

**Execution Pattern:**

*   4 Featherless API keys are used.
*   Independent workers push LLM tasks into a central queue.
*   The scheduler checks model-size class and key availability.
*   Requests are dispatched in eligible batches to maximize concurrency without violating limits.

### Phase 5: Courtroom Orchestration (LangGraph Deliberation)
After unique hypotheses are created, CORTEX-X (orchestrator) assigns one ADVOCATE per hypothesis.

**Round Structure (2-3 rounds typical, max 5):**

*   Each advocate builds the strongest case concurrently.
*   Tool access includes Google Search API, Wikipedia, and Tavily.
*   Institutional memory retrieval is planned but not active in the current implementation.

### Phase 6: Skeptic, Inquisitor, and Peer Review Logic
**SKEPTIC:**

*   Challenges weak or unsupported claims.
*   Assigns uncertainty penalties and gives remarks.

**INQUISITOR:**

*   Detects missing data requirements raised during challenge.
*   Checks whether missing evidence is critical.
*   If critical and unavailable, halts debate and asks clinician for more reports.

**Peer Advocate Evaluation:**

*   Advocates evaluate other advocates' cases.
*   Each case receives peer scores + remarks.
*   Peer score is averaged to estimate case robustness.

### Phase 7: Elimination, Refinement, and Consensus Search
CORTEX-X compares each case against peer consensus.

*   Cases with significantly weaker support are discarded for the next round.
*   Surviving advocates receive prior remarks and context to improve arguments.
*   Loop continues until one of the following:
    *   Convergence before 5 rounds
    *   Maximum round cap reached
    *   Debate halted due to critical missing data

### Phase 8: Simulation Gate + Final Decision
Before final recommendation, the SIMULATOR runs forward-looking checks on the leading diagnosis/treatment trajectory.

*   If projected outcome risk is acceptable, consensus can be approved.
*   If concerns remain, the orchestrator can continue deliberation or decline confident diagnosis.

### Phase 9: Continuous Documentation and Storage
SCRIBE records the full case timeline in real time:

*   hypotheses,
*   arguments,
*   penalties,
*   peer remarks,
*   round-by-round score evolution,
*   final decision state.

Artifacts are persisted to MongoDB Atlas Vector Database for auditability and future retrieval workflows.

---

## 4. Technical Stack

**Frontend (The Command Center):**
*   **React.js / Next.js** (App Router)
*   **Tailwind CSS** (for a clinical, clean UI)
*   **WebSockets** for real-time debate streaming.

**Backend (The Agent Engine):**
*   **Python / FastAPI** for async APIs, ingestion, and orchestration endpoints
*   **LangGraph** for cyclical multi-agent state transitions
*   **Queue-based LLM dispatcher** for concurrency-safe Featherless scheduling

**AI Pipeline:**
*   **Ingestion + Structuring:** Gemini 2.5 Flash (Gemini API)
*   **Diagnostic Generation:** Featherless AI with 6 open-source LLMs (listed above)
*   **Debate Roles:** Advocate, Skeptic, Inquisitor, Simulator, Scribe, Cortex-X

**Database & Memory:**
*   **MongoDB Atlas** for session/case persistence
*   **MongoDB Atlas Vector Database** for transcript and reasoning artifact storage
*   **Institutional memory retrieval:** planned, not currently enabled

**Research Tools Available to Advocates:**
*   **Google Search API**
*   **Wikipedia**
*   **Tavily API**

---

## 5. Complete Project Directory Structure

```text
Cortex_X_DevDominators-H2/      # Root Monorepo Directory
│
├── backend/                    # FASTAPI & LANGGRAPH ENGINE
│   ├── .env                    # Environment variables (APIs, Configs)
│   ├── pytest.ini              # Pytest configuration
│   ├── requirements.txt        # Python dependencies
│   ├── app/
│   │   ├── main.py             # FastAPI entry point & WebSocket connection handler
│   │   ├── api/
│   │   │   ├── atlas_routes.py     # MongoDB Vector endpoints
│   │   │   ├── routes_diagnosis.py # REST endpoints for workflow ingestion
│   │   │   └── websocket.py        # WebSocket streaming logic for LangGraph updates
│   │   ├── core/               # INFRASTRUCTURE & SETTINGS
│   │   │   ├── config.py       # Pydantic Settings
│   │   │   ├── exceptions.py   # Global Custom Error Handling 
│   │   │   ├── llm_client.py   # Wrapping logic for async LLMs 
│   │   │   └── logging.py      # Structlog initialiser
│   │   ├── db/
│   │   │   └── mongodb.py      # Async Motor client initialization pool
│   │   ├── graph/              # LANGGRAPH ARCHITECTURE
│   │   │   ├── agents.py       # Combined agent nodes logic (Triage, Advocates, Skeptic, Scribe)
│   │   │   ├── prompts.py      # Prompt constants for deterministic rendering
│   │   │   ├── state.py        # Defines the TypedDict for the shared deliberation graph
│   │   │   ├── tools.py        # Binds executable actions for agents
│   │   │   └── workflow.py     # StateGraph compiler (connects nodes & conditional edges)
│   │   ├── schemas/            # PYDANTIC SCHEMAS
│   │   │   ├── requests.py     # Payload definitions
│   │   │   └── responses.py    # Output payload formatting
│   │   └── services/           # EXTERNAL API MANAGERS
│   │       ├── atlas_service.py      # MongoDB connection & Vector Search logic
│   │       ├── ocr_service.py        # Image/PDf parsing via Gemini
│   │       ├── report_service.py     # Logic to format verdicts
│   │       └── structuring_service.py# NLP string sanitization
│   └── tests/                  # PYTEST SUITE
│       ├── conftest.py
│       ├── test_llm_client.py
│       ├── test_tools.py
│       └── test_workflow.py
│
├── frontend/                   # NEXT.JS & REACT UI
│   ├── AGENTS.md               # Frontend Agent Doc mappings
│   ├── package.json            # Node dependencies
│   ├── tailwind.config.ts      # UI styling bounds
│   └── src/
│       ├── app/
│       │   ├── globals.css     # Tailwind imports
│       │   ├── layout.tsx      # Global React layout & fonts
│       │   └── page.tsx        # Main routing dashboard
│       ├── components/         # UI BUILDING BLOCKS
│       │   ├── AppShell.tsx    # Native Next Layout Wrapper
│       │   ├── Chat/
│       │   │   └── ChatView.tsx         # Unified stream component
│       │   ├── Courtroom/
│       │   │   ├── LiveCourtroom.tsx    # Agent sidebar and hook multiplex loop
│       │   │   └── Triage.tsx           # Initial Hypotheses Generation component
│       │   ├── Ingestion/
│       │   │   ├── Dashboard.tsx        # UI for patient context & file dropzones
│       │   │   └── VisionLayer.tsx      # OCR File processing state
│       │   ├── Layout/
│       │   │   └── Header.tsx           # Application navigation
│       │   └── Verdict/
│       │       └── ConsensusDoc.tsx     # Final structured diagnostic report card
│       ├── hooks/              # CUSTOM REACT HOOKS
│       │   ├── useBackend.ts            # WebSockets connection and event handler
│       │   ├── useDemoMode.ts           # Development simulation overrides
│       │   └── useWebSocketChat.ts      # Raw string parsing stream
│       ├── store/
│       │   └── useCortexStore.ts        # Zustand global memory persistence
│       └── types/
│           └── types.ts                 # Full interface definitions
│
└── README.md                   # Project Documentation
```
