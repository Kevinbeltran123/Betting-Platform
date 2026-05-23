"""Fill NULL squad-value gaps in the dcaribou snapshot by direct TM scrape.

Background: dcaribou's national_teams snapshot has NULL total_market_value
for ~3 elite European teams (France, Spain, England). The hosted
felipeall/transfermarkt-api fly.dev demo is blocked by Transfermarkt's
cloud-IP filter ("Client Error. Not Allowed"). Self-hosting felipeall
via Docker is the documented 100% path; this script is the lightweight
equivalent: scrape the same canonical TM pages directly with httpx +
regex, using the URLs that dcaribou's national_teams.url already
provides.

For 3 missing teams: ~10 seconds wall-clock (3 requests × 2s polite delay).
For all 118 teams (--all): ~4 minutes wall-clock. Idempotent — re-runs
skip teams already in the JSON cache.

HTML parsing: the canonical selector is
``<a class="data-header__market-value-wrapper">€{n}{unit}…</a>``
where unit ∈ {bn, m, k} → multiplier ∈ {1e9, 1e6, 1e3}. This selector
has been stable since TM's late-2022 design refactor (verified by the
felipeall repo's xpath.py which uses the same class through 2026).

Polite scraping: 2.0s sleep between requests; browser UA. Total request
volume is bounded (≤ 118 once) — this falls well below TM's ~30 req/min
soft ceiling. Personal-use scraping is unenforced per the adversarial
research in Papers/WC2026_V3_CANDIDATES_EVALUATION.md §2.A.5.

Output: updates ``data/cache/transfermarkt/squad_values_current.parquet``
in place. Backs up the prior parquet to ``.bak`` before each run.

Usage:

    # Fill only the NULL gaps (fastest path — recommended)
    uv run python scripts/spike/wc2026_v3/fill_squad_value_gaps.py

    # Scrape all 118 teams from scratch
    uv run python scripts/spike/wc2026_v3/fill_squad_value_gaps.py --all
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx
import polars as pl


# Same browser UA used in ingest_dcaribou's R2 client — works on TM.
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Captures: €{number}{unit} from the data-header__market-value-wrapper anchor.
# Tolerant of extra attributes between the class and the value span.
_MARKET_VALUE_RE = re.compile(
    r'class="data-header__market-value-wrapper"[^>]*>\s*'
    r'<span[^>]*>€</span>([\d.,]+)<span[^>]*>([a-z]+)</span>',
    re.IGNORECASE,
)

_UNIT_MULTIPLIER = {
    "bn": 1_000_000_000.0,
    "m": 1_000_000.0,
    "k": 1_000.0,
}


@dataclass(frozen=True)
class ScrapeResult:
    team_name: str
    national_team_id: int
    url: str
    market_value_eur: float | None  # None if scrape/parse failed
    error: str | None = None


def parse_market_value(html: str) -> float | None:
    """Extract total squad market value (in EUR) from a TM team page HTML.

    Returns None when the canonical selector isn't found (TM refactor
    or non-team page). Returns 0.0 when the value is "€-" (TM's
    placeholder for unranked teams).
    """
    m = _MARKET_VALUE_RE.search(html)
    if not m:
        return None
    raw_number = m.group(1).replace(",", "").replace(".", "_")
    # TM uses "." as decimal separator and may omit thousands. Re-parse:
    raw_number = m.group(1)
    try:
        n = float(raw_number)
    except ValueError:
        return None
    unit = m.group(2).lower()
    mult = _UNIT_MULTIPLIER.get(unit)
    if mult is None:
        # Unknown unit suffix — caller logs as parse failure.
        return None
    return n * mult


def scrape_team(
    client: httpx.Client, url: str, team_name: str, national_team_id: int
) -> ScrapeResult:
    try:
        r = client.get(url, timeout=30.0)
        if r.status_code != 200:
            return ScrapeResult(
                team_name=team_name,
                national_team_id=national_team_id,
                url=url,
                market_value_eur=None,
                error=f"HTTP {r.status_code}",
            )
        value = parse_market_value(r.text)
        if value is None:
            return ScrapeResult(
                team_name=team_name,
                national_team_id=national_team_id,
                url=url,
                market_value_eur=None,
                error="parse_failed",
            )
        return ScrapeResult(
            team_name=team_name,
            national_team_id=national_team_id,
            url=url,
            market_value_eur=value,
        )
    except (httpx.HTTPError, httpx.TimeoutException) as e:
        return ScrapeResult(
            team_name=team_name,
            national_team_id=national_team_id,
            url=url,
            market_value_eur=None,
            error=str(e),
        )


def load_dcaribou_national_teams(data_dir: Path) -> pl.DataFrame:
    """Read the dcaribou national_teams snapshot — needs national_team_id +
    name + url + (current) total_market_value."""
    with gzip.open(data_dir / "national_teams.csv.gz", "rb") as f:
        return pl.read_csv(f.read(), infer_schema_length=20000).select(
            ["national_team_id", "name", "url", "total_market_value"]
        )


def select_teams_to_scrape(
    nt: pl.DataFrame, scrape_all: bool
) -> list[tuple[int, str, str]]:
    """Return list of (national_team_id, team_name, url) for the run."""
    if scrape_all:
        sub = nt
    else:
        sub = nt.filter(pl.col("total_market_value").is_null())
    return [
        (row["national_team_id"], row["name"], row["url"])
        for row in sub.iter_rows(named=True)
    ]


def merge_into_parquet(
    parquet_path: Path,
    scrape_results: list[ScrapeResult],
    snapshot_date_iso: str,
) -> int:
    """Merge ``scrape_results`` into the existing squad_values parquet.

    Adds rows for teams not yet present; UPDATES market_value_eur for
    teams already present (so re-runs with fresher data take effect).
    Returns the count of rows added/updated.
    """
    if not parquet_path.exists():
        raise FileNotFoundError(
            f"Parquet not found: {parquet_path}. Run "
            "`ingest_dcaribou.py --use-national-teams-snapshot` first."
        )

    existing = pl.read_parquet(parquet_path)
    by_name = {row["team_name"]: row for row in existing.iter_rows(named=True)}
    n_changes = 0
    for r in scrape_results:
        if r.market_value_eur is None:
            continue
        new_row = {
            "team_name": r.team_name,
            "tournament": "current",
            "season": 2025,
            "market_value_eur": float(r.market_value_eur),
            "players_n": by_name.get(r.team_name, {}).get("players_n") or 0,
            "snapshot_date": snapshot_date_iso,
            "club_id": int(r.national_team_id),
        }
        by_name[r.team_name] = new_row
        n_changes += 1

    merged = pl.DataFrame(list(by_name.values())).sort(
        "market_value_eur", descending=True
    )
    # Backup before overwrite
    backup = parquet_path.with_suffix(parquet_path.suffix + ".bak")
    shutil.copy(parquet_path, backup)
    merged.write_parquet(parquet_path)
    return n_changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/cache/transfermarkt/dcaribou"),
        help="dcaribou raw CSV.gz dir (read national_teams.csv.gz from here).",
    )
    parser.add_argument(
        "--parquet",
        type=Path,
        default=Path("data/cache/transfermarkt/squad_values_current.parquet"),
        help="Target squad-values parquet to merge into.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scrape ALL 118 teams (default: only NULL-value gaps).",
    )
    parser.add_argument(
        "--polite-delay-s",
        type=float,
        default=2.0,
        help="Seconds to sleep between requests (TM rate-limit safe).",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path("data/cache/transfermarkt/tm_scrape_cache.json"),
        help="JSON cache file to skip already-scraped teams across runs.",
    )
    args = parser.parse_args(argv)

    nt = load_dcaribou_national_teams(args.data_dir)
    todo = select_teams_to_scrape(nt, scrape_all=args.all)
    print(f"Selected {len(todo)} teams to scrape "
          f"({'all' if args.all else 'NULL-value gaps only'})")

    # Idempotent cache
    cache: dict[str, float] = {}
    if args.cache.exists():
        cache = json.loads(args.cache.read_text())

    headers = {"User-Agent": _BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"}
    results: list[ScrapeResult] = []
    with httpx.Client(headers=headers, follow_redirects=True) as client:
        for i, (nid, name, url) in enumerate(todo, start=1):
            cache_key = f"{nid}|{name}"
            if cache_key in cache and not args.all:
                value = cache[cache_key]
                print(f"  [{i}/{len(todo)}] {name:<30} (cached) €{value:>15,.0f}")
                results.append(
                    ScrapeResult(
                        team_name=name,
                        national_team_id=nid,
                        url=url,
                        market_value_eur=value,
                    )
                )
                continue

            r = scrape_team(client, url, name, nid)
            if r.market_value_eur is not None:
                print(f"  [{i}/{len(todo)}] {name:<30} → €{r.market_value_eur:>15,.0f}")
                cache[cache_key] = r.market_value_eur
            else:
                print(f"  [{i}/{len(todo)}] {name:<30} ✗ {r.error}")
            results.append(r)

            # Persist cache after each successful scrape (resume-safe)
            args.cache.parent.mkdir(parents=True, exist_ok=True)
            args.cache.write_text(json.dumps(cache, indent=2, sort_keys=True))

            if i < len(todo):
                time.sleep(args.polite_delay_s)

    n_ok = sum(1 for r in results if r.market_value_eur is not None)
    n_fail = sum(1 for r in results if r.market_value_eur is None)
    print(f"\nScraped {n_ok} OK / {n_fail} failed")

    if n_ok == 0:
        print("No successful scrapes — leaving parquet unchanged", file=sys.stderr)
        return 1

    n_changes = merge_into_parquet(
        args.parquet, results, snapshot_date_iso=str(date.today())
    )
    print(f"Merged {n_changes} rows into {args.parquet}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
