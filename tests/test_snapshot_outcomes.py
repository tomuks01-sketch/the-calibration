import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from generate_snapshot import is_live_outcome, section_for  # noqa: E402


def test_inactive_placeholder_is_hidden():
    assert not is_live_outcome({"groupItemTitle": "Team H", "active": False, "closed": False})


def test_resolved_submarket_is_hidden():
    assert not is_live_outcome({"active": True, "closed": True, "outcomePrices": '["1","0"]'})


def test_open_submarket_is_shown():
    assert is_live_outcome({"active": True, "closed": False})


def test_noisy_tags_map_to_clean_sections():
    assert section_for(["Main Election", "Israel"]) == "Elections"
    assert section_for(["Bitcoin", "Price Milestone"]) == "Crypto"
    assert section_for(["UCL", "Soccer"]) == "Sports"
    assert section_for(["Parent For Derivative"], "Will Jesus Christ return?") == "Other"


def test_short_keyword_needs_whole_word():
    assert section_for(["Main Street Gossip"]) != "Economy"
