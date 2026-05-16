"""Per-market QUALITATIVE context line — strictly subordinate, fail-open.

Honesty contract (enforced in code, not comments):
- NEVER a probability, verdict, recommendation, or forecast. QEST is the only
  number on this product. This layer only says "what is being discussed".
- Tier A (default, keyless, £0): deterministic surface of real Google News
  headlines already fetched — zero synthesis, zero hallucination risk.
- Tier B (optional, LLM_API_KEY secret; card-free Groq/OpenRouter etc.,
  OpenAI-compatible): a 1-sentence sourced summary; any
  output containing odds/verdict/forecast language is REJECTED and we fall
  back to Tier A. Tier A is always the floor.
- Must never raise into the pipeline; never block snapshot/ledger/QEST.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# Provider-agnostic, OpenAI-compatible. Works with any card-free free
# provider (Groq default; OpenRouter, etc.) via env overrides — NO Google,
# NO billing profile. Configure with repo secret LLM_API_KEY (+ optional
# LLM_API_BASE / LLM_MODEL).
# `or default` (not get(k, default)) so an empty env (unset GitHub var still
# injects "") falls back correctly.
LLM_API_BASE = os.environ.get("LLM_API_BASE") or "https://api.groq.com/openai/v1"
LLM_MODEL = os.environ.get("LLM_MODEL") or "llama-3.3-70b-versatile"
LLM_CALL_GAP_S = 4.0  # space calls to respect free-tier RPM
REQUEST_TIMEOUT_S = 12

# If a Tier-B summary contains any of these, it is rejected (honesty guard).
_BANNED = re.compile(
    r"\b(\d{1,3}\s?%|percent|odds|probabilit|likely|unlikely|will (win|happen)"
    r"|should (buy|bet)|forecast|predict|expect to|our call|verdict|"
    r"recommend|edge)\b",
    re.IGNORECASE,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sources(headlines: list[dict], limit: int = 3) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for h in headlines:
        name = (h.get("source") or "").strip()
        link = (h.get("link") or "").strip()
        if not name or name in seen or not link:
            continue
        seen.add(name)
        out.append({"name": name[:32], "link": link})
        if len(out) >= limit:
            break
    return out


def _tier_a(headlines: list[dict]) -> dict | None:
    """Deterministic: just surface the actual headlines. No synthesis."""
    titles = [str(h.get("title") or "").strip() for h in headlines if h.get("title")]
    titles = [t for t in titles if t][:2]
    if not titles:
        return None
    summary = "Coverage in the news: " + " · ".join(f"“{t}”" for t in titles)
    return {
        "summary": summary[:300],
        "sources": _sources(headlines),
        "tier": "A",
        "asOf": _now(),
    }


# Keyless, content-free diagnostics so we can see WHY Tier B fell back
# without ever logging the key or any model text.
STATS: dict[str, int] = {
    "attempt": 0, "ok": 0, "banned": 0, "http_error": 0,
    "empty": 0, "no_key": 0, "no_headlines": 0, "skipped_ratelimited": 0,
}
# Once the free tier 429s in a run, stop hammering it (wastes time, no value).
_RATE_LIMITED = False


def _llm(event_title: str, headlines: list[dict]) -> str | None:
    """OpenAI-compatible chat completion (Groq default; any compatible
    provider via LLM_API_BASE/LLM_MODEL). Card-free. Never raises out."""
    global _RATE_LIMITED
    if _RATE_LIMITED:
        STATS["skipped_ratelimited"] += 1
        return None
    key = os.environ.get("LLM_API_KEY")
    if not key:
        STATS["no_key"] += 1
        return None
    heads = "; ".join(
        str(h.get("title") or "")[:140] for h in headlines[:5] if h.get("title")
    )
    if not heads:
        STATS["no_headlines"] += 1
        return None
    STATS["attempt"] += 1
    prompt = (
        "In ONE neutral sentence, summarise only what current news coverage is "
        "DISCUSSING about this topic. Describe coverage, do not assess outcome. "
        "Absolutely no probabilities, odds, predictions, recommendations or "
        f"verdicts.\n\nTopic: {event_title}\nHeadlines: {heads}"
    )
    body = json.dumps(
        {
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 256,
            "temperature": 0.2,
        }
    ).encode()
    req = urllib.request.Request(
        f"{LLM_API_BASE.rstrip('/')}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "the-calibration/1.0 (+https://github.com)",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    time.sleep(LLM_CALL_GAP_S)  # space calls under free-tier RPM
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        # HTTP status only — never the key. Also capture the provider's own
        # error CODE (e.g. "model_terms_required") which is safe (no secret).
        code = getattr(exc, "code", "net")
        STATS[f"http_{code}"] = STATS.get(f"http_{code}", 0) + 1
        STATS["http_error"] += 1
        try:
            raw = exc.read().decode("utf-8", "replace")[:200]
            try:
                tag = str(
                    json.loads(raw).get("error", {}).get("code") or "json"
                )[:40]
            except (ValueError, AttributeError, TypeError):
                # non-JSON body (e.g. WAF/CDN HTML block) — first words only
                tag = (raw.strip().split("\n", 1)[0] or "empty")[:40]
            tag = re.sub(r"[^a-zA-Z0-9_]", "_", tag) or "empty"
            STATS[f"err_{tag}"] = STATS.get(f"err_{tag}", 0) + 1
        except (AttributeError, ValueError, TypeError):
            pass
        if code == 429:  # quota hit — stop further calls this run
            _RATE_LIMITED = True
        return None
    text = ""
    try:
        choice = (data.get("choices") or [{}])[0]
        text = ((choice.get("message") or {}).get("content") or "").strip()
    except (IndexError, AttributeError):
        text = ""
    if not text:
        STATS["empty"] += 1
        return None
    if _BANNED.search(text):  # honesty guard -> caller falls back to Tier A
        STATS["banned"] += 1
        return None
    STATS["ok"] += 1
    return text[:300]


def build_context(
    event_title: str, headlines: list[dict], use_llm: bool
) -> dict | None:
    """Tier B if enabled+clean, else Tier A floor, else None. Never raises."""
    try:
        if use_llm:
            s = _llm(event_title, headlines)
            if s:
                return {
                    "summary": s,
                    "sources": _sources(headlines),
                    "tier": "B",
                    "asOf": _now(),
                }
        return _tier_a(headlines)
    except Exception:  # fail-open: context must never break the pipeline
        return None


def llm_enabled() -> bool:
    return bool(os.environ.get("LLM_API_KEY"))
