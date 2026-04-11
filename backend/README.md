# Omni_CortexX — Medical Diagnostic Multi-Agent Debate System

A production-grade FastAPI backend that uses **LangGraph** to orchestrate a society of AI agents for medical diagnostic reasoning through structured debate.

## Architecture

```
Patient Data / OCR Upload
       │
       ▼
  ┌─────────┐
  │ TRIAGE  │  ← Multi-model swarm (6 models × N passes)
  │ ENGINE  │    Fan-out via Featherless AI + Semaphore(4)
  └────┬────┘
       │  Hypotheses seeded
       ▼
  ┌─────────────────────────────────────────┐
  │         DEBATE LOOP (max N rounds)      │
  │                                         │
  │  ┌───────────┐   ┌─────────┐           │
  │  │ ADVOCATES │──▶│ SKEPTIC │           │
  │  │ (dynamic) │   │         │           │
  │  └───────────┘   └────┬────┘           │
  │                        │                │
  │                  ┌─────▼──────┐         │
  │                  │ INQUISITOR │─ halt?  │
  │                  └─────┬──────┘         │
  │                        │                │
  │                  ┌─────▼──────┐         │
  │                  │   CORTEX   │─ loop?  │
  │                  │ CONSENSUS  │         │
  │                  └────────────┘         │
  └─────────────────────────────────────────┘
       │
       ▼
  ┌─────────┐
  │ SCRIBE  │  → Final structured clinical report
  └─────────┘
```

## Key Design Decisions

- **Featherless AI** for ALL agent reasoning (semaphore-bounded to 4 concurrent)
- **Gemini 2.5 Pro REST** for OCR / PDF / image parsing ONLY (no LangChain)
- **Dynamic Advocate Factory** — one reusable class replicated per hypothesis
- **Qwen3-32B is FORBIDDEN** for advocate agents (enforced in code)
- **LangGraph conditional routing** for consensus / halt / continue decisions

## Quick Start

```bash
# 1. Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
copy .env.example .env
# Edit .env with your API keys

# 4. Run the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 5. Run tests
pytest -v
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Liveness probe |
| `GET` | `/api/v1/ready` | Readiness probe |
| `POST` | `/api/v1/upload` | Upload PDF/image for OCR |
| `POST` | `/api/v1/diagnose` | Run full diagnostic workflow |
| `WS` | `/ws/diagnose` | WebSocket streaming |

## WebSocket Protocol

1. Connect to `ws://localhost:8000/ws/diagnose`
2. Send JSON: `{"patient_data": {...}, "max_rounds": 5}`
3. Receive streamed events:
   - `triage_complete` — initial hypotheses
   - `advocate_argument` — each advocate's defense
   - `skeptic_objection` — penalties and contradictions
   - `inquisitor_halt` / `inquisitor_clear` — halt decision
   - `consensus_event` — consensus reached or continue
   - `final_report` — complete diagnosis
   - `complete` — workflow finished

## Project Structure

```
backend/
├── requirements.txt
├── .env.example
├── pytest.ini
├── app/
│   ├── main.py                  # FastAPI app factory
│   ├── api/
│   │   ├── routes_diagnosis.py  # REST endpoints
│   │   └── websocket.py         # WebSocket streaming
│   ├── core/
│   │   ├── config.py            # pydantic-settings
│   │   ├── logging.py           # structlog + request IDs
│   │   ├── llm_client.py        # Featherless + Gemini callers
│   │   └── exceptions.py        # Exception hierarchy
│   ├── graph/
│   │   ├── state.py             # Pydantic state + TypedDict bridge
│   │   ├── prompts.py           # All agent prompts (separated)
│   │   ├── tools.py             # Async research tools
│   │   ├── agents.py            # Triage, Advocate, Skeptic, etc.
│   │   └── workflow.py          # LangGraph StateGraph wiring
│   ├── schemas/
│   │   ├── requests.py          # API request models
│   │   └── responses.py         # API response models
│   └── services/
│       ├── ocr_service.py       # Gemini OCR wrapper
│       └── report_service.py    # Response formatting
└── tests/
    ├── test_llm_client.py
    ├── test_tools.py
    └── test_workflow.py
```

## Triage Model Roster

| Model | Role |
|-------|------|
| `moonshotai/Kimi-K2.5` | Triage |
| `google/gemma-4-31B-it` | Triage |
| `Qwen/Qwen2.5-72B-Instruct` | Triage + Default Agent |
| `meta-llama/Llama-3.1-70B-Instruct` | Triage |
| `Qwen/Qwen3-32B` | Triage ONLY (forbidden for advocates) |
| `deepseek-ai/DeepSeek-R1-Distill-Llama-70B` | Triage |

## License

Private — Hackathon Project
