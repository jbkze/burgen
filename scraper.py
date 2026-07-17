#!/usr/bin/env python3
"""Scrapes castle data from ebidat.de (German castles only)."""

import json
import re
import time
import sys
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
HEADERS = {"User-Agent": "BurgenScraper/1.0 (educational project)"}
DELAY = 1.0


def get_session_and_first_ids():
    """Hit the search page, extract session file and first 10 castle IDs."""
    r = requests.get(SEARCH_URL, headers=HEADERS)
    # ebidat.de serves ISO-8859-1 (declared in meta charset); let bs4 detect it from the bytes
    soup = BeautifulSoup(r.content, "html.parser")

    form = soup.find("form", {"name": "formseite2"})
    session_file = form.find("input", {"name": "var_datei_selektionen"})["value"]

    ids = extract_ids(soup)
    return session_file, ids


def get_page_ids(session_file, offset):
    """Fetch a listing page by offset and extract castle IDs."""
    params = {
        "var_hauptpfad": "../r30/vc_shop/",
        "var_datei_selektionen": session_file,
        "var_anzahl_angezeigte_saetze": str(offset),
        "var_html_folgemaske": "r30msvcshop_anzeige.html",
    }
    r = requests.get(PAGE_URL, params=params, headers=HEADERS)
    soup = BeautifulSoup(r.content, "html.parser")
    return extract_ids(soup)


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
    r = requests.get(DETAIL_URL.format(castle_id), headers=HEADERS)
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

    r2 = requests.get(HAUPT_URL.format(castle_id), headers=HEADERS)
    soup2 = BeautifulSoup(r2.content, "html.parser")

    meta = {}
    coords = None
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


def main():
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    DATA_DIR.mkdir(exist_ok=True)

    print(f"Collecting castle IDs (target: {target})...")
    session_file, all_ids = get_session_and_first_ids()
    print(f"  Page 1: {len(all_ids)} IDs")

    offset = 10
    while len(all_ids) < target:
        time.sleep(DELAY)
        new_ids = get_page_ids(session_file, offset)
        if not new_ids:
            print(f"  No more results at offset {offset}")
            break
        all_ids.extend(new_ids)
        print(f"  Offset {offset}: +{len(new_ids)} IDs (total: {len(all_ids)})")
        offset += 10

    all_ids = all_ids[:target]
    print(f"\nScraping {len(all_ids)} castles...")

    castles = []
    for i, cid in enumerate(all_ids):
        print(f"  [{i+1}/{len(all_ids)}] ID {cid}...", end=" ", flush=True)
        try:
            castle = scrape_detail(cid)
            castles.append(castle)
            print(castle["name"])
        except Exception as e:
            print(f"ERROR: {e}")
        time.sleep(DELAY)

    out = DATA_DIR / "castles.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(castles, f, ensure_ascii=False, indent=2)

    print(f"\nDone! {len(castles)} castles saved to {out}")


if __name__ == "__main__":
    main()
