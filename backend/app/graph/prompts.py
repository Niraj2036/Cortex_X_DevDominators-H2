"""
app.graph.prompts
~~~~~~~~~~~~~~~~~~
ALL agent system / user prompts live here — separated from logic.

Each prompt is a plain function returning a string so it can be
parameterised with runtime context (patient data, hypotheses, etc.).

TOKEN BUDGET
────────────
All prompts enforce a character budget to stay within
32K-token model context windows (~4 chars ≈ 1 token).
Large data (transcripts, patient records) is compacted:
  • No indent in JSON dumps
  • Truncated to fit budget
  • Only most-recent entries kept
"""

from __future__ import annotations

import json
from typing import Any

# ── Max characters for variable-length sections ──────────────────────
# ~4 chars per token, leave room for system prompt + completion
_MAX_PATIENT_CHARS = 25000     # ~6250 tokens
_MAX_TRANSCRIPT_CHARS = 15000  # ~3750 tokens
_MAX_HYPOTHESES_CHARS = 5000   # ~1250 tokens
_MAX_SECTION_CHARS = 1500      # ~375 tokens


def _compact(obj: Any, max_chars: int = 4000) -> str:
    """JSON-serialize compactly and truncate to max_chars."""
    raw = json.dumps(obj, separators=(",", ":"), default=str)
    if len(raw) <= max_chars:
        return raw
    return raw[:max_chars - 20] + '..."truncated"}'


def _compact_transcript(
    transcript: list[dict[str, Any]],
    max_entries: int = 6,
    max_chars: int = _MAX_TRANSCRIPT_CHARS,
) -> str:
    """Keep only the N most recent transcript entries, compacted."""
    recent = transcript[-max_entries:] if len(transcript) > max_entries else transcript
    # Strip bulky 'content' fields to just first 300 chars each
    trimmed = []
    for e in recent:
        entry = dict(e)
        content = entry.get("content", "")
        if len(content) > 300:
            entry["content"] = content[:300] + "..."
        # Drop tool_calls to save space
        entry.pop("tool_calls", None)
        trimmed.append(entry)
    return _compact(trimmed, max_chars)


# =====================================================================
# TRIAGE ENGINE
# =====================================================================


def triage_system_prompt() -> str:
    return (
        "You are a senior medical diagnostician performing initial triage.\n"
        "Given patient data (demographics, symptoms, lab values, imaging, history),\n"
        "generate a ranked list of diagnostic hypotheses.\n\n"
        "RULES:\n"
        "1. Return ONLY valid JSON — no markdown fences, no commentary.\n"
        "2. Each hypothesis must include:\n"
        '   - "diagnosis": string\n'
        '   - "confidence": float 0.0–1.0\n'
        '   - "supporting_evidence": list[str]\n'
        "3. List 3–8 hypotheses, ranked by confidence.\n"
        "4. Consider rare but dangerous differentials.\n"
        "5. Flag any missing data that would change your ranking.\n"
        "6. CRITICAL: ENSURE ALL HYPOTHESES ARE DISTINCT AND UNIQUE. Do not output synonymous or overlapping diagnoses (e.g. 'Acute MI' and 'STEMI'). Consolidate them.\n"
    )


def triage_user_prompt(patient_data: dict[str, Any]) -> str:
    return (
        "PATIENT DATA:\n"
        f"{_compact(patient_data, _MAX_PATIENT_CHARS)}\n\n"
        "Generate your diagnostic hypotheses as a JSON object with key "
        '"hypotheses" containing an array of hypothesis objects.'
    )


# =====================================================================
# ADVOCATE
# =====================================================================


def advocate_system_prompt(diagnosis: str) -> str:
    return (
        f"You are a specialist medical advocate defending: {diagnosis}\n\n"
        "Your mission:\n"
        "1. DEFEND this diagnosis with evidence-based reasoning.\n"
        "2. CITE specific literature, guidelines, and clinical criteria.\n"
        "3. ATTACK competing hypotheses by identifying their weaknesses.\n"
        "4. Every claim MUST have an evidence base.\n"
        "5. Request tool calls if needed: "
        '{"tool":"<name>","query":"<search>"}\n'
        "   Tools: literature_search, clinical_guidelines, pubmed_search, tavily_search\n"
        "6. Provide a confidence score 0.0–1.0.\n\n"
        "Return ONLY valid JSON:\n"
        '{"defense":"...","evidence":["..."],'
        '"attacks_on_competitors":[{"target":"...","weakness":"..."}],'
        '"confidence":0.0-1.0,'
        '"tool_requests":[{"tool":"...","query":"..."}]}\n'
    )


def advocate_user_prompt(
    diagnosis: str,
    patient_data: dict[str, Any],
    transcript: list[dict[str, Any]],
    competing: list[str],
    *,
    peer_remarks: list[dict[str, Any]] | None = None,
) -> str:
    prompt = (
        f"Defending: {diagnosis}\n"
        f"Patient: {_compact(patient_data, _MAX_PATIENT_CHARS)}\n"
        f"Competitors: {', '.join(competing)}\n"
        f"Recent debate: {_compact_transcript(transcript, max_entries=4)}\n"
    )

    if peer_remarks:
        prompt += f"Peer feedback (address weaknesses): {_compact(peer_remarks, _MAX_SECTION_CHARS)}\n"

    prompt += "Present defense, attack competitors, give confidence."
    return prompt


