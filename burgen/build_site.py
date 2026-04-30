#!/usr/bin/env python3
"""Builds a static website from scraped castle data."""

import json
import html
from pathlib import Path

DATA = Path(__file__).parent / "data" / "castles.json"
OUT = Path(__file__).parent / "site"


def h(text):
    return html.escape(text)


def build_entry(castle, featured=False):
    name = h(castle["name"])
    cid = castle["id"]
    meta = castle.get("meta", {})
    bundesland = h(meta.get("Bundesland", ""))
    kreis = h(meta.get("Kreis", ""))
    typ = h(meta.get("Typ", ""))
    klassifizierung = h(meta.get("Klassifizierung", ""))
    kurzansprache = h(meta.get("Kurzansprache", ""))
    datierung = h(meta.get("Datierung-Beginn", ""))
    erhaltung = h(meta.get("Erhaltung - Heutiger Zustand", ""))

    img_html = ""
    if castle.get("images"):
        img = castle["images"][0]
        img_html = f'<img src="{h(img["thumb"])}" alt="{h(img.get("alt", name))}" loading="lazy">'

    location = ", ".join(p for p in [kreis, bundesland] if p)

    tags = [t for t in [typ, klassifizierung, datierung] if t]
    tags_html = "".join(f'<span class="tag">{t}</span>' for t in tags)

    if featured:
        return f"""
    <article class="entry entry--featured" data-id="{cid}" data-name="{name.lower()}" data-state="{bundesland.lower()}" role="button" tabindex="0">
      <div class="entry__img">{img_html if img_html else ""}</div>
      <div class="entry__body">
        <p class="entry__location">{location}</p>
        <h3 class="entry__name entry__name--lg">{name}</h3>
        <p class="entry__teaser">{kurzansprache[:220]}{"..." if len(kurzansprache) > 220 else ""}</p>
        <div class="entry__tags">{tags_html}</div>
      </div>
    </article>"""
    else:
        return f"""
    <article class="entry entry--compact" data-id="{cid}" data-name="{name.lower()}" data-state="{bundesland.lower()}" role="button" tabindex="0">
      {"<div class='entry__thumb'>" + img_html + "</div>" if img_html else ""}
      <div class="entry__body">
        <p class="entry__location">{location}</p>
        <h3 class="entry__name">{name}</h3>
        <p class="entry__meta-line">{" · ".join(tags[:2])}</p>
      </div>
    </article>"""


def build_detail(castle):
    name = h(castle["name"])
    cid = castle["id"]
    meta = castle.get("meta", {})
    sections = castle.get("sections", {})

    meta_items = ""
    for key in ["Bundesland", "Kreis", "Stadt / Gemeinde", "Typ", "Klassifizierung",
                 "Höhenlage", "Datierung-Beginn", "Datierung-Ende",
                 "Erhaltung - Heutiger Zustand"]:
        val = meta.get(key)
        if val:
            meta_items += f'<dt>{h(key)}</dt><dd>{h(val)}</dd>'

    sections_html = ""
    for title in ["Geschichte", "Bauentwicklung", "Baubeschreibung", "Arch-Untersuchung/Funde"]:
        text = sections.get(title)
        if text:
            paragraphs = "".join(f"<p>{h(p)}</p>" for p in text.split("\n\n"))
            sections_html += f'<section class="detail__section"><h3>{h(title)}</h3>{paragraphs}</section>'

    images_html = ""
    if castle.get("images"):
        imgs = "".join(
            f'<a href="{h(img["large"])}" target="_blank" rel="noopener"><img src="{h(img["thumb"])}" alt="{h(img.get("alt", ""))}" loading="lazy"></a>'
            for img in castle["images"]
        )
        images_html = f'<div class="detail__gallery">{imgs}</div>'

    map_html = ""
    if "lat" in castle:
        map_html = f'<div class="detail__map" data-lat="{castle["lat"]}" data-lon="{castle["lon"]}"></div>'

    location = ", ".join(p for p in [
        meta.get("Stadt / Gemeinde", ""),
        meta.get("Kreis", ""),
        meta.get("Bundesland", "")
    ] if p)
    kurzansprache = h(meta.get("Kurzansprache", ""))
    erhaltung_kommentar = h(meta.get("Erhaltung - Kommentar", ""))

    return f"""
    <div class="detail" id="detail-{cid}">
      <nav class="detail__nav">
        <button class="detail__back" onclick="closeDetail()">&larr; Alle Burgen</button>
      </nav>
      <header class="detail__header">
        <p class="detail__location">{h(location)}</p>
        <h2 class="detail__title">{name}</h2>
        <p class="detail__lead">{kurzansprache}</p>
      </header>
      {images_html}
      <div class="detail__content">
        <div class="detail__main">
          {sections_html}
        </div>
        <aside class="detail__sidebar">
          {map_html}
          <dl class="detail__meta">{meta_items}</dl>
          <a class="detail__source" href="{h(castle['url'])}" target="_blank" rel="noopener">Quelle: EBIDAT &nearr;</a>
        </aside>
      </div>
    </div>"""


