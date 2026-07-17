#!/usr/bin/env python3
"""Enrich castle data with Komoot hike scores and nearest train stations."""

import json
import time
import sys
from pathlib import Path

import requests

DATA = Path(__file__).parent / "site" / "data"
DELAY = 0.5
HEADERS = {"User-Agent": "BurgenPlaner/1.0", "Accept": "application/hal+json,application/json"}
HAFAS = "https://v6.db.transport.rest"
TIMEOUT = 5
MAX_RETRIES = 2


def get_komoot_score(lat, lon, radius=1000):
    try:
        r = requests.get("https://api.komoot.de/v007/discover_tours/", params={
            "lat": lat, "lng": lon, "sport": "hike",
            "max_distance": radius, "limit": 20, "page": 0,
            "srid": 4326, "format": "simple",
        }, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        data = r.json()
        page = data.get("page", {})
        total = page.get("totalElements", 0)
        tours = data.get("_embedded", {}).get("tours", [])
        avg_rating = None
        total_ratings = 0
        if tours:
            ratings = [t.get("rating_score", 0) for t in tours if t.get("rating_score")]
            counts = [t.get("rating_count", 0) for t in tours if t.get("rating_count")]
            if ratings:
                avg_rating = round(sum(ratings) / len(ratings), 2)
            total_ratings = sum(counts)
        return {"hike_count": total, "avg_rating": avg_rating, "total_ratings": total_ratings}
    except Exception as e:
        print(f"    Komoot error: {e}")
        return None


def get_nearest_station(lat, lon):
    try:
        r = requests.get(f"{HAFAS}/locations/nearby", params={
            "latitude": lat, "longitude": lon, "results": 5,
        }, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        stations = r.json()
        for s in stations:
            products = s.get("products", {})
            if products.get("regional") or products.get("suburban") or products.get("nationalExpress"):
                return {
                    "station_id": s["id"],
                    "station_name": s["name"],
                    "station_distance_m": s.get("distance", 0),
                    "station_lat": s.get("location", {}).get("latitude"),
                    "station_lon": s.get("location", {}).get("longitude"),
                }
        if stations:
            s = stations[0]
            return {
                "station_id": s["id"],
                "station_name": s["name"],
                "station_distance_m": s.get("distance", 0),
                "station_lat": s.get("location", {}).get("latitude"),
                "station_lon": s.get("location", {}).get("longitude"),
            }
        return None
    except Exception as e:
        print(f"    HAFAS error: {e}")
        return None


def main():
    enriched = DATA / "castles_enriched.json"
    fallback = DATA / "castles.json"
    src = enriched if enriched.exists() else fallback
    with open(src, encoding="utf-8") as f:
        castles = json.load(f)

    komoot_only = "--komoot-only" in sys.argv

    print(f"Enriching {len(castles)} castles...{' (Komoot only)' if komoot_only else ''}")

    for i, castle in enumerate(castles):
        name = castle.get("name", "?")
        print(f"  [{i+1}/{len(castles)}] {name}", end="", flush=True)

        if "lat" not in castle:
            print(" — no coordinates, skipping")
            continue

        lat, lon = castle["lat"], castle["lon"]

        komoot = get_komoot_score(lat, lon)
        if komoot:
            castle["komoot"] = komoot
            print(f" — {komoot['hike_count']} hikes", end="")
        time.sleep(DELAY)

        if not komoot_only and "station" not in castle:
            station = get_nearest_station(lat, lon)
            if station:
                castle["station"] = station
                print(f", station: {station['station_name']} ({station['station_distance_m']}m)", end="")
            time.sleep(DELAY)

        print()

    out = DATA / "castles_enriched.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(castles, f, ensure_ascii=False, indent=2)

    with_komoot = sum(1 for c in castles if "komoot" in c)
    with_station = sum(1 for c in castles if "station" in c)
    print(f"\nDone! {with_komoot} with Komoot, {with_station} with station. Saved to {out}")


if __name__ == "__main__":
    main()
