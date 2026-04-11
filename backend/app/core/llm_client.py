"""
app.core.llm_client
~~~~~~~~~~~~~~~~~~~~~
Centralised, fully-async LLM callers for both providers.

ARCHITECTURE RULES
──────────────────
• Gemini  → OCR / PDF / image parsing ONLY  (direct REST)
• Featherless → ALL agent reasoning calls   (OpenAI-compat chat)

CONCURRENCY — COST-AWARE MULTI-KEY QUEUE
─────────────────────────────────────────
Each Featherless API key has a concurrency budget of 4 units.
Models have different costs:
  • Heavy models (e.g. Kimi-K2.5, Qwen2.5-72B) → 4 units each
  • Light models (e.g. gemma-4-31B-it, Qwen3-32B) → 2 units each

The batch worker:
  1. Drains pending requests from the queue.
  2. For each request, picks a key with enough free budget (round-robin).
  3. Fires a batch concurrently, respecting per-key budget limits.
  4. Processes results one by one.
  5. Bad format → retry (up to 2×). No response → don't retry.
"""

from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    FeatherlessError,
    FeatherlessRateLimitError,
    GeminiOCRError,
    ModelPolicyViolation,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

# Max times we retry a request when the LLM responds but the format is bad
MAX_FORMAT_RETRIES = 2


# =====================================================================
# COST-AWARE MULTI-KEY QUEUE WORKER
# =====================================================================


@dataclass
class _KeySlot:
    """Tracks the live concurrency budget for one API key."""

    api_key: str
    budget: int           # max budget (e.g. 4)
    used: int = 0         # currently consumed budget

    @property
    def free(self) -> int:
        return self.budget - self.used


@dataclass
class _QueueItem:
    """One pending Featherless request sitting in the queue."""

    payload: dict[str, Any]
    url: str
    timeout: float
    model: str
    cost: int                                                      # concurrency cost
    future: asyncio.Future = field(default=None)                   # type: ignore[assignment]
    format_retries_left: int = MAX_FORMAT_RETRIES
    assigned_key: str = ""                                         # filled by scheduler


