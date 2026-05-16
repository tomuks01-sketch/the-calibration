"""Keyless news layer: Google News RSS for a market's topic.

No API key required. Read-only. Returns recent headlines so a trader can see
what is driving a market — context, not advice.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
REQUEST_TIMEOUT_S = 20
MAX_HEADLINES = 5
_STOPWORDS = {"will", "the", "win", "be", "a", "to", "of", "in", "on", "by", "for"}


@dataclass(frozen=True)
class Headline:
    title: str
    source: str
    published: str
    link: str


def topic_from_question(question: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", question)
    kept = [w for w in words if w.lower() not in _STOPWORDS]
    return " ".join(kept[:6]) if kept else question[:60]


def fetch_headlines(topic: str, limit: int = MAX_HEADLINES) -> list[Headline]:
    query = urllib.parse.quote(topic)
    url = f"{GOOGLE_NEWS_RSS}?q={query}&hl=en-US&gl=US&ceid=US:en"
    req = urllib.request.Request(
        url, headers={"User-Agent": "polymarket-insight/0.1 (analytics)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
            root = ET.fromstring(resp.read())
    except (urllib.error.URLError, ET.ParseError, TimeoutError):
        return []

    headlines: list[Headline] = []
    for item in list(root.iterfind(".//item"))[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        source_el = item.find("{*}source")
        source = source_el.text.strip() if source_el is not None and source_el.text else ""
        if title:
            headlines.append(Headline(title, source, pub, link))
    return headlines