def build_index(castles):
    states = sorted(set(
        c.get("meta", {}).get("Bundesland", "")
        for c in castles if c.get("meta", {}).get("Bundesland")
    ))
    state_options = "".join(f'<option value="{h(s.lower())}">{h(s)}</option>' for s in states)

    castles_with_images = [c for c in castles if c.get("images")]
    castles_without_images = [c for c in castles if not c.get("images")]
    ordered = castles_with_images + castles_without_images

    entries_html = ""
    for i, c in enumerate(ordered):
        featured = (i % 5 == 0) and c.get("images")
        entries_html += build_entry(c, featured=featured)

    details = "\n".join(build_detail(c) for c in castles)

    castles_with_coords = [c for c in castles if "lat" in c]
    markers_js = json.dumps([
        {"id": c["id"], "name": c["name"], "lat": c["lat"], "lon": c["lon"],
         "state": c.get("meta", {}).get("Bundesland", ""),
         "type": c.get("meta", {}).get("Klassifizierung", "")}
        for c in castles_with_coords
    ], ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Burgen in Deutschland</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,700;12..96,800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
:root {{
  --bg: oklch(97% 0.006 55);
  --surface: oklch(100% 0.003 55);
  --accent: oklch(52% 0.14 28);
  --accent-light: oklch(92% 0.04 28);
  --accent-hover: oklch(45% 0.16 28);
  --text: oklch(18% 0.01 55);
  --text-secondary: oklch(42% 0.02 55);
  --text-tertiary: oklch(58% 0.015 55);
  --border: oklch(88% 0.01 55);
  --border-light: oklch(93% 0.005 55);
  --shadow: oklch(50% 0.02 55 / 0.08);

  --font-display: 'Bricolage Grotesque', system-ui, sans-serif;
  --font-body: system-ui, -apple-system, 'Segoe UI', sans-serif;

  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 48px;
  --space-2xl: 64px;
  --space-3xl: 96px;

  --max-w: 1120px;
}}

@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{ animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }}
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
  font-family: var(--font-body);
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}}

/* --- MAP HERO --- */

.hero {{
  position: relative;
  background: var(--surface);
}}

.hero__map {{
  height: clamp(320px, 50vh, 560px);
  width: 100%;
}}

.hero__overlay {{
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: var(--space-xl) var(--space-lg) var(--space-lg);
  background: linear-gradient(to top, var(--surface) 20%, oklch(100% 0 0 / 0));
  pointer-events: none;
}}

.hero__title {{
  font-family: var(--font-display);
  font-weight: 800;
  font-size: clamp(2rem, 5vw + 0.5rem, 3.5rem);
  line-height: 1.1;
  letter-spacing: -0.02em;
  text-wrap: balance;
  color: var(--text);
}}

.hero__title span {{
  color: var(--accent);
}}

.hero__subtitle {{
  font-size: 1rem;
  color: var(--text-secondary);
  margin-top: var(--space-sm);
}}

/* --- CONTROLS --- */

.controls {{
  max-width: var(--max-w);
  margin: 0 auto;
  padding: var(--space-lg) var(--space-lg) 0;
  display: flex;
  gap: var(--space-md);
  flex-wrap: wrap;
  align-items: center;
}}

