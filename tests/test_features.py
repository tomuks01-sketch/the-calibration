"""P1 feature-store tests (zero-dep, run: python tests/test_features.py).

Covers the Asset backbone + crowd/baseline feature extraction + the fs-v1
feature-store record shape, per SIGNAL_SPEC.md. Honesty invariants enforced:
missing data -> available:false (never invented); composite is left None in
P1; regime is split descriptive vs adjustmentCandidate(applied:false).
"""

import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from assets import AssetKind, _num, from_coin, from_event  # noqa: E402
from features.baseline import baseline_features  # noqa: E402
from features.crowd import crowd_features  # noqa: E402
from features.store import build_record, build_records, write_features  # noqa: E402


def _binary_event():
    return {
        "id": "30001", "title": "Will X happen?", "category": "Politics",
        "binary": True, "leadPrice": 0.62, "volume": 1_000_000.0,
        "liquidity": 50_000.0, "daysToResolution": 12.3,
        "outcomes": [{"label": "Yes", "price": 0.62, "conditionId": "0xCOND1"}],
        "model": {"name": "QEST", "version": "baseline-v1", "prob": 0.58,
                  "divergencePp": -4.0, "tracked": True, "status": "PENDING"},
    }


def _multi_event():
    return {
        "id": "30002", "title": "Who wins?", "category": "Elections",
        "binary": False, "leadPrice": 0.31, "volume": 2_000_000.0,
        "liquidity": 90_000.0, "daysToResolution": 200.0,
        "outcomes": [{"label": "A", "price": 0.31, "conditionId": "0xCONDA"}],
        # no model block -> baseline unavailable
    }


def _coin():
    return {"symbol": "BTC", "name": "Bitcoin", "change24h": 1.7, "change7d": -1.0}


def test_num_guards_bools_and_numbers():
    # bool must NOT be coerced to a number (isinstance(True, int) trap)
    assert _num(True) is None and _num(False) is None
    assert _num(1) == 1.0 and _num(0.5) == 0.5
    assert _num("x") is None and _num(None) is None


def test_binary_event_missing_condition_id_is_visible():
    e = {"id": "9", "title": "t", "category": "c", "binary": True,
         "leadPrice": 0.5, "outcomes": [{"label": "Yes", "price": 0.5}]}
    a = from_event(e)
    assert a.asset_id == "UNKNOWN_COND:9"   # sentinel, never a silent event-id mismatch


def test_asset_from_event_binary():
    a = from_event(_binary_event())
    assert a.kind is AssetKind.PM_BINARY, a.kind
    assert a.asset_id == "0xCOND1", a.asset_id          # matches ledger conditionId
    assert a.crowd_prob == 0.62
    assert a.horizon_days == 12.3
    assert a.volume == 1_000_000.0 and a.liquidity == 50_000.0
    assert a.category == "Politics"


def test_asset_from_event_multi():
    a = from_event(_multi_event())
    assert a.kind is AssetKind.PM_MULTI
    assert a.asset_id == "30002"                        # event id, not a sub-market
    assert a.crowd_prob == 0.31


def test_asset_from_coin():
    a = from_coin(_coin())
    assert a.kind is AssetKind.CRYPTO
    assert a.asset_id == "btc"                          # lowercased symbol
    assert a.crowd_prob is None                         # crypto has no outcome prob
    assert a.category == "crypto"


def test_crowd_features_available_and_missing():
    pm = crowd_features(from_event(_binary_event()))
    assert pm["available"] is True and pm["prob"] == 0.62
    # fields we don't fetch yet must be honest nulls, not invented
    assert pm["spread"] is None and pm["tradeVelocity"] is None
    assert "source" in pm
    cr = crowd_features(from_coin(_coin()))
    assert cr["available"] is False and cr["prob"] is None


def test_baseline_features():
    on = baseline_features(from_event(_binary_event()))
    assert on["available"] is True
    assert on["prob"] == 0.58
    assert abs(on["gapVsCrowd"] - (-0.04)) < 1e-9       # divergencePp -> fraction
    assert on["signalQuality"] == "insufficient"        # 0 resolved -> gated
    off = baseline_features(from_event(_multi_event()))
    assert off["available"] is False and off["prob"] is None


def test_build_record_shape():
    a = from_event(_binary_event())
    rec = build_record(a, crowd_features(a), baseline_features(a))
    for k in ("assetId", "kind", "title", "category", "horizonDays",
              "crowd", "baseline", "regime", "pressure", "composite"):
        assert k in rec, k
    assert rec["composite"] is None                     # P2 fills this
    assert rec["pressure"]["class"] == "descriptive"
    assert rec["pressure"]["available"] is False
    assert rec["regime"]["adjustmentCandidate"]["applied"] is False
    assert rec["regime"]["descriptive"]["available"] is False


def test_build_records_pm_and_crypto():
    recs = build_records([_binary_event(), _multi_event()], [_coin()])
    assert len(recs) == 3
    kinds = {r["kind"] for r in recs}
    assert kinds == {"PM_BINARY", "PM_MULTI", "CRYPTO"}


def test_write_features_atomic_and_schema():
    recs = build_records([_binary_event()], [_coin()])
    with tempfile.TemporaryDirectory() as d:
        target = pathlib.Path(d) / "features.json"
        write_features(recs, target, "2026-05-30T00:00:00Z")
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data["schemaVersion"] == "fs-v1"
        assert data["weightsVersion"] == "w-v1"
        assert data["generatedAt"] == "2026-05-30T00:00:00Z"
        assert len(data["records"]) == 2
        assert not (pathlib.Path(d) / "features.json.tmp").exists()


if __name__ == "__main__":
    test_num_guards_bools_and_numbers()
    test_binary_event_missing_condition_id_is_visible()
    test_asset_from_event_binary()
    test_asset_from_event_multi()
    test_asset_from_coin()
    test_crowd_features_available_and_missing()
    test_baseline_features()
    test_build_record_shape()
    test_build_records_pm_and_crypto()
    test_write_features_atomic_and_schema()
    print("ALL P1 FEATURE TESTS PASSED")