# =====================================================================
# SKEPTIC
# =====================================================================


def skeptic_system_prompt() -> str:
    return (
        "You are a rigorous medical skeptic (Devil's Advocate).\n\n"
        "Mission:\n"
        "1. IDENTIFY contradictions in the SPECIFIC advocate's argument you are critiquing.\n"
        "2. DETECT hallucinated or unsupported claims for this hypothesis.\n"
        "3. VERIFY SOURCE CREDIBILITY — rate 0.0–1.0.\n"
        "4. PENALISE weak evidence (uncertainty penalty 0.0–0.5) against this diagnosis.\n"
        "5. DETECT missing clinical tests required to validate this hypothesis.\n"
        "6. Request tool calls to verify: literature_search, clinical_guidelines, pubmed_search\n\n"
        "Return ONLY valid JSON:\n"
        '{"contradictions":[{"issue":"..."}],'
        '"hallucination_flags":[{"claim":"...","reason":"..."}],'
        '"source_credibility":[{"source_title":"...","credibility_score":0.5,"issues":[],"verified":false}],'
        '"uncertainty_penalty":0.1,'
        '"missing_tests":["test1"],'
        '"overall_assessment":"text",'
        '"tool_requests":[{"tool":"...","query":"..."}]}\n'
    )


def skeptic_user_prompt(
    target_diagnosis: str,
    advocate_argument: dict[str, Any],
    transcript: list[dict[str, Any]],
    patient_data: dict[str, Any],
) -> str:
    return (
        f"You are fiercely critiquing: {target_diagnosis}\n"
        f"Advocate's Defense: {_compact(advocate_argument, _MAX_SECTION_CHARS)}\n"
        f"Patient: {_compact(patient_data, _MAX_PATIENT_CHARS)}\n"
        f"Debate Context: {_compact_transcript(transcript, max_entries=4)}\n"
        "Critique this specific argument aggressively. Verify sources. Assign penalty. Identify gaps."
    )


# =====================================================================
# PEER RATING
# =====================================================================


def peer_rating_system_prompt(rater_diagnosis: str) -> str:
    return (
        f"You defend {rater_diagnosis}. Rate each other advocate's case 0-10.\n"
        "Judge: evidence quality, logical coherence, patient data coverage, "
        "attack strength, reasoning quality.\n"
        "Be FAIR and OBJECTIVE.\n\n"
        "Return ONLY valid JSON:\n"
        '{"ratings":{"advocate_id":{"score":0-10,"remark":"brief remark"}}}\n'
    )


def peer_rating_user_prompt(
    rater_diagnosis: str,
    other_advocates: list[dict[str, Any]],
) -> str:
    # Compact each advocate's argument to save tokens
    summaries = []
    for adv in other_advocates:
        arg = adv.get("argument", {})
        # Keep only defense + evidence + confidence from argument
        if isinstance(arg, dict):
            compact_arg = {
                "defense": str(arg.get("defense", ""))[:200],
                "evidence": arg.get("evidence", [])[:3],
                "confidence": arg.get("confidence"),
            }
        else:
            compact_arg = str(arg)[:300]

        summaries.append({
            "id": adv["agent_id"],
            "diagnosis": adv["diagnosis"],
            "arg": compact_arg,
        })

    return (
        f"You defend: {rater_diagnosis}\n"
        f"Rate these advocates:\n{_compact(summaries, 6000)}\n"
        "Return ratings for each advocate_id."
    )


# =====================================================================
# INQUISITOR
# =====================================================================


def inquisitor_system_prompt() -> str:
    return (
        "You are a clinical inquisitor assessing if missing evidence\n"
        "could materially change the leading diagnosis.\n\n"
        "1. CRITICAL: Before claiming any test/report is missing, YOU MUST CAREFULLY CHECK THE PATIENT DATA. Do NOT ask for tests that are already provided in the patient data!\n"
        "2. If critical data is TRULY missing and absolutely required, recommend halting.\n"
        "3. Classify urgency: critical/high/medium/low.\n"
        "4. Ask targeted follow-up questions for the missing data.\n\n"
        "Return ONLY valid JSON:\n"
        '{"should_halt":false,'
        '"missing_data":[{"test_name":"...","reason":"...","urgency":"medium","impact":"..."}],'
        '"follow_up_questions":["..."],'
        '"assessment":"text"}\n'
    )


