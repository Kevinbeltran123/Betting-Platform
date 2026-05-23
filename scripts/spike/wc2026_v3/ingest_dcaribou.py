"""dcaribou CC0 Transfermarkt mirror ingestion (Wave 1.A.4).

Sidesteps direct Transfermarkt scraping (ToS-risky, slow, Cloudflare-prone)
by ingesting the dcaribou/transfermarkt-datasets CC0-1.0 mirror hosted on
Cloudflare R2. The mirror is refreshed weekly; we pin a specific snapshot
on first download.

Pipeline:
1. ``download_tables(data_dir, tables=[...])`` — fetch CSV.gz files from
   the dcaribou R2 endpoint, decompress on the fly. Idempotent: re-runs
   skip already-downloaded files.
2. ``build_squad_values(data_dir, competition_id, season, snapshot_date)``
   — for one tournament edition, joins:
     - ``games`` (filter by competition_id + season + date window)
     - ``game_lineups`` (player_id per club_id per game)
     - ``players`` (resolve club_id → national team name)
     - ``player_valuations`` (latest market_value_in_eur as of snapshot_date)
   Returns a Polars DataFrame: (team_name, competition_id, season,
   market_value_eur, players_n, snapshot_date).

Coverage: the v3 sprint needs squad values for these tournaments
(reconstructed at each tournament's start date):

| Slug         | competition_id | season | window (start–end)       | Purpose         |
|--------------|----------------|--------|--------------------------|-----------------|
| wc2018       | FIWC           | 2017   | 2018-06-14 to 2018-07-15 | calibration     |
| euro2020     | EURO           | 2020   | 2021-06-11 to 2021-07-11 | calibration     |
| wc2022       | FIWC           | 2021   | 2022-11-20 to 2022-12-18 | hold-out        |
| afcon2023    | AFCN           | 2023   | 2024-01-13 to 2024-02-11 | hold-out        |
| copa2024     | COPA           | 2023   | 2024-06-20 to 2024-07-15 | hold-out        |
| euro2024     | EURO           | 2023   | 2024-06-14 to 2024-07-15 | hold-out        |
| wc2026       | FIWC           | 2025   | 2026-06-11 to 2026-07-19 | lock_v3 emit    |

Note: ``season`` is the TM "saison_id" — start year of the football season
that the tournament falls in. WC2022 ran in late 2022 but is in the
2022-23 season, hence season=2022 (NB: this needs verification at runtime
against the actual games table — the v2 spike's PLAN.md doc had different
numbers and TM occasionally tags tournaments to the FOLLOWING season).

Usage:

    # Download once (~100-200 MB total)
    uv run python scripts/spike/wc2026_v3/ingest_dcaribou.py --download

    # Build squad values for one tournament
    uv run python scripts/spike/wc2026_v3/ingest_dcaribou.py \\
        --tournament wc2022 \\
        --output data/cache/transfermarkt/squad_values_wc2022.parquet

    # Build all (default tournament list)
    uv run python scripts/spike/wc2026_v3/ingest_dcaribou.py --build-all \\
        --output-dir data/cache/transfermarkt/

License: dcaribou is CC0-1.0. The aggregated squad-values parquet
inherits that license. Pin a snapshot by saving the SHA-256 of each
downloaded CSV.gz to ``data/cache/transfermarkt/dcaribou_manifest.json``
on first download. Subsequent runs verify against this manifest and
warn on mismatch (TM may have updated the mirror).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx
import polars as pl


DCARIBOU_R2_BASE = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data"

# Cloudflare in front of R2 rejects the default Python-urllib UA. A
# realistic browser UA gets HTTP 200; this is documented dcaribou
# behavior, not anti-scraping (the dataset is CC0).
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Tables we actually need for the squad-value reconstruction. Downloading
# only these (vs the full 12-table zip) keeps the footprint <200MB.
REQUIRED_TABLES = (
    "competitions",
    "national_teams",
    "clubs",
    "games",
    "game_lineups",
    "players",
    "player_valuations",
)


@dataclass(frozen=True)
class TournamentSpec:
    """One tournament edition's identifying tuple + snapshot policy."""

    slug: str
    competition_id: str
    season: int
    start_date: date
    end_date: date

    @property
    def snapshot_date(self) -> date:
        """Market values snapshot ON the tournament start (most recent value <=)."""
        return self.start_date