.controls__search {{
  flex: 1;
  min-width: 200px;
  padding: 0.65rem 1rem;
  font-size: 1rem;
  border: 1.5px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text);
  font-family: var(--font-body);
  transition: border-color 0.15s ease-out;
}}

.controls__search:focus {{
  outline: none;
  border-color: var(--accent);
}}

.controls__search::placeholder {{
  color: var(--text-tertiary);
}}

.controls__select {{
  padding: 0.65rem 1rem;
  font-size: 0.9rem;
  border: 1.5px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text);
  font-family: var(--font-body);
  cursor: pointer;
  transition: border-color 0.15s ease-out;
}}

.controls__select:focus {{
  outline: none;
  border-color: var(--accent);
}}

.controls__count {{
  font-size: 0.875rem;
  color: var(--text-tertiary);
  margin-left: auto;
}}

/* --- ENTRIES STREAM --- */

.stream {{
  max-width: var(--max-w);
  margin: 0 auto;
  padding: var(--space-lg);
}}

/* Featured entry: image left, text right */
.entry--featured {{
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: var(--space-lg);
  padding: var(--space-xl) 0;
  border-bottom: 1px solid var(--border-light);
  cursor: pointer;
  transition: opacity 0.15s ease-out;
}}

.entry--featured:hover {{ opacity: 0.85; }}

.entry--featured .entry__img {{
  border-radius: 6px;
  overflow: hidden;
  aspect-ratio: 4 / 3;
  background: var(--border-light);
}}

.entry--featured .entry__img img {{
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}}

.entry--featured .entry__body {{
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: var(--space-sm);
}}

.entry__name--lg {{
  font-family: var(--font-display);
  font-weight: 800;
  font-size: clamp(1.5rem, 2.5vw + 0.5rem, 2rem);
  line-height: 1.15;
  letter-spacing: -0.01em;
  color: var(--text);
}}

.entry__teaser {{
  font-size: 0.95rem;
  color: var(--text-secondary);
  line-height: 1.65;
  max-width: 48ch;
}}

/* Compact entry: small thumb + text in a row */
.entry--compact {{
  display: flex;
  gap: var(--space-md);
  align-items: center;
  padding: var(--space-md) 0;
  border-bottom: 1px solid var(--border-light);
  cursor: pointer;
  transition: opacity 0.15s ease-out;
}}

.entry--compact:hover {{ opacity: 0.75; }}

.entry__thumb {{
  width: 80px;
  height: 60px;
  border-radius: 4px;
  overflow: hidden;
  flex-shrink: 0;
  background: var(--border-light);
}}

.entry__thumb img {{
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}}

.entry--compact .entry__body {{
  min-width: 0;
}}

.entry__name {{
  font-family: var(--font-display);
  font-weight: 700;
  font-size: 1.05rem;
  line-height: 1.3;
  color: var(--text);
}}

.entry__location {{
  font-size: 0.75rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--accent);
  font-weight: 700;
}}

.entry__meta-line {{
  font-size: 0.8rem;
  color: var(--text-tertiary);
}}

.entry__tags {{
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
  margin-top: var(--space-xs);
}}

.tag {{
  background: var(--accent-light);
  color: var(--accent);
  padding: 2px 10px;
  border-radius: 99px;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.02em;
}}

.no-results {{
  text-align: center;
  padding: var(--space-2xl) var(--space-lg);
  color: var(--text-tertiary);
  font-size: 1.1rem;
  display: none;
}}

/* --- DETAIL VIEW --- */

.detail-view {{ display: none; }}
.detail-view.active {{ display: block; }}
.grid-view.hidden {{ display: none; }}

.detail__nav {{
  max-width: var(--max-w);
  margin: 0 auto;
  padding: var(--space-md) var(--space-lg);
}}

.detail__back {{
  background: none;
  border: 1.5px solid var(--border);
  color: var(--text);
  padding: 0.4rem 0.9rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.875rem;
  font-family: var(--font-body);
  transition: border-color 0.15s ease-out;
}}