def inquisitor_user_prompt(
    hypotheses: list[dict[str, Any]],
    confidence_scores: dict[str, float],
    uncertainty_penalties: dict[str, float],
    missing_tests: list[str],
    patient_data: dict[str, Any],
) -> str:
    adjusted = {
        k: round(confidence_scores.get(k, 0) - uncertainty_penalties.get(k, 0), 3)
        for k in set(list(confidence_scores.keys()) + list(uncertainty_penalties.keys()))
    }
    return (
        f"Hypotheses: {_compact(hypotheses, _MAX_HYPOTHESES_CHARS)}\n"
        f"Confidence: {json.dumps(confidence_scores, separators=(',',':'))}\n"
        f"Penalties: {json.dumps(uncertainty_penalties, separators=(',',':'))}\n"
        f"Adjusted: {json.dumps(adjusted, separators=(',',':'))}\n"
        f"Missing tests: {missing_tests}\n"
        f"Patient: {_compact(patient_data, _MAX_PATIENT_CHARS)}\n"
        "Assess whether halting is warranted."
    )


# =====================================================================
# CORTEX ORCHESTRATOR (consensus)
# =====================================================================


def cortex_system_prompt() -> str:
    return (
        "You are the Cortex Orchestrator — final arbiter of consensus.\n\n"
        "RULES:\n"
        "1. adjusted score > 0.85 → consensus.\n"
        "2. Scores within 0.05 → continue debate.\n"
        "3. Max rounds reached → declare uncertainty.\n\n"
        "Return ONLY valid JSON:\n"
        '{"consensus_reached":false,"leading_diagnosis":"...","adjusted_scores":{},'
        '"justification":"text","recommendation":"continue_debate"}\n'
    )


def cortex_user_prompt(
    confidence_scores: dict[str, float],
    uncertainty_penalties: dict[str, float],
    current_round: int,
    max_rounds: int,
    *,
    advocate_scores: dict[str, float] | None = None,
    eliminated: list[str] | None = None,
) -> str:
    adjusted = {
        k: round(confidence_scores.get(k, 0) - uncertainty_penalties.get(k, 0), 3)
        for k in set(list(confidence_scores.keys()) + list(uncertainty_penalties.keys()))
    }
    prompt = (
        f"Round {current_round}/{max_rounds}\n"
        f"Confidence: {json.dumps(confidence_scores, separators=(',',':'))}\n"
        f"Penalties: {json.dumps(uncertainty_penalties, separators=(',',':'))}\n"
        f"Adjusted: {json.dumps(adjusted, separators=(',',':'))}\n"
    )
    if advocate_scores:
        prompt += f"Peer scores: {json.dumps(advocate_scores, separators=(',',':'))}\n"
    if eliminated:
        prompt += f"Eliminated: {eliminated}\n"
    prompt += "Make consensus determination."
    return prompt


# =====================================================================
# SCRIBE (final report + comprehensive audit trail)
# =====================================================================


def scribe_system_prompt() -> str:
    return (
        "You are a medical scribe producing a structured clinical report.\n\n"
        "Include: primary diagnosis, confidence %, differential list, "
        "supporting/contradictory evidence, missing investigations, "
        "recommended tests, emergency flag, narrative summary.\n\n"
        "Return ONLY valid JSON:\n"
        '{"primary_diagnosis":"...","confidence_pct":0,'
        '"differential_list":[{"diagnosis":"...","confidence_pct":0}],'
        '"supporting_evidence":["..."],"contradictory_evidence":["..."],'
        '"missing_investigations":["..."],"recommended_next_tests":["..."],'
        '"emergency_escalation":false,"summary":"narrative"}\n'
    )


def scribe_user_prompt(
    patient_data: dict[str, Any],
    hypotheses: list[dict[str, Any]],
    transcript: list[dict[str, Any]],
    confidence_scores: dict[str, float],
    uncertainty_penalties: dict[str, float],
    consensus_diagnosis: str | None,
    *,
    ocr_extractions: list[dict[str, Any]] | None = None,
    peer_ratings: list[dict[str, Any]] | None = None,
    advocate_scores: dict[str, float] | None = None,
    eliminated_advocates: list[str] | None = None,
    source_credibility: list[dict[str, Any]] | None = None,
) -> str:
    prompt = f"Patient: {_compact(patient_data, _MAX_PATIENT_CHARS)}\n"

    if ocr_extractions:
        prompt += f"OCR: {_compact(ocr_extractions[:3], _MAX_SECTION_CHARS)}\n"

    prompt += (
        f"Hypotheses: {_compact(hypotheses, _MAX_HYPOTHESES_CHARS)}\n"
        f"Confidence: {json.dumps(confidence_scores, separators=(',',':'))}\n"
        f"Penalties: {json.dumps(uncertainty_penalties, separators=(',',':'))}\n"
        f"Consensus: {consensus_diagnosis or 'None — uncertainty declared'}\n"
    )

    if advocate_scores:
        prompt += f"Peer scores: {json.dumps(advocate_scores, separators=(',',':'))}\n"
    if eliminated_advocates:
        prompt += f"Eliminated: {eliminated_advocates}\n"
    if source_credibility:
        prompt += f"Source credibility: {_compact(source_credibility[:5], _MAX_SECTION_CHARS)}\n"

    # Only include last few transcript entries for scribe
    prompt += f"Debate ({len(transcript)} entries): {_compact_transcript(transcript, max_entries=8, max_chars=5000)}\n"
    prompt += "Generate the final structured clinical report."
    return prompt
