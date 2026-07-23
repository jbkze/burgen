#!/usr/bin/env python3
"""Enriches castles with Komoot hike counts and the nearest train station.

Reads  data/castles.jsonl   (raw scrape)
Writes data/enrichment.json ({castle_id: {komoot, station}})

Only castles with at least one image are enriched (the site shows only
those). Resume-capable: already-enriched ids are skipped, progress is
saved regularly. Stations come from HAFAS when it is up, otherwise from
Transitous (MOTIS) reverse-geocoding — then without a HAFAS station_id.

  python enrich.py               # enrich everything missing
  python enrich.py --limit N     # only N castles (for testing)
"""

import json
import sys
import time
from pathlib import Path

import requests

DATA = Path(__file__).parent / "data"
RAW = DATA / "castles.jsonl"
OUT = DATA / "enrichment.json"
DELAY = 0.35
HEADERS = {"User-Agent": "BurgenPlaner/1.0", "Accept": "application/hal+json,application/json"}
HAFAS = "https://v6.db.transport.rest"
TRANSITOUS = "https://api.transitous.org/api/v1"
TIMEOUT = 8

session = requests.Session()
session.headers.update(HEADERS)
hafas_down = False


def get_komoot_score(lat, lon, radius=1000):
    for attempt in range(4):
        try:
            r = session.get("https://api.komoot.de/v007/discover_tours/", params={
                "lat": lat, "lng": lon, "sport": "hike",
                "max_distance": radius, "limit": 20, "page": 0,
                "srid": 4326, "format": "simple",
            }, timeout=TIMEOUT)
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code != 200:
                return None
            data = r.json()
            total = data.get("page", {}).get("totalElements", 0)
            tours = data.get("_embedded", {}).get("tours", [])
            ratings = [t.get("rating_score", 0) for t in tours if t.get("rating_score")]
            avg = round(sum(ratings) / len(ratings), 2) if ratings else None
            return {"hike_count": total, "avg_rating": avg,
                    "total_ratings": sum(t.get("rating_count", 0) for t in tours)}
        except Exception:
            time.sleep(2)
    return None


def station_hafas(lat, lon):
    r = session.get(f"{HAFAS}/locations/nearby", params={
        "latitude": lat, "longitude": lon, "results": 5}, timeout=TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"HAFAS {r.status_code}")
    stations = r.json()
    pick = next((s for s in stations if any(
        (s.get("products") or {}).get(k) for k in ("regional", "suburban", "nationalExpress"))),
        stations[0] if stations else None)
    if not pick:
        return None
    return {
        "station_id": pick["id"],
        "station_name": pick["name"],
        "station_distance_m": pick.get("distance", 0),
        "station_lat": pick.get("location", {}).get("latitude"),
        "station_lon": pick.get("location", {}).get("longitude"),
    }


def station_transitous(lat, lon):
    from math import atan2, cos, radians, sin, sqrt
    r = session.get(f"{TRANSITOUS}/reverse-geocode",
                    params={"place": f"{lat},{lon}", "type": "STOP"}, timeout=TIMEOUT)
    if r.status_code != 200:
        return None
    stops = r.json()
    if not stops:
        return None
    s = stops[0]
    dlat, dlon = radians(s["lat"] - lat), radians(s["lon"] - lon)
    a = sin(dlat / 2) ** 2 + cos(radians(lat)) * cos(radians(s["lat"])) * sin(dlon / 2) ** 2
    dist = int(6371000 * 2 * atan2(sqrt(a), sqrt(1 - a)))
    return {
        "station_id": None,  # kein HAFAS-Bezug; Zugplanung läuft über Koordinaten
        "station_name": s["name"],
        "station_distance_m": dist,
        "station_lat": s["lat"],
        "station_lon": s["lon"],
    }


def get_station(lat, lon):
    global hafas_down
    if not hafas_down:
        try:
            return station_hafas(lat, lon)
        except Exception:
            hafas_down = True
            print("  (HAFAS nicht erreichbar — Bahnhöfe via Transitous)")
    try:
        return station_transitous(lat, lon)
    except Exception:
        return None


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None

    castles = []
    seen = set()
    with open(RAW, encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            if "error" in c or not c.get("images") or c.get("lat") is None or c["id"] in seen:
                continue
            seen.add(c["id"])
            castles.append(c)

    enrichment = json.loads(OUT.read_text()) if OUT.exists() else {}
    todo = [c for c in castles if str(c["id"]) not in enrichment]
    if limit:
        todo = todo[:limit]
    print(f"{len(castles)} Burgen mit Bild+Koordinaten, {len(enrichment)} angereichert, {len(todo)} offen")

    t0 = time.time()
    for i, c in enumerate(todo):
        rec = {}
        komoot = get_komoot_score(c["lat"], c["lon"])
        if komoot:
            rec["komoot"] = komoot
        time.sleep(DELAY)
        station = get_station(c["lat"], c["lon"])
        if station:
            rec["station"] = station
        time.sleep(DELAY)
        enrichment[str(c["id"])] = rec
        if (i + 1) % 25 == 0 or i + 1 == len(todo):
            OUT.write_text(json.dumps(enrichment, ensure_ascii=False))
            rate = (i + 1) / max(1, time.time() - t0)
            print(f"  {i+1}/{len(todo)} ({rate:.1f}/s, ~{(len(todo)-i-1)/max(rate,0.01)/60:.0f} min verbleibend)", flush=True)

    OUT.write_text(json.dumps(enrichment, ensure_ascii=False))
    print(f"Fertig -> {OUT}")


if __name__ == "__main__":
    main()