class _CostAwareWorker:
    """
    Queue-based, cost-aware, multi-key batch processor.

    Scheduling algorithm:
    1. Drain all pending items from the queue.
    2. For each item, find a key with enough free budget (round-robin).
    3. Items that don't fit any key wait for the next cycle.
    4. Fire the fitted batch concurrently.
    5. On completion, free the budget on each key.
    6. Process results one by one; re-queue format-retry items.

    No background task — callers cooperatively drive the loop.
    """

    def __init__(self, api_keys: list[str], budget_per_key: int = 4) -> None:
        self._slots = [_KeySlot(api_key=k, budget=budget_per_key) for k in api_keys]
        self._queue: asyncio.Queue[_QueueItem] = asyncio.Queue()
        self._lock = asyncio.Lock()
        logger.info(
            "cost_aware_worker_init",
            num_keys=len(api_keys),
            budget_per_key=budget_per_key,
            total_budget=len(api_keys) * budget_per_key,
        )

    async def submit(self, item: _QueueItem) -> dict[str, Any]:
        """Enqueue an item and cooperatively drive the batch loop."""
        await self._queue.put(item)

        if self._lock.locked():
            # Another coroutine is driving — just wait for our result
            return await item.future  # type: ignore[return-value]

        async with self._lock:
            while not self._queue.empty():
                scheduled, deferred = self._schedule_batch()
                if scheduled:
                    await self._fire_batch(scheduled)
                # Put deferred items back
                for d in deferred:
                    await self._queue.put(d)
                # If nothing was scheduled but items remain, all keys are full.
                # Break to avoid busy-loop; they'll be picked up after results return.
                if not scheduled and deferred:
                    break

        return await item.future  # type: ignore[return-value]

    def _schedule_batch(self) -> tuple[list[_QueueItem], list[_QueueItem]]:
        """
        Drain the queue and assign each item to a key that has enough budget.

        Returns (scheduled, deferred):
          - scheduled: items that got a key assigned
          - deferred: items that couldn't fit any key right now
        """
        pending: list[_QueueItem] = []
        while True:
            try:
                pending.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        scheduled: list[_QueueItem] = []
        deferred: list[_QueueItem] = []

        for item in pending:
            # Round-robin: pick the slot with the most free budget
            best_slot = max(self._slots, key=lambda s: s.free)

            if best_slot.free >= item.cost:
                best_slot.used += item.cost
                item.assigned_key = best_slot.api_key
                scheduled.append(item)
                logger.debug(
                    "request_scheduled",
                    model=item.model,
                    cost=item.cost,
                    key=best_slot.api_key[-6:],
                    key_used=best_slot.used,
                    key_free=best_slot.free,
                )
            else:
                deferred.append(item)

        if scheduled:
            logger.info(
                "batch_scheduled",
                size=len(scheduled),
                deferred=len(deferred),
                key_status=[
                    {"key": s.api_key[-6:], "used": s.used, "free": s.free}
                    for s in self._slots
                ],
            )

        return scheduled, deferred

    async def _fire_batch(self, batch: list[_QueueItem]) -> None:
        """Fire all scheduled items concurrently, then process one by one."""

        async def _do_request(
            item: _QueueItem,
        ) -> tuple[_QueueItem, httpx.Response | Exception]:
            headers = {
                "Authorization": f"Bearer {item.assigned_key}",
                "Content-Type": "application/json",
            }
            try:
                async with httpx.AsyncClient(timeout=item.timeout) as client:
                    resp = await client.post(
                        item.url, headers=headers, json=item.payload,
                    )
                return (item, resp)
            except Exception as exc:
                return (item, exc)

        # Fire concurrently
        tasks = [_do_request(it) for it in batch]
        results = await asyncio.gather(*tasks)

        # Process results one by one
        retry_items: list[_QueueItem] = []

        for item, result in results:
            # Free the budget for this request's key
            self._free_budget(item.assigned_key, item.cost)

            if isinstance(result, Exception):
                # Network error / timeout → do NOT retry
                logger.warning(
                    "featherless_no_response",
                    model=item.model,
                    error=type(result).__name__,
                    detail=str(result),
                )
                if not item.future.done():
                    item.future.set_exception(
                        FeatherlessError(
                            f"No response from Featherless: {result}",
                            details={"error": str(result)},
                        )
                    )
                continue

            resp: httpx.Response = result

            if resp.status_code == 429:
                if not item.future.done():
                    item.future.set_exception(
                        FeatherlessRateLimitError(
                            "Featherless rate limit hit",
                            details={"status": 429, "body": resp.text},
                        )
                    )
                continue

            if resp.status_code != 200:
                logger.warning(
                    "featherless_server_error",
                    model=item.model,
                    status=resp.status_code,
                )
                if not item.future.done():
                    item.future.set_exception(
                        FeatherlessError(
                            f"Featherless returned {resp.status_code}",
                            details={"status": resp.status_code, "body": resp.text},
                        )
                    )
                continue

            # 200 OK — extract the message
            try:
                data = resp.json()
                choices = data.get("choices")
                if not choices:
                    raise ValueError("No choices in response")
                message = choices[0]["message"]
                content = message.get("content", "")

                if not content or not content.strip():
                    raise ValueError("Empty content in LLM response")

                logger.info(
                    "featherless_response",
                    model=item.model,
                    finish_reason=choices[0].get("finish_reason"),
                    key=item.assigned_key[-6:],
                )

                if not item.future.done():
                    item.future.set_result(message)

            except (json.JSONDecodeError, KeyError, IndexError, ValueError) as exc:
                # Bad format → retry if retries left
                if item.format_retries_left > 0:
                    item.format_retries_left -= 1
                    logger.warning(
                        "featherless_bad_format_retry",
                        model=item.model,
                        error=str(exc),
                        retries_left=item.format_retries_left,
                    )
                    item.assigned_key = ""  # clear so scheduler reassigns
                    retry_items.append(item)
                else:
                    logger.error(
                        "featherless_bad_format_exhausted",
                        model=item.model,
                        error=str(exc),
                    )
                    if not item.future.done():
                        item.future.set_exception(
                            FeatherlessError(
                                f"LLM responded but format invalid after retries: {exc}",
                                details={"error": str(exc)},
                            )
                        )

        # Re-queue format-retry items
        for ri in retry_items:
            await self._queue.put(ri)

    def _free_budget(self, api_key: str, cost: int) -> None:
        """Return budget units to the key slot."""
        for slot in self._slots:
            if slot.api_key == api_key:
                slot.used = max(0, slot.used - cost)
                return


# ── Worker singleton ────────────────────────────────────────────────

_worker: _CostAwareWorker | None = None


def _get_worker() -> _CostAwareWorker:
    """Lazily create the cost-aware worker."""
    global _worker
    if _worker is None:
        settings = get_settings()
        _worker = _CostAwareWorker(
            api_keys=settings.featherless_api_keys,
            budget_per_key=settings.featherless_budget_per_key,
        )
    return _worker


# =====================================================================
# FEATHERLESS AGENT CALLER
# =====================================================================


