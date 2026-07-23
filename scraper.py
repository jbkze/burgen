#!/usr/bin/env python3
"""Scrapes castle data from ebidat.de (German castles only).

Resume-capable full scrape:
  python scraper.py            # scrape ALL castles (~8800, takes a while)
  python scraper.py --limit N  # scrape only the first N castles

Progress is checkpointed per castle in data/castles.jsonl (one JSON object
per line, errors recorded as {"id": ..., "error": ...}); re-running skips
everything already scraped. Collected IDs are cached in data/ids.json.

ebidat.de serves ISO-8859-1 (declared in the meta charset); responses are
parsed from bytes with BeautifulSoup so the charset is honored — never
force r.encoding.
"""

import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.ebidat.de"
SEARCH_URL = f"{BASE}/cgi-bin/ebidat.pl?a=a&te53=1"
PAGE_URL = f"{BASE}/cgi-bin/r30msvcshop_anzeige.pl"
DETAIL_URL = f"{BASE}/cgi-bin/ebidat.pl?id={{}}"
HAUPT_URL = f"{BASE}/cgi-bin/ebidat.pl?m=h&id={{}}"
DATA_DIR = Path(__file__).parent / "data"
IDS_FILE = DATA_DIR / "ids.json"
OUT_FILE = DATA_DIR / "castles.jsonl"
HEADERS = {"User-Agent": "BurgenScraper/1.0 (educational project)"}
DELAY = 0.25
WORKERS = 3

_tls = threading.local()
_write_lock = threading.Lock()


def http():
    if not hasattr(_tls, "session"):
        _tls.session = requests.Session()
        _tls.session.headers.update(HEADERS)
    return _tls.session


def get_session_and_first_ids():
    """Hit the search page, extract session file and first 10 castle IDs."""
    r = http().get(SEARCH_URL, timeout=30)
    soup = BeautifulSoup(r.content, "html.parser")

    form = soup.find("form", {"name": "formseite2"})
    session_file = form.find("input", {"name": "var_datei_selektionen"})["value"]

    total = None
    label = soup.find("section", class_="ergebnis")
    if label:
        m = re.search(r"Ergebnis:\s*(\d+)", label.get_text())
        if m:
            total = int(m.group(1))
    return session_file, extract_ids(soup), total


def get_page_ids(session_file, offset):
    """Fetch a listing page by offset and extract castle IDs."""
    params = {
        "var_hauptpfad": "../r30/vc_shop/",
        "var_datei_selektionen": session_file,
        "var_anzahl_angezeigte_saetze": str(offset),
        "var_html_folgemaske": "r30msvcshop_anzeige.html",
    }
    r = http().get(PAGE_URL, params=params, timeout=30)
    return extract_ids(BeautifulSoup(r.content, "html.parser"))


def extract_ids(soup):
    """Extract castle IDs from a listing page."""
    ids = []
    for a in soup.find_all("a", href=re.compile(r"ebidat\.pl\?id=\d+")):
        m = re.search(r"id=(\d+)", a["href"])
        if m:
            castle_id = int(m.group(1))
            if castle_id not in ids:
                ids.append(castle_id)
    return ids


