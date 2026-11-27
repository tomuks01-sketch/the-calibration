import gzip
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fetch_markets import _decode_body  # noqa: E402


def test_decodes_plain_body():
    assert _decode_body(b'[{"id": 1}]', None) == '[{"id": 1}]'


def test_gunzips_when_header_says_gzip():
    assert _decode_body(gzip.compress(b"[1, 2]"), "gzip") == "[1, 2]"


def test_gunzips_by_magic_bytes_without_header():
    assert _decode_body(gzip.compress(b"[]"), None) == "[]"