.detail__back:hover {{ border-color: var(--accent); color: var(--accent); }}

.detail__header {{
  max-width: var(--max-w);
  margin: 0 auto;
  padding: var(--space-xl) var(--space-lg) var(--space-lg);
}}

.detail__location {{
  font-size: 0.8rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--accent);
  font-weight: 700;
  margin-bottom: var(--space-sm);
}}

.detail__title {{
  font-family: var(--font-display);
  font-weight: 800;
  font-size: clamp(2rem, 4vw + 0.5rem, 3rem);
  line-height: 1.1;
  letter-spacing: -0.02em;
  color: var(--text);
  text-wrap: balance;
}}

.detail__lead {{
  font-size: 1.1rem;
  color: var(--text-secondary);
  margin-top: var(--space-md);
  max-width: 65ch;
  line-height: 1.7;
}}

.detail__gallery {{
  max-width: var(--max-w);
  margin: 0 auto;
  padding: 0 var(--space-lg);
  display: flex;
  gap: var(--space-md);
  overflow-x: auto;
  padding-bottom: var(--space-sm);
  scrollbar-width: thin;
}}

.detail__gallery a {{ flex-shrink: 0; }}

.detail__gallery img {{
  height: 280px;
  border-radius: 6px;
  display: block;
}}

.detail__content {{
  max-width: var(--max-w);
  margin: 0 auto;
  padding: var(--space-xl) var(--space-lg);
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: var(--space-2xl);
}}

.detail__section h3 {{
  font-family: var(--font-display);
  font-weight: 700;
  font-size: 1.25rem;
  color: var(--text);
  margin-bottom: var(--space-md);
  padding-bottom: var(--space-sm);
  border-bottom: 2px solid var(--accent);
  display: inline-block;
}}

.detail__section p {{
  color: var(--text-secondary);
  line-height: 1.75;
  max-width: 65ch;
  margin-bottom: var(--space-md);
}}

.detail__section + .detail__section {{
  margin-top: var(--space-xl);
}}

.detail__map {{
  height: 220px;
  border-radius: 8px;
  margin-bottom: var(--space-lg);
  border: 1px solid var(--border);
}}

.detail__meta {{
  font-size: 0.85rem;
  line-height: 1.8;
}}

.detail__meta dt {{
  color: var(--text-tertiary);
  font-size: 0.75rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  margin-top: var(--space-md);
}}

.detail__meta dt:first-child {{ margin-top: 0; }}

.detail__meta dd {{
  color: var(--text);
  font-weight: 500;
}}

.detail__source {{
  display: inline-block;
  margin-top: var(--space-lg);
  color: var(--accent);
  font-size: 0.8rem;
  font-weight: 600;
  text-decoration: none;
}}

.detail__source:hover {{ text-decoration: underline; }}

/* --- RESPONSIVE --- */

@media (max-width: 768px) {{
  .entry--featured {{
    grid-template-columns: 1fr;
    gap: var(--space-md);
    padding: var(--space-lg) 0;
  }}

  .detail__content {{
    grid-template-columns: 1fr;
    gap: var(--space-xl);
  }}

  .detail__gallery img {{
    height: 200px;
  }}
}}

@media (max-width: 480px) {{
  .controls {{
    flex-direction: column;
  }}

  .controls__count {{
    margin-left: 0;
  }}

  .hero__map {{
    height: 280px;
  }}
}}

/* Leaflet popup override */
.leaflet-popup-content-wrapper {{
  border-radius: 6px;
  font-family: var(--font-display);
  font-weight: 700;
}}
</style>
</head>
<body>

<div class="grid-view">
  <div class="hero">
    <div class="hero__map" id="map"></div>
    <div class="hero__overlay">
      <h1 class="hero__title">Burgen in <span>Deutschland</span></h1>
      <p class="hero__subtitle">{len(castles)} Burgen aus der EBIDAT-Datenbank</p>
    </div>
  </div>

  <div class="controls">
    <input class="controls__search" type="text" id="search" placeholder="Burg suchen...">
    <select class="controls__select" id="state-filter">
      <option value="">Alle Bundesländer</option>
      {state_options}
    </select>
    <span class="controls__count"><span id="count">{len(castles)}</span> Burgen</span>
  </div>

  <div class="stream" id="stream">
    {entries_html}
  </div>

  <p class="no-results" id="no-results">Keine Burgen gefunden.</p>