def scrape_detail(castle_id):
    """Scrape the detail + Hauptdaten pages for a single castle."""
    r = http().get(DETAIL_URL.format(castle_id), timeout=30)
    soup = BeautifulSoup(r.content, "html.parser")

    data = {"id": castle_id, "url": DETAIL_URL.format(castle_id)}

    h2 = soup.find("h2")
    data["name"] = h2.get_text(strip=True) if h2 else ""

    sections = {}
    for h3 in soup.find_all("h3"):
        key = h3.get_text(strip=True).rstrip(":")
        paragraphs = []
        for sib in h3.next_siblings:
            if sib.name == "h3":
                break
            if sib.name == "p":
                paragraphs.append(sib.get_text(strip=True))
        if paragraphs:
            sections[key] = "\n\n".join(paragraphs)
    data["sections"] = sections

    images = []
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "bilder/firma451" in src:
            full_url = urljoin(r.url, src)
            large_url = full_url.replace("_18_", "_101_").replace("_19_", "_103_").replace("_20_", "_105_")
            images.append({
                "thumb": full_url,
                "large": large_url,
                "alt": img.get("alt", ""),
                "title": img.get("title", ""),
            })
    data["images"] = images

    time.sleep(DELAY)

    r2 = http().get(HAUPT_URL.format(castle_id), timeout=30)
    soup2 = BeautifulSoup(r2.content, "html.parser")

    meta = {}
    for li in soup2.find_all("li", class_="daten"):
        key_div = li.find("div", class_="gruppe")
        val_div = li.find("div", class_="gruppenergebnis")
        if key_div and val_div:
            key = key_div.get_text(strip=True).rstrip(":")
            val = val_div.get_text(strip=True)
            if val:
                meta[key] = val
    data["meta"] = meta

    maps_link = soup2.find("a", href=re.compile(r"maps\.google\.com"))
    if maps_link:
        m = re.search(r"q=([\d.]+),([\d.]+)", maps_link["href"])
        if m:
            data["lat"] = float(m.group(1))
            data["lon"] = float(m.group(2))

    return data


def collect_ids(target=None):
    """Collect all castle IDs from the paginated search (cached in ids.json)."""
    if IDS_FILE.exists():
        ids = json.loads(IDS_FILE.read_text())
        print(f"IDs aus Cache: {len(ids)}")
        return ids if target is None else ids[:target]

    print("Sammle Burgen-IDs...")
    session_file, ids, total = get_session_and_first_ids()
    total = total or 10**9
    print(f"  EBIDAT meldet {total} Treffer")
    seen = set(ids)
    offset = 10
    while len(ids) < (target or total):
        time.sleep(0.15)
        try:
            page = get_page_ids(session_file, offset)
        except Exception as e:
            print(f"  Offset {offset}: Fehler {e}, retry...")
            time.sleep(3)
            continue
        if not page:
            break
        fresh = [i for i in page if i not in seen]
        ids.extend(fresh)
        seen.update(fresh)
        if offset % 500 == 0:
            print(f"  ... {len(ids)} IDs (Offset {offset})", flush=True)
        offset += 10
    DATA_DIR.mkdir(exist_ok=True)
    IDS_FILE.write_text(json.dumps(ids))
    print(f"  Fertig: {len(ids)} IDs gesammelt")
    return ids if target is None else ids[:target]


def load_done():
    done = set()
    if OUT_FILE.exists():
        with open(OUT_FILE, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["id"])
                except Exception:
                    pass
    return done


def worker(cid, stats):
    for attempt in (1, 2, 3):
        try:
            data = scrape_detail(cid)
            break
        except Exception as e:
            if attempt == 3:
                data = {"id": cid, "error": str(e)[:200]}
            else:
                time.sleep(2 * attempt)
    with _write_lock:
        with open(OUT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
        stats["done"] += 1
        if "error" in data:
            stats["errors"] += 1
        if stats["done"] % 100 == 0:
            rate = stats["done"] / max(1, time.time() - stats["t0"])
            remaining = (stats["total"] - stats["done"]) / max(rate, 0.01)
            print(f"  {stats['done']}/{stats['total']} ({stats['errors']} Fehler, "
                  f"{rate:.1f}/s, ~{remaining/60:.0f} min verbleibend)", flush=True)
    time.sleep(DELAY)


def main():
    target = None
    if "--limit" in sys.argv:
        target = int(sys.argv[sys.argv.index("--limit") + 1])

    DATA_DIR.mkdir(exist_ok=True)
    ids = collect_ids(target)
    done = load_done()
    todo = [i for i in ids if i not in done]
    print(f"{len(ids)} IDs, {len(done)} bereits gescraped, {len(todo)} offen")
    if not todo:
        print("Nichts zu tun.")
        return

    stats = {"done": 0, "errors": 0, "total": len(todo), "t0": time.time()}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for cid in todo:
            ex.submit(worker, cid, stats)

    print(f"\nFertig! {stats['done']} gescraped, {stats['errors']} Fehler. -> {OUT_FILE}")


if __name__ == "__main__":
    main()
