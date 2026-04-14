# Omni_CortexX

**A Society of Arguing AI Agents That Diagnose Patients By Simulating Alternate Realities**

[![Watch the Demo Video](https://img.shields.io/badge/📺_Watch_Demo_Video-blue?style=for-the-badge)](https://drive.google.com/file/d/1iDTL0hivs9I0j5S7D19Ehs94nYqFWMPJ/view?usp=sharing)

---

## 1. Executive Summary

Currently, clinical AI tools fail because they are overconfident single-model systems. They produce a single answer, cannot explain their reasoning, and lack the ability to say "I don't know." This contributes to the 12 million diagnostic errors occurring annually.

**Omni_CortexX** solves this by treating medical diagnosis as a courtroom rather than a calculator. We deploy a society of specialized AI agents (powered by a diverse fleet of LLMs) that actively debate competing hypotheses, simulate counterfactual outcomes, cross-examine each other, and search the medical internet for real-world case precedents. The system enforces **epistemic humility**: it will explicitly refuse to diagnose and instead demand missing information if the agents cannot reach a mathematical consensus.

---

## 2. Unique Selling Propositions (USPs)

*   **Multimodal Vision Ingestion:** Doctors don't type JSON. Omni_CortexX allows clinicians to drag-and-drop raw ECG images, PDFs of blood work, and typed clinical notes. We use the Gemini Vision API to instantly standardize this chaotic data into a clean, queryable JSON format.
*   **Poly-Model Triage Engine:** Instead of relying on one model, we hit GPT-4, Claude 3.5 Sonnet, and Gemini simultaneously to generate the initial hypotheses, catching edge cases a single model would miss.
*   **The Agentic Courtroom:** Agents don't just output text; they actively cross-examine each other's logic and use tool-calling (Tavily API) to cite real-time medical literature.
*   **Epistemic Humility (The "I Don't Know" Feature):** The system is deliberately designed to block premature consensus. If uncertainty is too high, it issues an "Uncertainty Declaration" to the human doctor.

---

## 3. Detailed Architecture & User Flow

### Phase 1: Multimodal Data Ingestion (The Vision Layer)
**Trigger:** A clinician uploads a mix of data (ECG images, Blood Work PDFs, and text notes) to the React dashboard.
**Action:** Instead of passing heavy, expensive images to the debating agents, the backend intercepts the files. The system uses the Gemini 1.5 Pro/Flash Vision API to read every single report, extract the medical inferences, and structure them into a standardized JSON array.

**Output Data Structure (The Global Input):**
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

### Phase 2: Poly-Model Triage & Setup
**Action:** The standardized JSON is sent concurrently to multiple LLMs (OpenAI, Anthropic, Google).
**Result:** The system extracts unique diagnostic hypotheses (e.g., Cardiac, Pulmonary, GI).
**Setup:** CORTEX (The Chief Justice) initializes a LangGraph state machine. It dynamically assigns an ADVOCATE agent to each identified hypothesis.

### Phase 3: The Live Courtroom (Stateful Deliberation)
**Action:** The React UI transitions to a real-time WebSockets feed. The debate begins:
*   **Research:** Advocates pause to query the internet (Tavily API) and the institutional memory database (MongoDB Vector Search) for real-world case precedents matching the ingested reports.
*   **Debate:** Advocates present their arguments to the Shared Deliberation Graph. They actively read the transcript and disagree with other advocates if evidence contradicts them.
*   **Cross-Examination:** The SKEPTIC (Devil's Advocate) attacks the advocates, finds logical flaws, and assigns mathematical "Uncertainty Penalties" to weak arguments.
*   **Simulation:** The SIMULATOR runs in the background, projecting "What if?" scenarios (e.g., "If we administer Heparin now, what is the bleeding risk?").

### Phase 4: The Information Gap Check
**Action:** The INQUISITOR agent monitors the debate. If the SKEPTIC successfully blocks an argument because data is missing (e.g., prior imaging is absent), the INQUISITOR calculates the diagnostic value of that missing data.
**Result:** It halts the debate and triggers a UI prompt to the clinician: *"Critical Data Missing: Please upload prior chest X-ray to rule out dissection."*

### Phase 5: Verdict & Documentation
**Action:** CORTEX continuously runs a weighted voting algorithm (Advocate Confidence - Skeptic Uncertainty = Adjusted Score).
*   **Scenario A (Supermajority Reached):** If a hypothesis crosses the threshold (e.g., >85%), the SCRIBE generates a Consensus Certificate. It logs the winning diagnosis, the confidence band, and explicitly lists the dissenting agents' opinions for the clinician to review.
*   **Scenario B (Deadlock):** If the score remains too low, CORTEX issues an Uncertainty Declaration, explaining exactly why the AI society cannot safely diagnose the patient, handing control back to the human.

### Phase 6: Post-Case Learning
**Action:** After the clinician finalizes the case, the entire transcript, inputs, and actual patient outcome are stored in the database.
**Result:** MNEMOS (Institutional Memory) updates the MongoDB Atlas Vector embeddings. In future cases, Advocates will retrieve this case to improve their reasoning, making the system measurably smarter over time.

---

## 4. Technical Stack

**Frontend (The Command Center):**
*   **React.js / Next.js** (App Router)
*   **Tailwind CSS** (for a clinical, clean UI)
*   **WebSockets** (Socket.io) for real-time debate streaming.
*   **Recharts** for dynamic data visualization.

**Backend (The Agent Engine):**
*   **Python / FastAPI** (Chosen for native async support, critical for long-running LLM calls).
*   **LangGraph** (Crucial for managing the cyclic, stateful multi-agent debate).
*   **LangChain** (Wraps LLM APIs and equips agents with tools).

**AI & LLM Fleet:**
*   **Vision Ingestion:** Gemini 1.5 Pro / Flash (Best-in-class for medical image/PDF OCR).
*   **The Advocates/Skeptic:** GPT-4o and Claude 3.5 Sonnet (High reasoning capabilities).
*   **Orchestration (CORTEX/Scribe):** Llama-3 (via Groq) or Gemini Flash for fast, cheap state routing.

**Database & Memory:**
*   **MongoDB Atlas** (Stores patient sessions and JSON reports using motor async Python driver).
*   **MongoDB Atlas Vector Search** (Powers MNEMOS to retrieve past cases for RAG).

**External Tooling:**
*   **Tavily Search API** (Grants Advocates internet access for live medical research).

---

## 5. Complete Project Directory Structure

```text
omni-cortex-x/                  # Root Monorepo Directory
│
├── backend/                    # FASTAPI & LANGGRAPH ENGINE
│   ├── .env                    # API Keys (OpenAI, Google, Anthropic, Tavily, Mongo)
│   ├── requirements.txt        # Python dependencies
│   └── app/
│       ├── main.py             # FastAPI entry point & WebSocket connection handler
│       ├── api/
│       │   ├── routes.py       # REST endpoints (e.g., POST /upload for Vision OCR)
│       │   └── websockets.py   # WebSocket streaming logic for LangGraph updates
│       │
│       ├── graph/              # LANGGRAPH ARCHITECTURE
│       │   ├── state.py        # Defines the TypedDict for the shared deliberation graph
│       │   └── workflow.py     # StateGraph compiler (connects nodes & conditional edges)
│       │
│       ├── agents/             # LANGGRAPH NODES (The AI Society)
│       │   ├── __init__.py
│       │   ├── triage.py       # Multi-model inference to extract hypotheses
│       │   ├── cortex.py       # Evaluator logic (Checks math for >85% consensus)
│       │   ├── advocates.py    # Logic & prompts for Cardiac, GI, Pulmonary agents
│       │   ├── skeptic.py      # Devil's Advocate logic & uncertainty penalty math
│       │   ├── simulator.py    # Counterfactual generator
│       │   └── inquisitor.py   # Identifies missing information
│       │
│       ├── services/           # EXTERNAL API MANAGERS
│       │   ├── vision_extractor.py # Gemini API logic to parse Images/PDFs to JSON
│       │   ├── search_tool.py  # Tavily API integration for web research
│       │   └── database.py     # MongoDB connection & Vector Search logic (MNEMOS)
│       │
│       └── models/             # Pydantic schemas (Ensures JSON data is strictly typed)
│           └── schemas.py      # PatientInput, ActiveHypothesis, FinalVerdict schemas
│
├── frontend/                   # NEXT.JS & REACT UI
│   ├── .env.local              # Frontend config (Backend URL, etc.)
│   ├── package.json
│   ├── tailwind.config.ts
│   └── src/
│       ├── app/
│       │   ├── layout.tsx      # Global layout & fonts
│       │   ├── page.tsx        # Main Dashboard Page
│       │   └── globals.css     # Tailwind imports
│       │
│       ├── components/         # UI BUILDING BLOCKS
│       │   ├── Ingestion/
│       │   │   └── FileUploader.tsx    # Drag-and-drop for images, PDFs, text
│       │   ├── Courtroom/
│       │   │   ├── LiveFeed.tsx        # Terminal-style scrolling text of agent debate
│       │   │   └── AgentBadge.tsx      # Visual indicators of who is speaking
│       │   ├── Analytics/
│       │   │   └── BeliefChart.tsx     # Recharts component for confidence scores
│       │   └── Verdict/
│       │       ├── ConsensusDoc.tsx    # Green UI: Shows final diagnosis & dissenters
│       │       └── UncertaintyWarning.tsx # Yellow UI: Prompts for missing data
│       │
│       ├── hooks/
│       │   └── useDebateSocket.ts      # Custom React Hook to manage WebSocket state
│       │
│       └── lib/
│           └── utils.ts        # Helper functions (date formatting, class merging)
│
└── README.md                   # Hackathon Pitch & Setup Instructions
```

---

## 6. Recommended Workflow Execution

1.  **Backend Initialization:** Start by setting up the `backend/app/models/schemas.py` and `backend/app/services/vision_extractor.py`. Prove that you can upload a dummy PDF/Image and get your structured JSON back using Gemini.
2.  **State Machine:** Build the `state.py` and `workflow.py`. Start with dummy agents (simple Python functions that just return hardcoded strings) to ensure LangGraph routes properly from Advocate -> Skeptic -> Cortex.
3.  **Frontend Sockets:** Build the Next.js UI and establish the WebSocket connection. Stream the dummy text to the `LiveFeed.tsx` component.
4.  **Inject Real AI:** Once the pipes are connected, replace the dummy agent functions with actual LangChain LLM calls.
