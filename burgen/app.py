#!/usr/bin/env python3
"""FastAPI backend for the Burgen trip planner."""

import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles

DATA_DIR = Path(__file__).parent / "data"
SITE_DIR = Path(__file__).parent / "site"
HAFAS = "https://v6.db.transport.rest"
OSRM = "https://router.project-osrm.org"

app = FastAPI()
castles = []


@app.on_event("startup")
def load_data():
    global castles
    enriched = DATA_DIR / "castles_enriched.json"
    fallback = DATA_DIR / "castles.json"
    src = enriched if enriched.exists() else fallback
    with open(src, encoding="utf-8") as f:
        castles = json.load(f)


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@app.get("/api/castles")
def list_castles(
    q: Optional[str] = None,
    state: Optional[str] = None,
    typ: Optional[str] = None,
    erhaltung: Optional[str] = None,
    min_hikes: Optional[int] = None,
):
    results = []
    for c in castles:
        meta = c.get("meta", {})
        if q and q.lower() not in c.get("name", "").lower():
            continue
        if state and state.lower() != meta.get("Bundesland", "").lower():
            continue
        if typ and typ.lower() not in meta.get("Klassifizierung", "").lower():
            continue
        if erhaltung and erhaltung.lower() not in meta.get("Erhaltung - Heutiger Zustand", "").lower():
            continue
        if min_hikes:
            if c.get("komoot", {}).get("hike_count", 0) < min_hikes:
                continue
        results.append(build_summary(c))
    return {"count": len(results), "castles": results}


@app.get("/api/castles/{castle_id}")
def get_castle(castle_id: int):
    for c in castles:
        if c["id"] == castle_id:
            return c
    return {"error": "not found"}


@app.get("/api/plan")
def plan_trip(
    origin: str = Query(..., description="Start station name, e.g. 'Leipzig Hbf'"),
    mode: str = Query("train", description="'train' or 'car'"),
    max_minutes: int = Query(120, description="Max travel time in minutes"),
    typ: Optional[str] = None,
    erhaltung: Optional[str] = None,
    min_hikes: Optional[int] = None,
):
    origin_info = resolve_station(origin)
    if not origin_info:
        return {"error": f"Station '{origin}' nicht gefunden"}

    candidates = []
    for c in castles:
        if "lat" not in c:
            continue
        meta = c.get("meta", {})
        if typ and typ.lower() not in meta.get("Klassifizierung", "").lower():
            continue
        if erhaltung and erhaltung.lower() not in meta.get("Erhaltung - Heutiger Zustand", "").lower():
            continue
        if min_hikes and c.get("komoot", {}).get("hike_count", 0) < min_hikes:
            continue
        candidates.append(c)

    if not candidates:
        return {"origin": origin_info, "mode": mode, "max_minutes": max_minutes, "count": 0, "castles": []}

    if mode == "car":
        results = plan_car(origin_info, candidates, max_minutes)
    else:
        results = plan_train(origin_info, candidates, max_minutes)

    results.sort(key=lambda x: x.get("travel", {}).get("duration_min") or 999)

    return {
        "origin": origin_info,
        "mode": mode,
        "max_minutes": max_minutes,
        "count": len(results),
        "castles": results,
    }


