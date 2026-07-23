#!/usr/bin/env python3
"""Builds the site's data files from the raw scrape + enrichment.

Reads  data/castles.jsonl        (raw scrape, one JSON object per line)
       data/enrichment.json      (optional: {id: {komoot, station}})
Writes site/data/index.json      (slim list for browse/map/search/planner)
       site/data/burg/<id>.json  (full record per castle, fetched on demand)

Only castles with at least one image make it into the site.
Index records use short keys to keep the payload small:
  id, n(ame), s(tate=Bundesland), k(reis), t(yp=Klassifizierung),
  e(rhaltung), d(atierung), c(=Kurzansprache, truncated), i(mage thumb,
  relative to the shared ebidat image prefix), lat, lon, h(ike count),
  st=[station_id, station_lat, station_lon] (id may be null)
"""

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "castles.jsonl"
ENRICH = ROOT / "data" / "enrichment.json"
SITE_DATA = ROOT / "site" / "data"
BURG_DIR = SITE_DATA / "burg"
IMG_PREFIX = "https://www.ebidat.de/r30/vc_content/bilder/firma451/msvc_intern/"


def main():
    enrichment = {}
    if ENRICH.exists():
        enrichment = {int(k): v for k, v in json.loads(ENRICH.read_text()).items()}

    castles = {}
    with open(RAW, encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            if "error" in c or not c.get("name") or not c.get("images"):
                continue
            castles[c["id"]] = c  # last write wins on duplicate ids

    ordered = sorted(castles.values(), key=lambda c: (c["name"].lower(), c["id"]))

    if BURG_DIR.exists():
        shutil.rmtree(BURG_DIR)
    BURG_DIR.mkdir(parents=True)

    index = []
    for c in ordered:
        extra = enrichment.get(c["id"], {})
        komoot, station = extra.get("komoot"), extra.get("station")
        full = {**c}
        if komoot:
            full["komoot"] = komoot
        if station:
            full["station"] = station
        (BURG_DIR / f"{c['id']}.json").write_text(
            json.dumps(full, ensure_ascii=False), encoding="utf-8")

        m = c.get("meta") or {}
        thumb = c["images"][0]["thumb"]
        rec = {
            "id": c["id"],
            "n": c["name"],
            "s": m.get("Bundesland", ""),
            "k": m.get("Kreis", ""),
            "t": m.get("Klassifizierung", ""),
            "e": m.get("Erhaltung - Heutiger Zustand", ""),
            "d": m.get("Datierung-Beginn", ""),
            "c": (m.get("Kurzansprache") or "")[:200],
            "i": thumb[len(IMG_PREFIX):] if thumb.startswith(IMG_PREFIX) else thumb,
        }
        if c.get("lat") is not None:
            rec["lat"] = round(c["lat"], 5)
            rec["lon"] = round(c["lon"], 5)
        if komoot and komoot.get("hike_count"):
            rec["h"] = komoot["hike_count"]
        if station and station.get("station_lat") is not None:
            rec["st"] = [station.get("station_id"),
                         round(station["station_lat"], 5),
                         round(station["station_lon"], 5)]
        index.append(rec)

    out = SITE_DATA / "index.json"
    out.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    size_mb = out.stat().st_size / 1e6
    print(f"{len(index)} Burgen mit Bild -> {out} ({size_mb:.2f} MB) + {len(index)} Detail-Dateien")


if __name__ == "__main__":
    main()
