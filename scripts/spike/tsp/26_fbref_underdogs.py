"""Scrap FBref stats for the 8 WC2026 underdogs not covered by StatsBomb.

Strategy:
  1. Visit country page /en/country/{CODE}/{Country}-Football
  2. Find "View entire squad history" link -> extract team_id
  3. Visit main stats page /en/squads/{team_id}/{Country}-Men-Stats
  4. Parse "Standard Stats" + "Goalkeeping" tables (and any xG-bearing tables)
  5. Save raw HTML + parsed JSON sidecar to data/cache/tsp/profiles_fbref/

Uses patchright (Cloudflare-bypass Playwright) with persistent profile.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from patchright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "data" / "cache" / "tsp" / "profiles_fbref"
RAW_HTML_DIR = OUT_DIR / "raw_html"
PROFILE_DIR = Path("/tmp/patchright_profile_fbref")

TARGETS = {
    "Bosnia and Herzegovina": "BIH",
    "Curaçao": "CUW",
    "Haiti": "HAI",
    "Iraq": "IRQ",
    "Jordan": "JOR",
    "New Zealand": "NZL",
    "Norway": "NOR",
    "Uzbekistan": "UZB",
}


def wait_for_clear(page, max_wait_s: int = 30) -> bool:
    """Wait for Cloudflare challenge to clear; return True if cleared."""
    for _ in range(max_wait_s):
        time.sleep(1)
        ct = page.content()
        if "Just a moment" not in ct and "Un momento" not in ct:
            return True
    return False


def discover_team_id(page, code: str, country_slug: str) -> tuple[str | None, str | None]:
    """From country page, find squad history link and extract team_id."""
    url = f"https://fbref.com/en/country/{code}/{country_slug}-Football"
    print(f"    → {url}")
    page.goto(url, timeout=60000, wait_until="load")
    if not wait_for_clear(page):
        return None, None

    links = page.query_selector_all("a")
    for ln in links:
        href = ln.get_attribute("href") or ""
        m = re.match(r"^/en/squads/([0-9a-f]+)/history/(.+?)-Men-Stats-and-History$", href)
        if m:
            tid = m.group(1)
            slug = m.group(2)
            return tid, slug
    return None, None


def scrap_team_stats(page, team_id: str, slug: str) -> dict:
    """Visit main stats page and extract tables."""
    url = f"https://fbref.com/en/squads/{team_id}/{slug}-Men-Stats"
    print(f"    → {url}")
    page.goto(url, timeout=60000, wait_until="load")
    if not wait_for_clear(page):
        return {"error": "cloudflare_block"}

    html = page.content()
    # Save raw
    RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_HTML_DIR / f"{team_id}_stats.html").write_text(html)

    # Extract main tables by id (FBref convention: stats_squads_*, etc.)
    tables = page.query_selector_all("table")
    parsed_tables: dict[str, dict] = {}
    for t in tables:
        table_id = t.get_attribute("id") or ""
        if not table_id:
            continue
        # Skip player-level tables; we want squad summaries
        if "squads" in table_id or "summary" in table_id or table_id.startswith("stats_"):
            # Grab headers + first row (squad totals usually first or last "vs Opponent" row)
            rows = t.query_selector_all("tr")
            if not rows:
                continue
            headers: list[str] = []
            header_row = t.query_selector("thead tr:last-child") or rows[0]
            for c in header_row.query_selector_all("th, td"):
                aria = c.get_attribute("aria-label") or c.inner_text()
                headers.append(aria.strip())
            data_rows: list[dict] = []
            for r in rows[1:]:
                cells = r.query_selector_all("th, td")
                if not cells:
                    continue
                row_data = {}
                for i, c in enumerate(cells):
                    if i >= len(headers):
                        break
                    text = c.inner_text().strip()
                    if text:
                        row_data[headers[i]] = text
                if row_data:
                    data_rows.append(row_data)
            parsed_tables[table_id] = {
                "headers": headers,
                "rows": data_rows[:20],  # cap to avoid bloat
            }

    return {
        "team_id": team_id,
        "slug": slug,
        "url": url,
        "n_tables_parsed": len(parsed_tables),
        "tables": parsed_tables,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)

    results: dict[str, dict] = {}
    failed: list[tuple[str, str]] = []

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chromium",
            headless=False,
            no_viewport=True,
        )
        page = context.pages[0] if context.pages else context.new_page()

        # Warm up to clear Cloudflare once for the whole session
        print("Warm-up navigation to fbref.com...")
        page.goto("https://fbref.com/en/", timeout=60000, wait_until="load")
        wait_for_clear(page)
        print("  Warm-up done.\n")

        for i, (team_name, code) in enumerate(TARGETS.items(), 1):
            slug = team_name.replace(" ", "-").replace("ç", "c").replace("'", "")
            slug = slug.replace("ã", "a")  # generic fallback
            print(f"\n[{i}/{len(TARGETS)}] {team_name} (code={code})")

            try:
                team_id, country_slug = discover_team_id(page, code, slug)
                if team_id is None:
                    failed.append((team_name, "no team_id found on country page"))
                    print(f"    ✗ team_id not found")
                    continue
                print(f"    team_id={team_id}, slug={country_slug}")

                stats = scrap_team_stats(page, team_id, country_slug)
                stats["team_name"] = team_name
                stats["fbref_country_code"] = code
                stats["scraped_at"] = datetime.now().isoformat()

                out_path = OUT_DIR / f"{team_name.replace(' ', '_').replace(chr(39), '').lower()}_fbref.json"
                out_path.write_text(json.dumps(stats, indent=2, ensure_ascii=False))
                n_tables = stats.get("n_tables_parsed", 0)
                print(f"    ✓ saved {out_path.name} ({n_tables} tables)")
                results[team_name] = {"team_id": team_id, "n_tables": n_tables}
            except Exception as exc:
                msg = f"{type(exc).__name__}: {exc}"
                failed.append((team_name, msg))
                print(f"    ✗ FAIL: {msg}")

            # Be polite
            time.sleep(3)

        context.close()

    print(f"\n=== Done. Profiled: {len(results)}/{len(TARGETS)} ===")
    if failed:
        print(f"\nFailed ({len(failed)}):")
        for n, e in failed:
            print(f"  {n}: {e}")

    diag = {
        "timestamp": datetime.now().isoformat(),
        "results": results,
        "failed": [{"team": n, "error": e} for n, e in failed],
    }
    (OUT_DIR / "_diagnostic.json").write_text(json.dumps(diag, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