def plan_car(origin_info, candidates, max_minutes):
    """Use OSRM table API: one request for all driving times."""
    olat, olon = origin_info["lat"], origin_info["lon"]
    coords = f"{olon},{olat}" + "".join(f";{c['lon']},{c['lat']}" for c in candidates)

    try:
        r = requests.get(
            f"{OSRM}/table/v1/driving/{coords}",
            params={"sources": "0", "annotations": "duration,distance"},
            timeout=15,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        durations = data.get("durations", [[]])[0]
        distances = data.get("distances", [[]])[0]
    except Exception:
        return []

    results = []
    for i, c in enumerate(candidates):
        dur_sec = durations[i + 1] if i + 1 < len(durations) else None
        dist_m = distances[i + 1] if i + 1 < len(distances) else None
        if dur_sec is None:
            continue
        dur_min = round(dur_sec / 60)
        if dur_min > max_minutes:
            continue
        summary = build_summary(c)
        summary["distance_km"] = round(dist_m / 1000, 1) if dist_m else None
        summary["travel"] = {"duration_min": dur_min, "distance_km": summary["distance_km"]}
        results.append(summary)
    return results


def plan_train(origin_info, candidates, max_minutes):
    """Pre-filter with OSRM driving times, then HAFAS for top candidates in parallel."""
    olat, olon = origin_info["lat"], origin_info["lon"]

    with_station = [c for c in candidates if c.get("station")]
    if not with_station:
        return []

    coords = f"{olon},{olat}" + "".join(f";{c['lon']},{c['lat']}" for c in with_station)
    try:
        r = requests.get(
            f"{OSRM}/table/v1/driving/{coords}",
            params={"sources": "0", "annotations": "duration"},
            timeout=15,
        )
        if r.status_code == 200:
            durations = r.json().get("durations", [[]])[0]
            scored = []
            for i, c in enumerate(with_station):
                dur_sec = durations[i + 1] if i + 1 < len(durations) else None
                drive_min = round(dur_sec / 60) if dur_sec else 999
                scored.append((c, drive_min))
            scored.sort(key=lambda x: x[1])
            top = [c for c, d in scored if d <= max_minutes * 2][:15]
        else:
            top = sorted(with_station, key=lambda c: haversine_km(olat, olon, c["lat"], c["lon"]))[:15]
    except Exception:
        top = sorted(with_station, key=lambda c: haversine_km(olat, olon, c["lat"], c["lon"]))[:15]

    origin_id = origin_info["id"]
    results = []

    def fetch_journey(c):
        station_id = c["station"]["station_id"]
        journey = get_journey(origin_id, station_id)
        if journey and journey["duration_min"] <= max_minutes:
            summary = build_summary(c)
            summary["distance_km"] = round(haversine_km(olat, olon, c["lat"], c["lon"]), 1)
            summary["travel"] = journey
            return summary
        return None

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(fetch_journey, c): c for c in top}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    return results


@app.get("/api/filters")
def get_filters():
    states = sorted(set(
        c.get("meta", {}).get("Bundesland", "")
        for c in castles if c.get("meta", {}).get("Bundesland")
    ))
    types = sorted(set(
        t.strip()
        for c in castles
        for t in c.get("meta", {}).get("Klassifizierung", "").split(",")
        if t.strip()
    ))
    erhaltung = sorted(set(
        c.get("meta", {}).get("Erhaltung - Heutiger Zustand", "")
        for c in castles if c.get("meta", {}).get("Erhaltung - Heutiger Zustand")
    ))
    return {"states": states, "types": types, "erhaltung": erhaltung}


def build_summary(c):
    meta = c.get("meta", {})
    komoot = c.get("komoot", {})
    img = c["images"][0]["thumb"] if c.get("images") else None
    return {
        "id": c["id"],
        "name": c["name"],
        "lat": c.get("lat"),
        "lon": c.get("lon"),
        "state": meta.get("Bundesland", ""),
        "kreis": meta.get("Kreis", ""),
        "typ": meta.get("Klassifizierung", ""),
        "erhaltung": meta.get("Erhaltung - Heutiger Zustand", ""),
        "datierung": meta.get("Datierung-Beginn", ""),
        "kurzansprache": meta.get("Kurzansprache", ""),
        "image": img,
        "hike_count": komoot.get("hike_count", 0),
        "avg_rating": komoot.get("avg_rating"),
        "station": c.get("station", {}).get("station_name"),
        "station_distance_m": c.get("station", {}).get("station_distance_m"),
    }


def resolve_station(name):
    try:
        r = requests.get(f"{HAFAS}/locations", params={
            "query": name, "results": 1,
        }, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        if not data:
            return None
        s = data[0]
        return {
            "id": s["id"],
            "name": s["name"],
            "lat": s.get("location", {}).get("latitude"),
            "lon": s.get("location", {}).get("longitude"),
        }
    except Exception:
        return None


def get_journey(from_id, to_id):
    try:
        r = requests.get(f"{HAFAS}/journeys", params={
            "from": from_id, "to": to_id, "results": 1,
        }, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        journeys = data.get("journeys", [])
        if not journeys:
            return None
        j = journeys[0]
        legs = j.get("legs", [])
        if not legs:
            return None
        dep = legs[0].get("departure", "")
        arr = legs[-1].get("arrival", "")
        if dep and arr:
            t1 = datetime.fromisoformat(dep.replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(arr.replace("Z", "+00:00"))
            duration_min = int((t2 - t1).total_seconds() / 60)
            changes = len([l for l in legs if l.get("line")]) - 1
            lines = [l.get("line", {}).get("name", "") for l in legs if l.get("line")]
            return {
                "duration_min": duration_min,
                "changes": max(0, changes),
                "lines": lines,
            }
        return None
    except Exception:
        return None


app.mount("/", StaticFiles(directory=str(SITE_DIR), html=True), name="static")
