"""P4 repricing-pressure tests (zero-dep, run: python tests/test_pressure.py).

Pressure is DESCRIPTIVE-only (SIGNAL_SPEC.md §1/§2): "what is moving / unsettled
NOW", never "which way it resolves". It must carry no probability field and
must never be read by the composite. PM vs crypto move units differ (fraction
vs percent) and are normalised before any threshold.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from assets import from_coin, from_event  # noqa: E402
from features.pressure import pressure_features  # noqa: E402


def _pm(change24h=None, lead=0.5, horizon=None, binary=True):
    e = {"id": "1", "title": "t", "category": "c", "binary": binary,
         "leadPrice": lead, "daysToResolution": horizon,
         "outcomes": [{"conditionId": "0xC", "price": lead}]}
    if change24h is not None:
        e["change24h"] = change24h
    return from_event(e)


def test_pm_sudden_move_and_pre_resolution():
    p = pressure_features(_pm(change24h=0.06, lead=0.5, horizon=2))
    assert p["available"] is True and p["class"] == "descriptive"
    assert p["suddenMove"] is True
    assert p["move24hPp"] == 6.0
    assert p["infoEventNear"] is True          # horizon <= 3
    assert p["preResolutionVol"] is True       # near + sudden
    assert p["overheated"] is False            # lead 0.5 not extreme
    assert "prob" not in p                      # descriptive — never a probability


def test_pm_overheated_when_priced_near_certain():
    p = pressure_features(_pm(change24h=0.01, lead=0.98, horizon=100))
    assert p["overheated"] is True
    assert p["suddenMove"] is False             # 1pp move is not sudden


def test_pm_missing_move_is_unavailable():
    p = pressure_features(_pm(change24h=None))
    assert p["available"] is False and p["class"] == "descriptive"


def test_crypto_percent_move_is_normalised():
    # crypto change24h is a PERCENT (7.0 = 7%) -> normalised to 0.07 fraction
    p = pressure_features(from_coin({"symbol": "BTC", "name": "Bitcoin", "change24h": 7.0}))
    assert p["available"] is True
    assert p["suddenMove"] is True              # 7% >= 5% threshold
    assert p["move24hPp"] == 7.0
    # PM-only descriptors are False for crypto (no outcome / resolution)
    assert p["overheated"] is False and p["infoEventNear"] is False


def test_composite_never_reads_pressure():
    import inspect

    import composite
    src = inspect.getsource(composite)
    assert "pressure" not in src                # composite must not touch pressure


if __name__ == "__main__":
    test_pm_sudden_move_and_pre_resolution()
    test_pm_overheated_when_priced_near_certain()
    test_pm_missing_move_is_unavailable()
    test_crypto_percent_move_is_normalised()
    test_composite_never_reads_pressure()
    print("ALL P4 PRESSURE TESTS PASSED")