</div>

<div class="detail-view" id="detail-view">
  {details}
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const markers = {markers_js};
let map;

(function initMap() {{
  map = L.map('map', {{ zoomControl: false }}).setView([51.0, 10.4], 6);
  L.control.zoom({{ position: 'topright' }}).addTo(map);
  L.tileLayer('https://{{s}}.basemaps.cartocdn.com/voyager/{{z}}/{{x}}/{{y}}@2x.png', {{
    attribution: '&copy; OSM &copy; CARTO',
    maxZoom: 18
  }}).addTo(map);

  const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();

  markers.forEach(m => {{
    const marker = L.circleMarker([m.lat, m.lon], {{
      radius: 5,
      fillColor: '#b54b2a',
      color: '#fff',
      weight: 1.5,
      fillOpacity: 0.9
    }});
    marker.bindPopup(`<b>${{m.name}}</b><br><small>${{m.state}}</small>`);
    marker.on('click', () => openDetail(m.id));
    marker.addTo(map);
  }});
}})();

function openDetail(id) {{
  document.querySelector('.grid-view').classList.add('hidden');
  const dv = document.getElementById('detail-view');
  dv.classList.add('active');
  dv.querySelectorAll('.detail').forEach(d => d.style.display = 'none');
  const detail = document.getElementById('detail-' + id);
  if (detail) {{
    detail.style.display = 'block';
    const mapDiv = detail.querySelector('.detail__map');
    if (mapDiv && !mapDiv._init) {{
      const lat = parseFloat(mapDiv.dataset.lat);
      const lon = parseFloat(mapDiv.dataset.lon);
      const dm = L.map(mapDiv, {{ zoomControl: false }}).setView([lat, lon], 13);
      L.tileLayer('https://{{s}}.basemaps.cartocdn.com/voyager/{{z}}/{{x}}/{{y}}@2x.png', {{
        attribution: '&copy; OSM', maxZoom: 18
      }}).addTo(dm);
      L.circleMarker([lat, lon], {{
        radius: 8, fillColor: '#b54b2a', color: '#fff', weight: 2, fillOpacity: 1
      }}).addTo(dm);
      mapDiv._init = true;
    }}
  }}
  window.scrollTo({{ top: 0, behavior: 'instant' }});
}}

function closeDetail() {{
  document.querySelector('.grid-view').classList.remove('hidden');
  document.getElementById('detail-view').classList.remove('active');
}}

document.querySelectorAll('.entry--featured, .entry--compact').forEach(el => {{
  el.addEventListener('click', () => openDetail(el.dataset.id));
  el.addEventListener('keydown', e => {{ if (e.key === 'Enter') openDetail(el.dataset.id); }});
}});

const search = document.getElementById('search');
const stateFilter = document.getElementById('state-filter');
const stream = document.getElementById('stream');
const countEl = document.getElementById('count');
const noResults = document.getElementById('no-results');

function filter() {{
  const q = search.value.toLowerCase();
  const state = stateFilter.value;
  let visible = 0;
  stream.querySelectorAll('[data-id]').forEach(el => {{
    const matchName = el.dataset.name.includes(q);
    const matchState = !state || el.dataset.state === state;
    const show = matchName && matchState;
    el.style.display = show ? '' : 'none';
    if (show) visible++;
  }});
  countEl.textContent = visible;
  noResults.style.display = visible === 0 ? 'block' : 'none';
}}

search.addEventListener('input', filter);
stateFilter.addEventListener('change', filter);
</script>
</body>
</html>"""


def main():
    with open(DATA, encoding="utf-8") as f:
        castles = json.load(f)

    OUT.mkdir(exist_ok=True)
    index = OUT / "index.html"
    index.write_text(build_index(castles), encoding="utf-8")
    print(f"Built {index} with {len(castles)} castles")


if __name__ == "__main__":
    main()