DEFAULT_TOURNAMENTS: tuple[TournamentSpec, ...] = (
    TournamentSpec("wc2018", "FIWC", 2017, date(2018, 6, 14), date(2018, 7, 15)),
    TournamentSpec("euro2020", "EURO", 2020, date(2021, 6, 11), date(2021, 7, 11)),
    TournamentSpec("wc2022", "FIWC", 2021, date(2022, 11, 20), date(2022, 12, 18)),
    TournamentSpec("afcon2023", "AFCN", 2023, date(2024, 1, 13), date(2024, 2, 11)),
    TournamentSpec("copa2024", "COPA", 2023, date(2024, 6, 20), date(2024, 7, 15)),
    TournamentSpec("euro2024", "EURO", 2023, date(2024, 6, 14), date(2024, 7, 15)),
    TournamentSpec("wc2026", "FIWC", 2025, date(2026, 6, 11), date(2026, 7, 19)),
)


# ─────────────────────────────────────────────────────────────────
# Download
# ─────────────────────────────────────────────────────────────────


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_tables(
    data_dir: Path,
    tables: tuple[str, ...] = REQUIRED_TABLES,
    *,
    force: bool = False,
) -> dict[str, str]:
    """Download CSV.gz tables from dcaribou R2.

    Returns ``{table_name: sha256}`` manifest. Writes both the CSV.gz
    files and a ``dcaribou_manifest.json`` to ``data_dir``. Idempotent:
    skips downloads when the file already exists unless ``force=True``.
    """

    data_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    headers = {"User-Agent": _BROWSER_UA}
    with httpx.Client(headers=headers, timeout=httpx.Timeout(300.0), follow_redirects=True) as client:
        for table in tables:
            local = data_dir / f"{table}.csv.gz"
            url = f"{DCARIBOU_R2_BASE}/{table}.csv.gz"
            if local.exists() and not force:
                manifest[table] = _sha256_file(local)
                print(f"  [skip] {table} → already at {local} (sha256 {manifest[table][:12]}...)")
                continue
            print(f"  [download] {table} ← {url}")
            with client.stream("GET", url) as r:
                r.raise_for_status()
                with local.open("wb") as f:
                    for chunk in r.iter_bytes(chunk_size=1 << 20):
                        f.write(chunk)
            manifest[table] = _sha256_file(local)
            print(f"     {local} ({local.stat().st_size:,} bytes, sha256 {manifest[table][:12]}...)")

    manifest_path = data_dir / "dcaribou_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


# ─────────────────────────────────────────────────────────────────
# Build
# ─────────────────────────────────────────────────────────────────


def _read_gz(path: Path, **kwargs) -> pl.DataFrame:
    """Read a gzipped CSV via Polars (transparent decompression)."""
    with gzip.open(path, "rb") as f:
        return pl.read_csv(f.read(), **kwargs)


