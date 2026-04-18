"""
app.graph.agents
~~~~~~~~~~~~~~~~~
All agent node functions for the LangGraph StateGraph.

AGENT SOCIETY
─────────────
A) Triage Engine      — multi-model swarm, hypothesis dedup, confidence bootstrap
B) Advocate Factory   — ONE reusable class, dynamically replicated per hypothesis
C) Skeptic Agent      — contradiction detection, source credibility, penalties
D) Peer Rating Node   — each advocate rates all others → compute elimination scores
E) Inquisitor Agent   — missing evidence detection, halt decision
F) Cortex Orchestrator — consensus math + advocate elimination + routing
G) Scribe Agent       — final structured report + comprehensive audit trail

DEBATE FLOW
───────────
  advocate_round → skeptic → peer_rating → inquisitor → cortex
    ├── consensus → scribe → END
    ├── halted → END
    └── continue (with eliminated advocates removed) → advocate_round

SCORING
───────
  peer_score(advocate_i) = sum(all other advocates' scores for i) / (N - 1)
  Advocates below elimination threshold are removed from next round.
  Minimum 2 advocates are always kept alive.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import ModelPolicyViolation
from app.core.llm_client import (
    featherless_chat_json,
    validate_advocate_model,
)
from app.core.logging import get_logger
from app.graph.prompts import (
    advocate_system_prompt,
    advocate_user_prompt,
    cortex_system_prompt,
    cortex_user_prompt,
    inquisitor_system_prompt,
    inquisitor_user_prompt,
    peer_rating_system_prompt,
    peer_rating_user_prompt,
    scribe_system_prompt,
    scribe_user_prompt,
    skeptic_system_prompt,
    skeptic_user_prompt,
    triage_system_prompt,
    triage_user_prompt,
)
from app.graph.state import (
    DebateEntry,
    DiagnosisResult,
    Hypothesis,
    MissingDataItem,
    OmniState,
    PeerRating,
    SourceCredibility,
    Urgency,
    WorkflowPhase,
)
from app.services.atlas_service import store_case
from app.graph.tools import execute_tool_calls_batch

logger = get_logger(__name__)

# Minimum number of advocates that must survive elimination
MIN_ADVOCATES = 2


# =====================================================================
# A) TRIAGE ENGINE
# =====================================================================


async def triage_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Run the multi-model triage swarm.

    • Fan-out across all triage models (queue-bounded)
    • Each model runs N passes for edge-case coverage
    • Deduplicate & bootstrap-score hypotheses
    • Seed advocate list dynamically
    """
    settings = get_settings()
    s = OmniState.model_validate(state)
    patient_data = s.patient_data

    sys_prompt = triage_system_prompt()
    usr_prompt = triage_user_prompt(patient_data)

    # Build all (model, pass) tasks
    tasks: list[tuple[str, int, asyncio.Task]] = []  # type: ignore[type-arg]
    for model in settings.triage_models:
        for pass_num in range(1, settings.triage_passes_per_model + 1):
            coro = featherless_chat_json(
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": usr_prompt},
                ],
                model=model,
                temperature=0.5 + (pass_num * 0.1),  # vary temperature per pass
                max_tokens=2048,
            )
            tasks.append((model, pass_num, coro))  # type: ignore[arg-type]

    # Execute with fan-out (queue inside llm_client limits concurrency)
    raw_outputs: list[dict[str, Any]] = []
    coros = [t[2] for t in tasks]
    results = await asyncio.gather(*coros, return_exceptions=True)

    events: list[dict[str, Any]] = []

    for (model, pass_num, _), result in zip(tasks, results):
        if isinstance(result, Exception):
            logger.warning(
                "triage_model_failed",
                model=model,
                pass_num=pass_num,
                error=str(result),
            )
            continue

        raw_outputs.append(
            {"model": model, "pass": pass_num, "output": result}
        )

    # Extract hypotheses from all outputs
    all_hypotheses: list[Hypothesis] = []
    for entry in raw_outputs:
        output = entry["output"]
        hyps = []
        if isinstance(output, dict):
            hyps = output.get("hypotheses", [])
            if not hyps and "diagnosis" in output:
                hyps = [output]
        elif isinstance(output, list):
            hyps = output

        for h in hyps:
            if isinstance(h, dict) and "diagnosis" in h:
                all_hypotheses.append(
                    Hypothesis(
                        diagnosis=h["diagnosis"],
                        confidence=float(h.get("confidence", 0.5)),
                        supporting_evidence=h.get("supporting_evidence", []),
                        source_model=entry["model"],
                        source_pass=entry["pass"],
                    )
                )

    # Deduplicate by normalised diagnosis name
    deduped = _deduplicate_hypotheses(all_hypotheses)

    # Bootstrap confidence: average across models that proposed each diagnosis
    confidence_scores: dict[str, float] = {}
    for hyp in deduped:
        confidence_scores[hyp.diagnosis] = round(hyp.confidence, 3)

    events.append({
        "type": "triage_complete",
        "hypotheses": [h.model_dump() for h in deduped],
        "model_count": len(settings.triage_models),
        "timestamp": datetime.utcnow().isoformat(),
    })

    return {
        **state,
        "phase": WorkflowPhase.DEBATE.value,
        "raw_triage_outputs": raw_outputs,
        "active_hypotheses": [h.model_dump() for h in deduped],
        "confidence_scores": confidence_scores,
        "uncertainty_penalties": {h.diagnosis: 0.0 for h in deduped},
        "pending_events": state.get("pending_events", []) + events,
    }


