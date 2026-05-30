"""Generate web/world.svg from Natural Earth (public domain) country data.

Reproducible build of the homepage geopolitics map. Downloads the
ne_110m_admin_0_countries GeoJSON (public domain), projects it with a
plain equirectangular mapping into a 1000x500 viewBox, rounds coordinates
to keep the file small, and writes one <path id="c-XX"> per country (XX =
ISO-3166 alpha-2, using ISO_A2_EH so France/Norway resolve correctly).

No CDN at runtime — the output SVG is committed and served statically.

Usage:  python src/gen_world_map.py
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

SRC = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_110m_admin_0_countries.geojson"
)
OUT = Path(__file__).resolve().parent.parent / "web" / "world.svg"
W, H = 1000, 500


def _proj(lon: float, lat: float) -> tuple[float, float]:
    return round((lon + 180) / 360 * W, 1), round((90 - lat) / 180 * H, 1)


def _ring(ring: list) -> str:
    pts, last = [], None
    for lon, lat in ring:
        xy = _proj(lon, lat)
        if xy == last:
            continue
        last = xy
        pts.append(f"{xy[0]},{xy[1]}")
    return "M" + "L".join(pts) + "Z" if len(pts) >= 3 else ""


def build() -> str:
    with urllib.request.urlopen(SRC, timeout=60) as r:
        gj = json.loads(r.read().decode("utf-8"))
    paths = []
    for f in gj["features"]:
        p = f["properties"]
        iso = p.get("ISO_A2_EH") or p.get("ISO_A2") or "-99"
        if iso in ("-99", None, ""):
            iso = (p.get("ADM0_A3", "")[:2] or "XX")
        if p.get("NAME") == "Antarctica":
            continue
        geom = f["geometry"]
        coords, kind, d = geom["coordinates"], geom["type"], ""
        if kind == "Polygon":
            for ring in coords:
                d += _ring(ring)
        elif kind == "MultiPolygon":
            for poly in coords:
                for ring in poly:
                    d += _ring(ring)
        if d:
            paths.append(f'<path id="c-{iso}" d="{d}"/>')
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 500" '
        'preserveAspectRatio="xMidYMid meet" class="worldsvg" role="img" '
        'aria-label="World map of markets by country">' + "".join(paths) + "</svg>"
    )


if __name__ == "__main__":
    svg = build()
    OUT.write_text(svg, encoding="utf-8")
    print(f"wrote {OUT} ({len(svg)} bytes)")