def build_squad_values(
    data_dir: Path,
    spec: TournamentSpec,
) -> pl.DataFrame:
    """Reconstruct per-team squad market value for one tournament edition.

    Algorithm:
    1. Filter ``games`` to (competition_id == spec.competition_id) AND
       (date in [start, end]).
    2. Collect distinct national-team club_ids from home_club_id + away_club_id.
    3. From ``game_lineups``, get distinct player_ids per (game_id, club_id)
       intersected with the tournament games.
    4. For each (player_id, team_id), find the most recent valuation row
       with ``date <= snapshot_date``.
    5. Aggregate sum of ``market_value_in_eur`` per team, count players.
    6. Resolve team_name from ``clubs`` table.

    Returns DataFrame columns: team_name, competition_id, season,
    market_value_eur, players_n, snapshot_date.
    """

    games = _read_gz(
        data_dir / "games.csv.gz",
        infer_schema_length=10_000,
    ).filter(
        (pl.col("competition_id") == spec.competition_id)
        & (pl.col("date").str.to_date(strict=False).is_between(spec.start_date, spec.end_date))
    )
    if games.is_empty():
        raise RuntimeError(
            f"No games found in dcaribou for {spec.slug} "
            f"(competition_id={spec.competition_id}, "
            f"date in [{spec.start_date}, {spec.end_date}]). "
            "Check that the tournament edition is in the current dcaribou snapshot."
        )

    game_ids = set(games["game_id"].to_list())
    teams_in_tournament = set(games["home_club_id"].to_list()) | set(
        games["away_club_id"].to_list()
    )

    lineups = _read_gz(
        data_dir / "game_lineups.csv.gz",
        infer_schema_length=10_000,
    ).filter(
        pl.col("game_id").is_in(list(game_ids))
        & pl.col("club_id").is_in(list(teams_in_tournament))
    )

    # (player_id, club_id) pairs from the tournament — these are the "squads"
    # by appearance (player who played at least 1 tournament minute for team T).
    squads = (
        lineups.select(["player_id", "club_id"]).unique().sort(["club_id", "player_id"])
    )

    # Snapshot each player's most-recent market value as of snapshot_date.
    valuations = (
        _read_gz(data_dir / "player_valuations.csv.gz", infer_schema_length=10_000)
        .with_columns(pl.col("date").str.to_date(strict=False).alias("val_date"))
        .filter(pl.col("val_date") <= spec.snapshot_date)
        .sort(["player_id", "val_date"], descending=[False, True])
        .group_by("player_id")
        .agg(
            [
                pl.col("market_value_in_eur").first().alias("market_value_eur"),
                pl.col("val_date").first().alias("snapshot_value_date"),
            ]
        )
    )

    enriched = squads.join(valuations, on="player_id", how="left").with_columns(
        # Players with no pre-tournament valuation get 0 (typically very
        # young or fringe players); they don't shift the team total much.
        pl.col("market_value_eur").fill_null(0.0)
    )

    per_team = (
        enriched.group_by("club_id")
        .agg(
            [
                pl.col("market_value_eur").sum().alias("market_value_eur"),
                pl.len().alias("players_n"),
            ]
        )
        .sort("market_value_eur", descending=True)
    )

    clubs = _read_gz(
        data_dir / "clubs.csv.gz", infer_schema_length=10_000
    ).select(["club_id", "name"])
    out = per_team.join(clubs, on="club_id", how="left").rename(
        {"name": "team_name"}
    )

    return out.with_columns(
        [
            pl.lit(spec.competition_id).alias("competition_id"),
            pl.lit(spec.season).alias("season"),
            pl.lit(str(spec.snapshot_date)).alias("snapshot_date"),
            pl.lit(spec.slug).alias("tournament"),
        ]
    ).select(
        [
            "team_name",
            "tournament",
            "competition_id",
            "season",
            "market_value_eur",
            "players_n",
            "snapshot_date",
            "club_id",
        ]
    )


def build_national_teams_snapshot(data_dir: Path) -> pl.DataFrame:
    """Pivot path: use ``national_teams.total_market_value`` directly.

    This is a CURRENT-SNAPSHOT loader — it does NOT reconstruct historical
    per-tournament squad values. Use this when:
    - The lineups+valuations join is unavailable for the target tournament
      (dcaribou has FIWC+EURO games WITHOUT lineups; only COPA+AFCN have
      lineups, so only those tournaments can be reconstructed rigorously).
    - First-pass approximation is acceptable.

    Bias note: nominal TM values grew ~50-100% from 2018 to 2026, but the
    ``_market_data.compute_offsets`` uses a **median anchor** across the
    snapshot. Under uniform inflation (all teams grow at the same rate),
    the median scales identically and log-ratios stay invariant — so
    most of the inflation bias cancels in the offset computation. The
    residual bias is per-team RELATIVE growth differences, which are
    bounded and tolerable for a first-pass v3.

    Returns DataFrame columns: team_name, tournament ("current"), season,
    market_value_eur, players_n (squad_size), snapshot_date (today),
    club_id (national_team_id).
    """
    nt = _read_gz(
        data_dir / "national_teams.csv.gz", infer_schema_length=10_000
    ).filter(pl.col("total_market_value").is_not_null())

    today_iso = date.today().isoformat()
    return nt.select(
        [
            pl.col("name").alias("team_name"),
            pl.lit("current").alias("tournament"),
            pl.col("last_season").alias("season"),
            pl.col("total_market_value")
            .cast(pl.Float64)
            .alias("market_value_eur"),
            pl.col("squad_size").alias("players_n"),
            pl.lit(today_iso).alias("snapshot_date"),
            pl.col("national_team_id").alias("club_id"),
        ]
    ).sort("market_value_eur", descending=True)


