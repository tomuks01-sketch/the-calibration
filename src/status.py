"""One-command live health check for The Calibration.

Read-only, no secrets, works from anywhere. For a fresh session or the user:
`python src/status.py` prints the full current state in ~1 screen so nobody
has to re-derive or re-explain anything.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE = "https://tomuks01-sketch.github.io/the-calibration"
FILES = ("", "briefs/", "scoreboard/", "data.json", "scoreboard.json",
         "ledger.json", "briefs/latest.json")


def _get(url: str, as_json: bool = False):
    req = urllib.request.Request(url, headers={"User-Agent": "status/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read().decode("utf-8")
        return (json.loads(body) if as_json else r.status)


def _age_min(iso: str) -> str:
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return f"{int((datetime.now(timezone.utc) - t).total_seconds() // 60)} min ago"
    except (ValueError, TypeError):
        return "unknown"


def main() -> None:
    print("=" * 56)
    print(" THE CALIBRATION — live status")
    print("=" * 56)

    print("\nReachability:")
    for f in FILES:
        try:
            code = _get(f"{BASE}/{f}")
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            code = f"DOWN ({getattr(exc, 'code', 'net')})"
        print(f"  {('/' + f) or '/':<22} {code}")

    try:
        d = _get(f"{BASE}/data.json", as_json=True)
        ev = d.get("events", [])
        ctx = [e for e in ev if e.get("context")]
        tiers: dict[str, int] = {}
        for e in ctx:
            t = e["context"]["tier"]
            tiers[t] = tiers.get(t, 0) + 1
        qest = sum(1 for e in ev if e.get("model"))
        m = d.get("macro", {})
        print("\nData snapshot:")
        print(f"  generated      {_age_min(d.get('generatedAt', ''))}")
        print(f"  events         {len(ev)}  | QEST shown {qest}")
        print(f"  context tiers  {tiers or 'none'}  (B = live AI)")
        print(f"  macro          available={m.get('available')} "
              f"regime={m.get('regime')}")
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        print(f"\nData snapshot: UNREADABLE ({exc})")

    try:
        sb = _get(f"{BASE}/scoreboard.json", as_json=True)
        c = sb.get("counts", {})
        print("\nScoreboard (the moat):")
        print(f"  resolved {c.get('resolved')} | pending {c.get('pending')} "
              f"| void {c.get('void')} | confidence {sb.get('confidence')} "
              f"| model {sb.get('modelVersion')}")
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        print(f"\nScoreboard: UNREADABLE ({exc})")

    print("\nNext: see ~/.claude memory project_resume_state.md for open "
          "decisions (multi-source Kalshi; distribution A/B/C).")
    print("=" * 56)


if __name__ == "__main__":
    main()