def _deduplicate_hypotheses(hyps: list[Hypothesis]) -> list[Hypothesis]:
    """Merge hypotheses with similar diagnosis names, averaging confidence."""
    groups: dict[str, list[Hypothesis]] = {}
    for h in hyps:
        key = h.diagnosis.strip().lower()
        groups.setdefault(key, []).append(h)

    deduped: list[Hypothesis] = []
    for key, group in groups.items():
        avg_conf = sum(h.confidence for h in group) / len(group)
        all_evidence = []
        for h in group:
            all_evidence.extend(h.supporting_evidence)
        deduped.append(
            Hypothesis(
                diagnosis=group[0].diagnosis,  # preserve original casing
                confidence=round(avg_conf, 3),
                supporting_evidence=list(dict.fromkeys(all_evidence)),  # dedup
                source_model=f"{len(group)}_models",
                source_pass=0,
            )
        )

    # Sort by confidence descending
    deduped.sort(key=lambda h: h.confidence, reverse=True)
    return deduped[:8]  # Cap at 8 hypotheses


# =====================================================================
# B) DYNAMIC ADVOCATE FACTORY
# =====================================================================


class AdvocateAgent:
    """
    Reusable advocate — ONE class, dynamically replicated per hypothesis.

    NOT hardcoded to any specialty.  Each instance defends a specific
    diagnosis and is parameterised at construction time.
    """

    def __init__(
        self,
        diagnosis: str,
        agent_id: str,
        model: str | None = None,
    ) -> None:
        settings = get_settings()
        self.diagnosis = diagnosis
        self.agent_id = agent_id
        self.model = model or settings.default_agent_model

        # Enforce model policy
        validate_advocate_model(self.model)

    async def argue(
        self,
        patient_data: dict[str, Any],
        transcript: list[dict[str, Any]],
        competing_diagnoses: list[str],
        round_number: int,
        *,
        peer_remarks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Produce one round of argumentation.

        Returns parsed JSON with defense, evidence, attacks, confidence,
        and optional tool_requests.
        """
        sys_msg = advocate_system_prompt(self.diagnosis)
        usr_msg = advocate_user_prompt(
            self.diagnosis,
            patient_data,
            transcript,
            competing_diagnoses,
            peer_remarks=peer_remarks,
        )

        result = await featherless_chat_json(
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": usr_msg},
            ],
            model=self.model,
            temperature=0.4,
            max_tokens=2048,
        )

        # Execute any tool requests
        tool_results: list[dict[str, Any]] = []
        tool_requests = []
        if isinstance(result, dict):
            tool_requests = result.get("tool_requests", [])
        if tool_requests:
            tool_outputs = await execute_tool_calls_batch(tool_requests)
            tool_results = [t.model_dump() for t in tool_outputs]

        return {
            "agent_role": "advocate",
            "agent_id": self.agent_id,
            "diagnosis": self.diagnosis,
            "response": result if isinstance(result, dict) else {"raw": result},
            "tool_results": tool_results,
            "round_number": round_number,
        }


async def advocate_round_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Run ALL active (non-eliminated) advocates concurrently.

    Dynamically creates one AdvocateAgent per active hypothesis,
    skipping eliminated advocates. Includes peer remarks from
    the previous round so advocates can strengthen weak areas.
    """
    s = OmniState.model_validate(state)
    settings = get_settings()

    eliminated_set = set(s.eliminated_advocates)

    # Collect peer remarks from previous round for each advocate
    remarks_by_advocate: dict[str, list[dict[str, Any]]] = {}
    if s.peer_ratings:
        for pr in s.peer_ratings:
            pr_dict = pr.model_dump() if isinstance(pr, PeerRating) else pr
            ratee = pr_dict.get("ratee_id", "")
            if ratee:
                remarks_by_advocate.setdefault(ratee, []).append({
                    "from": pr_dict.get("rater_id", ""),
                    "score": pr_dict.get("score", 0),
                    "remark": pr_dict.get("remark", ""),
                })

    # Build advocates dynamically
    advocates: list[AdvocateAgent] = []
    all_diagnoses = [
        h["diagnosis"] if isinstance(h, dict) else h.diagnosis
        for h in s.active_hypotheses
    ]

    for i, hyp in enumerate(s.active_hypotheses):
        diag = hyp["diagnosis"] if isinstance(hyp, dict) else hyp.diagnosis
        agent_id = f"advocate_{i}_{diag[:20]}"

        # Skip eliminated advocates
        if agent_id in eliminated_set:
            logger.info("advocate_eliminated_skip", agent_id=agent_id, diagnosis=diag)
            continue

        try:
            advocate = AdvocateAgent(
                diagnosis=diag,
                agent_id=agent_id,
                model=settings.default_agent_model,
            )
            advocates.append(advocate)
        except ModelPolicyViolation as e:
            logger.warning("advocate_model_blocked", diagnosis=diag, error=str(e))

    # Run all advocates concurrently (queue inside llm_client)
    transcript_dicts = [
        e.model_dump() if isinstance(e, DebateEntry) else e
        for e in s.debate_transcript
    ]

    tasks = [
        adv.argue(
            patient_data=s.patient_data,
            transcript=transcript_dicts,
            competing_diagnoses=[d for d in all_diagnoses if d != adv.diagnosis],
            round_number=s.current_round,
            peer_remarks=remarks_by_advocate.get(adv.agent_id),
        )
        for adv in advocates
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    new_entries: list[dict[str, Any]] = []
    updated_confidence = dict(s.confidence_scores)
    events: list[dict[str, Any]] = []

    for result in results:
        if isinstance(result, Exception):
            logger.warning("advocate_failed", error=str(result))
            continue

        response = result.get("response", {})
        confidence = response.get("confidence")
        if confidence is not None:
            updated_confidence[result["diagnosis"]] = float(confidence)

        entry = DebateEntry(
            agent_role="advocate",
            agent_id=result["agent_id"],
            agent_name=f"{result['diagnosis']} Advocate",
            content=json.dumps(response, default=str),
            round_number=s.current_round,
            tool_calls=result.get("tool_results", []),
            evidence_refs=response.get("evidence", []),
        )
        new_entries.append(entry.model_dump())

        events.append({
            "type": "advocate_argument",
            "diagnosis": result["diagnosis"],
            "confidence": confidence,
            "round": s.current_round,
            "timestamp": datetime.utcnow().isoformat(),
        })

    return {
        **state,
        "debate_transcript": [
            (e.model_dump() if isinstance(e, DebateEntry) else e)
            for e in s.debate_transcript
        ] + new_entries,
        "confidence_scores": updated_confidence,
        "pending_events": state.get("pending_events", []) + events,
    }


# =====================================================================
# C) SKEPTIC AGENT
# =====================================================================


async def skeptic_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Sceptical critique of all advocate arguments. (1-to-1 Mapping)

    • Spawns independent concurrent Skeptic tasks for each active Advocate.
    • Identifies contradictions and hallucinated claims against specific diagnoses.
    • VERIFIES SOURCE CREDIBILITY
    • Assigns targeted uncertainty penalties.
    """
    s = OmniState.model_validate(state)
    eliminated_set = set(s.eliminated_advocates)

    transcript_dicts = [
        e.model_dump() if isinstance(e, DebateEntry) else e
        for e in s.debate_transcript
    ]

    active_diagnoses = [
        h.diagnosis if isinstance(h, Hypothesis) else h["diagnosis"]
        for h in s.active_hypotheses
    ]

    tasks = []
    
    for i, diag in enumerate(active_diagnoses):
        agent_id = f"advocate_{i}_{diag[:20]}"
        if agent_id in eliminated_set:
            continue
            
        # Extract the specific argument this advocate JUST made
        adv_content = {}
        for entry in reversed(transcript_dicts):
            if entry.get("agent_id") == agent_id and entry.get("round_number") == s.current_round:
                raw_c = entry.get("content", "{}")
                if isinstance(raw_c, str):
                    try:
                        adv_content = json.loads(raw_c)
                    except:
                        adv_content = {"raw": raw_c}
                else:
                    adv_content = raw_c
                break

        skeptic_id = f"skeptic_{i}_{diag[:20]}"
        
        coro = featherless_chat_json(
            messages=[
                {"role": "system", "content": skeptic_system_prompt()},
                {
                    "role": "user",
                    "content": skeptic_user_prompt(
                        diag, adv_content, transcript_dicts, s.patient_data
                    ),
                },
            ],
            temperature=0.3,
            max_tokens=2048,
        )
        tasks.append((diag, skeptic_id, coro))

    results = await asyncio.gather(*[t[2] for t in tasks], return_exceptions=True)

    new_entries: list[dict[str, Any]] = []
    tool_results_overall: list[dict[str, Any]] = []
    new_credibility: list[dict[str, Any]] = []
    missing_tests_overall = []
    penalties = dict(s.uncertainty_penalties)
    
    events = []

    for (diag, skeptic_id, _), result in zip(tasks, results):
        if isinstance(result, Exception):
            logger.warning("skeptic_failed", skeptic_id=skeptic_id, diag=diag, error=str(result))
            continue
            
        if not isinstance(result, dict):
            result = {"raw": result}

        # Tools
        tool_requests = result.get("tool_requests", [])
        adv_tool_results = []
        if tool_requests:
            tool_outputs = await execute_tool_calls_batch(tool_requests) # This runs sequentially per skeptic, safe enough.
            adv_tool_results = [t.model_dump() for t in tool_outputs]
            tool_results_overall.extend(adv_tool_results)

        # Penalties - specific to this diag
        penalty = float(result.get("uncertainty_penalty", 0.0))
        if penalty > 0:
            current = penalties.get(diag, 0.0)
            penalties[diag] = round(current + penalty, 3)

        # Credibility
        for sc in result.get("source_credibility", []):
            if isinstance(sc, dict):
                new_credibility.append(
                    SourceCredibility(
                        source_url=sc.get("source_url", ""),
                        source_title=sc.get("source_title", ""),
                        cited_by_advocate=diag,
                        credibility_score=float(sc.get("credibility_score", 0.5)),
                        issues=sc.get("issues", []),
                        verified=sc.get("verified", False),
                    ).model_dump()
                )

        # Missing tests
        missing_tests_overall.extend(result.get("missing_tests", []))

        # Create entry
        entry = DebateEntry(
            agent_role="skeptic",
            agent_id=skeptic_id,
            agent_name=f"{diag} Skeptic",
            content=json.dumps(result, default=str),
            round_number=s.current_round,
            tool_calls=adv_tool_results,
        )
        new_entries.append(entry.model_dump())

        events.append({
            "type": "skeptic_objection",
            "target": diag,
            "penalty": penalty,
            "contradictions": result.get("contradictions", []),
            "hallucination_flags": result.get("hallucination_flags", []),
            "source_credibility_count": len(result.get("source_credibility", [])),
            "missing_tests": result.get("missing_tests", []),
            "round": s.current_round,
            "timestamp": datetime.utcnow().isoformat(),
        })

    return {
        **state,
        "debate_transcript": [
            (e.model_dump() if isinstance(e, DebateEntry) else e)
            for e in s.debate_transcript
        ] + new_entries,
        "uncertainty_penalties": penalties,
        "source_credibility": [
            (sc.model_dump() if isinstance(sc, SourceCredibility) else sc)
            for sc in s.source_credibility
        ] + new_credibility,
        "missing_data": [
            (m.model_dump() if isinstance(m, MissingDataItem) else m)
            for m in s.missing_data
        ] + [
            MissingDataItem(
                test_name=t,
                reason="Identified by skeptic",
                urgency=Urgency.MEDIUM,
            ).model_dump()
            for t in missing_tests_overall
        ],
        "pending_events": state.get("pending_events", []) + events,
    }


# =====================================================================
# D) PEER RATING NODE
# =====================================================================


async def peer_rating_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Each active advocate rates ALL other advocates' cases.

    Score formula:
        peer_score(advocate_i) = sum(all others' scores for i) / (N - 1)

    Produces a dict of advocate_id → computed peer score.
    """
    s = OmniState.model_validate(state)
    eliminated_set = set(s.eliminated_advocates)

    # Collect the latest advocate arguments from this round
    advocate_args: dict[str, dict[str, Any]] = {}
    for entry in s.debate_transcript:
        e = entry.model_dump() if isinstance(entry, DebateEntry) else entry
        if e.get("agent_role") == "advocate" and e.get("round_number") == s.current_round:
            agent_id = e.get("agent_id", "")
            if agent_id not in eliminated_set:
                try:
                    content = json.loads(e.get("content", "{}"))
                except (json.JSONDecodeError, TypeError):
                    content = {"raw": e.get("content", "")}
                advocate_args[agent_id] = {
                    "agent_id": agent_id,
                    "diagnosis": _extract_diagnosis_from_id(agent_id, s),
                    "argument": content,
                }

    active_advocates = list(advocate_args.values())

    # If only 1 or 0 advocates, skip peer rating
    if len(active_advocates) <= 1:
        logger.info("peer_rating_skip", reason="not enough advocates")
        return {
            **state,
            "pending_events": state.get("pending_events", []) + [{
                "type": "peer_rating_skip",
                "reason": "not enough advocates for peer rating",
                "timestamp": datetime.utcnow().isoformat(),
            }],
        }

    # Each advocate rates all others concurrently
    rating_tasks = []
    for rater in active_advocates:
        others = [a for a in active_advocates if a["agent_id"] != rater["agent_id"]]
        coro = featherless_chat_json(
            messages=[
                {"role": "system", "content": peer_rating_system_prompt(rater["diagnosis"])},
                {"role": "user", "content": peer_rating_user_prompt(rater["diagnosis"], others)},
            ],
            temperature=0.3,
            max_tokens=1024,
        )
        rating_tasks.append((rater, coro))

    # Execute all rating calls concurrently
    coros = [t[1] for t in rating_tasks]
    results = await asyncio.gather(*coros, return_exceptions=True)

    new_ratings: list[dict[str, Any]] = []

    for (rater, _), result in zip(rating_tasks, results):
        if isinstance(result, Exception):
            logger.warning("peer_rating_failed", rater=rater["agent_id"], error=str(result))
            continue

        if not isinstance(result, dict):
            continue

        ratings_dict = result.get("ratings", result)
        for ratee_id, rating_data in ratings_dict.items():
            if not isinstance(rating_data, dict):
                continue
            score = float(rating_data.get("score", 5))
            score = max(0.0, min(10.0, score))  # clamp 0-10
            remark = str(rating_data.get("remark", ""))

            new_ratings.append(
                PeerRating(
                    rater_id=rater["agent_id"],
                    ratee_id=ratee_id,
                    ratee_diagnosis=_extract_diagnosis_from_id(ratee_id, s),
                    score=score,
                    remark=remark,
                    round_number=s.current_round,
                ).model_dump()
            )

    # Compute advocate scores: sum(scores for advocate_i) / (N - 1)
    score_sums: dict[str, float] = {}
    score_counts: dict[str, int] = {}
    for r in new_ratings:
        ratee = r["ratee_id"]
        score_sums[ratee] = score_sums.get(ratee, 0.0) + r["score"]
        score_counts[ratee] = score_counts.get(ratee, 0) + 1

    advocate_scores: dict[str, float] = {}
    for agent_id in score_sums:
        count = score_counts.get(agent_id, 1)
        advocate_scores[agent_id] = round(score_sums[agent_id] / count, 2)

    events = [{
        "type": "peer_rating_complete",
        "ratings_count": len(new_ratings),
        "advocate_scores": advocate_scores,
        "round": s.current_round,
        "timestamp": datetime.utcnow().isoformat(),
    }]

    return {
        **state,
        "peer_ratings": [
            (pr.model_dump() if isinstance(pr, PeerRating) else pr)
            for pr in s.peer_ratings
        ] + new_ratings,
        "advocate_scores": advocate_scores,
        "pending_events": state.get("pending_events", []) + events,
    }


def _extract_diagnosis_from_id(agent_id: str, s: OmniState) -> str:
    """Extract the diagnosis name from an advocate's agent_id."""
    for i, hyp in enumerate(s.active_hypotheses):
        diag = hyp["diagnosis"] if isinstance(hyp, dict) else hyp.diagnosis
        expected_id = f"advocate_{i}_{diag[:20]}"
        if expected_id == agent_id:
            return diag
    return agent_id


# =====================================================================
# E) INQUISITOR AGENT
# =====================================================================


async def inquisitor_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Determine whether missing evidence materially changes the diagnosis.

    If critical data is missing → halt the graph and emit required tests.
    """
    s = OmniState.model_validate(state)

    hyp_dicts = [
        h.model_dump() if isinstance(h, Hypothesis) else h
        for h in s.active_hypotheses
    ]
    existing_missing = [
        m["test_name"] if isinstance(m, dict) else m.test_name
        for m in s.missing_data
    ]

    result = await featherless_chat_json(
        messages=[
            {"role": "system", "content": inquisitor_system_prompt()},
            {
                "role": "user",
                "content": inquisitor_user_prompt(
                    hyp_dicts,
                    s.confidence_scores,
                    s.uncertainty_penalties,
                    existing_missing,
                    s.patient_data,
                ),
            },
        ],
        temperature=0.2,
        max_tokens=1024,
    )

    if not isinstance(result, dict):
        result = {"should_halt": False, "raw": result}

    should_halt = result.get("should_halt", False)

    # Parse new missing data items
    new_missing: list[dict[str, Any]] = []
    for item in result.get("missing_data", []):
        if isinstance(item, dict):
            new_missing.append(
                MissingDataItem(
                    test_name=item.get("test_name", ""),
                    reason=item.get("reason", ""),
                    urgency=Urgency(item.get("urgency", "medium")),
                    impact_on_diagnosis=item.get("impact", ""),
                ).model_dump()
            )

    entry = DebateEntry(
        agent_role="inquisitor",
        agent_id="inquisitor_main",
        content=json.dumps(result, default=str),
        round_number=s.current_round,
    )

    update: dict[str, Any] = {
        **state,
        "debate_transcript": [
            (e.model_dump() if isinstance(e, DebateEntry) else e)
            for e in s.debate_transcript
        ] + [entry.model_dump()],
        "missing_data": [
            (m.model_dump() if isinstance(m, MissingDataItem) else m)
            for m in s.missing_data
        ] + new_missing,
    }

    events: list[dict[str, Any]] = []

    if should_halt:
        update["phase"] = WorkflowPhase.HALTED.value
        update["halt_reason"] = result.get("assessment", "Critical data missing")
        events.append({
            "type": "inquisitor_halt",
            "required_tests": [m.get("test_name", "") for m in new_missing],
            "follow_up_questions": result.get("follow_up_questions", []),
            "timestamp": datetime.utcnow().isoformat(),
        })
    else:
        events.append({
            "type": "inquisitor_clear",
            "assessment": result.get("assessment", ""),
            "timestamp": datetime.utcnow().isoformat(),
        })

    update["pending_events"] = state.get("pending_events", []) + events
    return update


# =====================================================================
# F) CORTEX ORCHESTRATOR (consensus + elimination)
# =====================================================================


async def cortex_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Consensus determination + advocate elimination.

    1. Compute adjusted scores:  adjusted = confidence - uncertainty_penalty
    2. Consider peer-rating scores
    3. Determine elimination:
       - avg_high = average of advocates scoring ABOVE overall mean
       - If an advocate's score diff from avg_high > 2 → eliminated
       - Always keep at least MIN_ADVOCATES alive
    4. Route: consensus → scribe, else → next round with fewer advocates
    """
    s = OmniState.model_validate(state)
    settings = get_settings()

    # Compute adjusted confidence scores
    adjusted: dict[str, float] = {}
    for diag in set(
        list(s.confidence_scores.keys()) + list(s.uncertainty_penalties.keys())
    ):
        raw = s.confidence_scores.get(diag, 0.0)
        penalty = s.uncertainty_penalties.get(diag, 0.0)
        adjusted[diag] = round(raw - penalty, 3)

    # Determine consensus: top score significantly higher than average
    consensus_reached = False
    if adjusted:
        avg_adjusted = sum(adjusted.values()) / len(adjusted)
        top_score = max(adjusted.values())
        if top_score - avg_adjusted >= 0.15:
            consensus_reached = True
    at_max_rounds = s.current_round >= s.max_rounds

    # ── Advocate elimination logic ───────────────────────────────
    newly_eliminated: list[str] = []
    advocate_scores = dict(s.advocate_scores)

    if advocate_scores and len(advocate_scores) > MIN_ADVOCATES:
        scores = list(advocate_scores.values())
        overall_mean = sum(scores) / len(scores) if scores else 0

        # Sort advocates by score ascending to eliminate weakest first
        sorted_advocates = sorted(advocate_scores.items(), key=lambda x: x[1])

        alive_count = len(advocate_scores) - len(s.eliminated_advocates)
        for agent_id, score in sorted_advocates:
            if alive_count <= MIN_ADVOCATES:
                break
            if agent_id in s.eliminated_advocates:
                continue
            
            # Eliminate if significantly lower than average (e.g., > 1.5 pts worse)
            diff = overall_mean - score
            if diff >= 1.5:
                newly_eliminated.append(agent_id)
                alive_count -= 1
                logger.info(
                    "advocate_eliminated",
                    agent_id=agent_id,
                    score=score,
                    overall_mean=overall_mean,
                    diff=diff,
                )

    all_eliminated = list(s.eliminated_advocates) + newly_eliminated

    # Also call Cortex LLM for nuanced determination
    result = await featherless_chat_json(
        messages=[
            {"role": "system", "content": cortex_system_prompt()},
            {
                "role": "user",
                "content": cortex_user_prompt(
                    s.confidence_scores,
                    s.uncertainty_penalties,
                    s.current_round,
                    s.max_rounds,
                    advocate_scores=advocate_scores,
                    eliminated=all_eliminated,
                ),
            },
        ],
        temperature=0.2,
        max_tokens=1024,
    )

    if not isinstance(result, dict):
        result = {"consensus_reached": consensus_reached}

    llm_consensus = result.get("consensus_reached", consensus_reached)
    leading = result.get("leading_diagnosis")
    recommendation = result.get("recommendation", "continue_debate")

    # Final determination: trust math + LLM
    final_consensus = consensus_reached or (llm_consensus and bool(leading))

    if not final_consensus and at_max_rounds:
        # Deadlock: pick highest adjusted score
        if adjusted:
            leading = max(adjusted, key=adjusted.get)  # type: ignore[arg-type]
        final_consensus = True  # Force completion
        recommendation = "declare_uncertainty"

    entry = DebateEntry(
        agent_role="cortex",
        agent_id="cortex_orchestrator",
        content=json.dumps(result, default=str),
        round_number=s.current_round,
    )

    events = [
        {
            "type": "consensus_event",
            "consensus_reached": final_consensus,
            "leading_diagnosis": leading,
            "adjusted_scores": adjusted,
            "advocate_peer_scores": advocate_scores,
            "newly_eliminated": newly_eliminated,
            "total_eliminated": all_eliminated,
            "recommendation": recommendation,
            "round": s.current_round,
            "timestamp": datetime.utcnow().isoformat(),
        }
    ]

    update: dict[str, Any] = {
        **state,
        "debate_transcript": [
            (e.model_dump() if isinstance(e, DebateEntry) else e)
            for e in s.debate_transcript
        ] + [entry.model_dump()],
        "confidence_scores": {**s.confidence_scores, **{k: v for k, v in adjusted.items()}},
        "consensus_reached": final_consensus,
        "eliminated_advocates": all_eliminated,
        "current_round": s.current_round + 1,
        "pending_events": state.get("pending_events", []) + events,
    }

    if final_consensus and leading:
        update["phase"] = WorkflowPhase.CONSENSUS.value
    elif not at_max_rounds:
        update["phase"] = WorkflowPhase.DEBATE.value

    return update


# =====================================================================
# G) SCRIBE AGENT (final report + comprehensive audit trail)
# =====================================================================


async def scribe_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Generate the final structured clinical report AND build
    a comprehensive audit trail covering the entire session.

    Audit trail includes:
    - OCR extractions
    - Triage model outputs
    - All debate rounds (advocate, skeptic, ratings)
    - Source credibility assessments
    - Peer ratings & advocate scores
    - Elimination history
    - Final consensus
    """
    s = OmniState.model_validate(state)

    hyp_dicts = [
        h.model_dump() if isinstance(h, Hypothesis) else h
        for h in s.active_hypotheses
    ]
    transcript_dicts = [
        e.model_dump() if isinstance(e, DebateEntry) else e
        for e in s.debate_transcript
    ]

    # Determine consensus diagnosis
    consensus_diag: str | None = None
    if s.confidence_scores:
        adjusted = {
            k: s.confidence_scores.get(k, 0) - s.uncertainty_penalties.get(k, 0)
            for k in s.confidence_scores
        }
        consensus_diag = max(adjusted, key=adjusted.get)  # type: ignore[arg-type]

    result = await featherless_chat_json(
        messages=[
            {"role": "system", "content": scribe_system_prompt()},
            {
                "role": "user",
                "content": scribe_user_prompt(
                    s.patient_data,
                    hyp_dicts,
                    transcript_dicts,
                    s.confidence_scores,
                    s.uncertainty_penalties,
                    consensus_diag,
                    ocr_extractions=s.ocr_extractions,
                    peer_ratings=[
                        (pr.model_dump() if isinstance(pr, PeerRating) else pr)
                        for pr in s.peer_ratings
                    ],
                    advocate_scores=s.advocate_scores,
                    eliminated_advocates=s.eliminated_advocates,
                    source_credibility=[
                        (sc.model_dump() if isinstance(sc, SourceCredibility) else sc)
                        for sc in s.source_credibility
                    ],
                ),
            },
        ],
        temperature=0.2,
        max_tokens=2048,
    )

    if not isinstance(result, dict):
        result = {
            "primary_diagnosis": consensus_diag or "Undetermined",
            "confidence_pct": 0,
            "summary": str(result),
        }

    diagnosis_result = DiagnosisResult(
        primary_diagnosis=result.get("primary_diagnosis", consensus_diag or "Undetermined"),
        confidence_pct=float(result.get("confidence_pct", 0)),
        differential_list=result.get("differential_list", []),
        supporting_evidence=result.get("supporting_evidence", []),
        contradictory_evidence=result.get("contradictory_evidence", []),
        missing_investigations=result.get("missing_investigations", []),
        recommended_next_tests=result.get("recommended_next_tests", []),
        emergency_escalation=result.get("emergency_escalation", False),
        scribe_summary=result.get("summary", ""),
    )

    # ── Build comprehensive audit trail ──────────────────────────
    audit_trail = {
        "session_id": s.session_id,
        "request_id": s.request_id,
        "generated_at": datetime.utcnow().isoformat(),
        "phases": {
            "ocr_extraction": {
                "extractions": s.ocr_extractions,
                "extraction_count": len(s.ocr_extractions),
            },
            "triage": {
                "models_used": list({
                    o.get("model", "") for o in s.raw_triage_outputs
                }),
                "raw_outputs": s.raw_triage_outputs,
                "hypotheses_generated": hyp_dicts,
                "hypotheses_count": len(hyp_dicts),
            },
            "debate": {
                "total_rounds": s.current_round,
                "transcript": transcript_dicts,
                "entry_count": len(transcript_dicts),
            },
            "peer_ratings": {
                "all_ratings": [
                    (pr.model_dump() if isinstance(pr, PeerRating) else pr)
                    for pr in s.peer_ratings
                ],
                "final_scores": s.advocate_scores,
                "ratings_count": len(s.peer_ratings),
            },
            "elimination": {
                "eliminated_advocates": s.eliminated_advocates,
                "total_eliminated": len(s.eliminated_advocates),
            },
            "source_credibility": {
                "assessments": [
                    (sc.model_dump() if isinstance(sc, SourceCredibility) else sc)
                    for sc in s.source_credibility
                ],
                "total_assessed": len(s.source_credibility),
            },
            "missing_data": {
                "items": [
                    (m.model_dump() if isinstance(m, MissingDataItem) else m)
                    for m in s.missing_data
                ],
                "total": len(s.missing_data),
            },
        },
        "consensus": {
            "reached": s.consensus_reached,
            "diagnosis": consensus_diag,
            "confidence_scores": s.confidence_scores,
            "uncertainty_penalties": s.uncertainty_penalties,
        },
        "final_diagnosis": diagnosis_result.model_dump(),
    }

    # Store finalized transcript and vectors into MongoDB fully async
    try:
        await store_case(
            session_id=s.session_id,
            request_id=s.request_id,
            final_diagnosis=diagnosis_result.primary_diagnosis,
            confidence=diagnosis_result.confidence_pct,
            audit_trail=audit_trail,
        )
    except Exception as e:
        logger.error(f"MongoDB dual-write failed non-fatally: {e}")

    events = [
        {
            "type": "final_report",
            "diagnosis": diagnosis_result.model_dump(),
            "timestamp": datetime.utcnow().isoformat(),
        }
    ]

    return {
        **state,
        "phase": WorkflowPhase.COMPLETE.value,
        "final_diagnosis": diagnosis_result.model_dump(),
        "consensus_reached": True,
        "audit_trail": audit_trail,
        "pending_events": state.get("pending_events", []) + events,
    }