async def featherless_chat(
    messages: list[dict[str, Any]],
    model: str | None = None,
    *,
    temperature: float = 0.4,
    max_tokens: int = 2048,
    response_format: dict[str, str] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Enqueue a Featherless chat request and wait for the result.

    The request goes into a global queue. A cost-aware batch worker
    assigns it to the API key with the most free budget, respecting
    each model's concurrency cost:
      • Heavy models (Kimi-K2.5, Qwen2.5-72B, etc.) → cost 4
      • Light models (gemma-4-31B, Qwen3-32B, etc.) → cost 2

    With 4 keys × budget 4 = 16 total units:
      • Up to 4 heavy requests simultaneously, OR
      • Up to 8 light requests simultaneously, OR
      • Any mix that fits

    Retry policy:
      • LLM responded but format is bad → retried up to 2 times.
      • No response (timeout / network / HTTP error) → NOT retried.
    """
    cfg = settings or get_settings()
    used_model = model or cfg.default_agent_model
    cost = cfg.model_cost(used_model)

    payload: dict[str, Any] = {
        "model": used_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        payload["response_format"] = response_format

    logger.info(
        "featherless_enqueue",
        model=used_model,
        cost=cost,
        msg_count=len(messages),
    )

    worker = _get_worker()
    loop = asyncio.get_running_loop()

    item = _QueueItem(
        payload=payload,
        url=cfg.featherless_base_url,
        timeout=cfg.llm_timeout,
        model=used_model,
        cost=cost,
        future=loop.create_future(),
    )

    return await worker.submit(item)


async def featherless_chat_content(
    messages: list[dict[str, Any]],
    model: str | None = None,
    **kwargs: Any,
) -> str:
    """Convenience wrapper that returns just the text content."""
    msg = await featherless_chat(messages, model, **kwargs)
    return msg.get("content", "")


async def featherless_chat_json(
    messages: list[dict[str, Any]],
    model: str | None = None,
    **kwargs: Any,
) -> dict[str, Any] | list[Any]:
    """Call Featherless and parse the response as JSON."""
    kwargs.setdefault("response_format", {"type": "json_object"})
    msg = await featherless_chat(messages, model, **kwargs)
    raw = msg.get("content", "{}")

    # Handle models that wrap JSON in markdown fences
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        return json.loads(cleaned)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        logger.warning("featherless_json_parse_failed", raw_content=raw[:500])
        return {"raw": raw}


# =====================================================================
# MODEL POLICY ENFORCEMENT
# =====================================================================


def validate_advocate_model(model: str, settings: Settings | None = None) -> None:
    """Raise ``ModelPolicyViolation`` if *model* is forbidden for advocates."""
    cfg = settings or get_settings()
    if model in cfg.advocate_forbidden_models:
        raise ModelPolicyViolation(
            f"Model '{model}' is forbidden for advocate agents",
            details={"model": model, "forbidden": cfg.advocate_forbidden_models},
        )


# =====================================================================
# GEMINI OCR CALLER  (strict REST — no LangChain)
# =====================================================================

_GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models"
    "/{model}:generateContent?key={key}"
)


async def gemini_ocr(
    *,
    file_bytes: bytes | None = None,
    file_path: str | Path | None = None,
    mime_type: str = "application/pdf",
    prompt: str = "Extract all text, lab values, and clinical findings from this document. Return structured JSON.",
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """
    Call Gemini for OCR / document extraction.

    Either *file_bytes* or *file_path* must be provided.
    """
    cfg = settings or get_settings()

    if file_bytes is None and file_path is not None:
        file_bytes = Path(file_path).read_bytes()
    if file_bytes is None:
        raise GeminiOCRError("Either file_bytes or file_path is required")

    b64_data = base64.standard_b64encode(file_bytes).decode("ascii")

    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_data,
                        }
                    },
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
        },
    }

    url = _GEMINI_ENDPOINT.format(model=cfg.gemini_model, key=cfg.gemini_api_key)

    try:
        async with httpx.AsyncClient(timeout=cfg.llm_timeout) as client:
            logger.info("gemini_ocr_request", mime_type=mime_type, size_kb=len(file_bytes) // 1024)
            resp = await client.post(url, json=body)
    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        raise GeminiOCRError(
            f"Gemini request failed: {exc}",
            details={"error": str(exc)},
        )

    if resp.status_code != 200:
        raise GeminiOCRError(
            f"Gemini returned {resp.status_code}",
            details={"status": resp.status_code, "body": resp.text[:1000]},
        )

    data = resp.json()

    try:
        candidates = data.get("candidates", [])
        if not candidates:
            raise GeminiOCRError("No candidates in Gemini response")

        raw_text = candidates[0]["content"]["parts"][0]["text"]

        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        parsed = json.loads(cleaned)

        if isinstance(parsed, dict):
            parsed = [parsed]
        if isinstance(parsed, list):
            return [
                item if isinstance(item, dict) else {"content": str(item)}
                for item in parsed
            ]
        return [{"content": str(parsed)}]

    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        logger.warning("gemini_ocr_json_fallback", error=str(exc))
        raw_text = ""
        try:
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            raw_text = str(data)
        return [{"content": raw_text, "parse_mode": "raw"}]


async def gemini_ocr_image(
    *,
    image_bytes: bytes,
    mime_type: str = "image/png",
    prompt: str = "Extract all visible text, lab values, clinical findings, and annotations from this medical image. Return structured JSON.",
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Convenience wrapper for image-based OCR via Gemini."""
    return await gemini_ocr(
        file_bytes=image_bytes,
        mime_type=mime_type,
        prompt=prompt,
        settings=settings,
    )
