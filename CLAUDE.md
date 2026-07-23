# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

**Burgen in Deutschland** — a fully static site (castle browser + trip planner + visit diary) served via **GitHub Pages** at **https://jbkze.github.io/burgen/**. There is no backend: all dynamic features run as JavaScript in the visitor's browser against public CORS-enabled APIs.

See PRODUCT.md for product goals and design principles.

## Architecture

- `site/` — the deployed site, exactly as served by GitHub Pages
  - `site/index.html` — the main frontend (single file: markup, CSS, JS). Loads the slim `data/index.json` once for browsing/filtering/map/planner; full castle records are lazy-loaded per castle. Hash routing (`#/`, `#/planer`, `#/burg/<id>`) makes castles linkable and keeps the back button working. The stream renders incrementally (IntersectionObserver); maps use Leaflet with canvas markers.
  - `site/data/index.json` — slim index of **all castles that have at least one image** (short keys: `id,n,s,k,t,e,d,c,i,lat,lon,h,st`; image paths relative to the shared ebidat prefix).
  - `site/data/burg/<id>.json` — full record per castle (sections, gallery, meta, komoot, station), fetched on demand by the detail view.
  - `site/tagebuch/index.html` — the castle diary app (single file, same design language). Visits with per-category star ratings, tags and free text; persisted in `localStorage` (key `burgen-tagebuch-v1`), JSON export/import for backup. `?burg=<id>` preselects a castle (deep-linked from the main app's detail view).
- Trip planner calls external APIs directly from the browser:
  - `https://v6.db.transport.rest` (HAFAS/DB) — station lookup and train journeys
  - `https://api.transitous.org` (MOTIS) — fallback geocoding + train routing when HAFAS is down (it often is)
  - `https://nominatim.openstreetmap.org` — last-resort geocoding for the origin
  - `https://router.project-osrm.org` — driving time/distance matrix. Candidates are pre-filtered by air distance and capped (`OSRM_MAX`) before the table call — the demo server rejects huge tables.
- Each castle's detail view deep-links to Google Maps (`google.com/maps/search/?api=1&query=<name, town, state>`) for reviews and directions — no API key needed.

## Data pipeline

Run in order; all steps are resume-capable and skip work already done:

1. `scraper.py` — scrapes **all** German castles from ebidat.de (~8,800). IDs are cached in `data/ids.json`; per-castle results are checkpointed in `data/castles.jsonl` (gitignored; committed compressed as `data/castles.jsonl.gz`). ebidat.de serves **ISO-8859-1**; responses are parsed from bytes with BeautifulSoup so the declared charset is honored — never force `r.encoding`.
2. `enrich.py` — adds Komoot hike counts and nearest train stations (HAFAS, falling back to Transitous) for castles with images; writes `data/enrichment.json`.
3. `build_site.py` — composes `site/data/index.json` + `site/data/burg/<id>.json` from the raw scrape and enrichment. **Only castles with at least one image are included.**

## Deployment

Push to `main` → GitHub Actions (`.github/workflows/deploy.yml`) uploads `site/` verbatim to GitHub Pages (source must stay set to "GitHub Actions" in the repo's Pages settings).

## Local development

```bash
python -m http.server -d site
# open http://localhost:8000
```