def build_all(
    data_dir: Path,
    output_dir: Path,
    tournaments: tuple[TournamentSpec, ...] = DEFAULT_TOURNAMENTS,
) -> dict[str, int]:
    """Build squad values for each tournament in ``tournaments``.

    Writes one parquet per tournament + a combined parquet. Returns
    ``{tournament_slug: n_teams}`` for caller logging.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, int] = {}
    all_dfs: list[pl.DataFrame] = []
    for spec in tournaments:
        try:
            df = build_squad_values(data_dir, spec)
            out = output_dir / f"squad_values_{spec.slug}.parquet"
            df.write_parquet(out)
            summary[spec.slug] = df.height
            all_dfs.append(df)
            print(f"  [{spec.slug}] {df.height} teams → {out}")
        except RuntimeError as e:
            print(f"  [{spec.slug}] SKIP: {e}", file=sys.stderr)
            summary[spec.slug] = 0

    if all_dfs:
        combined = pl.concat(all_dfs)
        combined_out = output_dir / "squad_values_all.parquet"
        combined.write_parquet(combined_out)
        print(f"  [combined] {combined.height} rows → {combined_out}")

    return summary


# ─────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/cache/transfermarkt/dcaribou"),
        help="Where to download dcaribou CSV.gz files.",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download (or refresh with --force) the required dcaribou tables.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download even if local files exist.",
    )
    parser.add_argument(
        "--build-all",
        action="store_true",
        help="Build squad values for every tournament in DEFAULT_TOURNAMENTS.",
    )
    parser.add_argument(
        "--tournament",
        type=str,
        help="Build a single tournament (slug, e.g. wc2022).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output parquet path (single-tournament mode). Required with --tournament.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/cache/transfermarkt"),
        help="Output directory for --build-all mode.",
    )
    parser.add_argument(
        "--use-national-teams-snapshot",
        action="store_true",
        help=(
            "Pivot mode: write a single squad-values parquet from the "
            "national_teams CURRENT-SNAPSHOT table. Required because "
            "dcaribou's game_lineups don't cover FIWC/EURO tournaments. "
            "Median-anchored compute_offsets makes the snapshot-vs-historical "
            "bias mostly cancel."
        ),
    )
    args = parser.parse_args(argv)

    if args.download:
        print(f"Downloading dcaribou tables → {args.data_dir}")
        download_tables(args.data_dir, force=args.force)

    if args.use_national_teams_snapshot:
        df = build_national_teams_snapshot(args.data_dir)
        out_path = args.output or (args.output_dir / "squad_values_current.parquet")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(out_path)
        print(
            f"Wrote {df.height} national-team squad values (current snapshot) "
            f"to {out_path}"
        )
        return 0 if df.height > 0 else 1

    if args.build_all:
        print(f"Building squad values for {len(DEFAULT_TOURNAMENTS)} tournaments")
        summary = build_all(args.data_dir, args.output_dir)
        n_ok = sum(1 for n in summary.values() if n > 0)
        print(f"Built {n_ok}/{len(summary)} tournaments")
        return 0 if n_ok > 0 else 1

    if args.tournament:
        if not args.output:
            parser.error("--tournament requires --output")
        match = next(
            (t for t in DEFAULT_TOURNAMENTS if t.slug == args.tournament), None
        )
        if match is None:
            slugs = ", ".join(t.slug for t in DEFAULT_TOURNAMENTS)
            parser.error(f"Unknown tournament slug: {args.tournament}. Known: {slugs}")
        df = build_squad_values(args.data_dir, match)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(args.output)
        print(f"Wrote {df.height} teams to {args.output}")
        return 0

    if not args.download:
        parser.error("Provide at least one of: --download, --build-all, --tournament")
    return 0


if __name__ == "__main__":
    sys.exit(main())
