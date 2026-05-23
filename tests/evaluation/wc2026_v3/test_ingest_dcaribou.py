"""Tests for the dcaribou ingestion script (Wave 1.A.4).

The download path itself is integration-tested with a real network call
behind ``pytest.mark.network`` (skipped by default — opt-in for the
operator's first run). The join/aggregate logic is validated here with
synthetic mini-CSVs gzipped on the fly into a tmp_path, so the join
correctness is locked in BEFORE we burn 130MB of real download.
"""

from __future__ import annotations

import gzip
import sys
from datetime import date
from pathlib import Path

import polars as pl
import pytest


_SCRIPT_DIR = Path(__file__).resolve().parents[3] / "scripts" / "spike" / "wc2026_v3"
sys.path.insert(0, str(_SCRIPT_DIR))
import ingest_dcaribou as ing  # noqa: E402


def _write_gz(path: Path, df: pl.DataFrame) -> None:
    """Write df as a gzipped CSV at path (mirrors dcaribou's distribution)."""
    csv_bytes = df.write_csv().encode("utf-8")
    with gzip.open(path, "wb") as f:
        f.write(csv_bytes)


def _build_fake_dcaribou(data_dir: Path) -> ing.TournamentSpec:
    """Create a tiny synthetic dcaribou snapshot covering a single fake
    tournament with 3 teams × 3 players each. Returns the TournamentSpec
    pointing at the synthetic tournament.

    Layout:
      - games:    3 games, all in competition FAKE during 2024-06-{10..20}
      - lineups:  9 (team, game, player) rows
      - valuations:
          team A players: 100, 200, 300 (sum 600)
          team B players: 50, 50, 50    (sum 150)
          team C players: 1000, 0, 0    (sum 1000)
        Some have multiple historical rows; latest as of 2024-06-10
        must be picked.
      - clubs:    3 rows mapping club_id → team_name
    """

    spec = ing.TournamentSpec(
        slug="fake2024",
        competition_id="FAKE",
        season=2023,
        start_date=date(2024, 6, 10),
        end_date=date(2024, 6, 20),
    )

    # 3 games covering 3 teams (A vs B, B vs C, A vs C)
    games = pl.DataFrame(
        {
            "game_id": [1, 2, 3, 999],  # 999 = unrelated friendly to ignore
            "competition_id": ["FAKE", "FAKE", "FAKE", "FAKE"],
            "season": [2023, 2023, 2023, 2023],
            "date": ["2024-06-12", "2024-06-15", "2024-06-18", "2023-09-01"],
            "home_club_id": [101, 102, 101, 101],
            "away_club_id": [102, 103, 103, 103],
        }
    )

    # Lineups (one row per starting XI player; 3 per team for simplicity)
    lineups = pl.DataFrame(
        {
            "game_id": [
                1, 1, 1, 1, 1, 1,  # game 1: A players + B players
                2, 2, 2, 2, 2, 2,
                3, 3, 3, 3, 3, 3,
                999, 999, 999,     # friendly: should be excluded
            ],
            "club_id": [
                101, 101, 101, 102, 102, 102,
                102, 102, 102, 103, 103, 103,
                101, 101, 101, 103, 103, 103,
                101, 999, 999,
            ],
            "player_id": [
                1, 2, 3, 4, 5, 6,
                4, 5, 6, 7, 8, 9,
                1, 2, 3, 7, 8, 9,
                10, 11, 12,  # friendly-only player + other-team players (filtered out)
            ],
        }
    )

    # Player valuations: each player has a "latest as of 2024-06-10" value
    # plus older rows that must NOT be picked.
    valuations = pl.DataFrame(
        {
            "player_id": [
                1, 1, 2, 2, 3, 3,
                4, 5, 6,
                7, 7, 8, 9,
            ],
            "date": [
                "2024-05-01", "2023-05-01",  # team A p1: latest 100
                "2024-05-15", "2023-04-01",  # team A p2: latest 200
                "2024-04-01", "2024-07-01",  # team A p3: pick 04-01 (300), NOT 07-01
                "2024-05-10",
                "2024-05-10",
                "2024-05-10",
                "2024-04-01", "2024-05-01",  # team C p7: latest 1000
                "2024-04-01",
                "2024-04-01",
            ],
            "market_value_in_eur": [
                100, 99, 200, 99, 300, 9999,  # team A players
                50, 50, 50,                    # team B players
                999, 1000, 0, 0,               # team C players (p7 has two)
            ],
        }
    )

    clubs = pl.DataFrame(
        {
            "club_id": [101, 102, 103],
            "name": ["Alphaland", "Betaland", "Gammaland"],
        }
    )

    _write_gz(data_dir / "games.csv.gz", games)
    _write_gz(data_dir / "game_lineups.csv.gz", lineups)
    _write_gz(data_dir / "player_valuations.csv.gz", valuations)
    _write_gz(data_dir / "clubs.csv.gz", clubs)

    return spec


# ─────────────────────────────────────────────────────────────────
# build_squad_values — join correctness
# ─────────────────────────────────────────────────────────────────


def test_build_squad_values_three_teams(tmp_path: Path) -> None:
    spec = _build_fake_dcaribou(tmp_path)
    df = ing.build_squad_values(tmp_path, spec)

    # Three teams expected (101, 102, 103), regardless of order.
    assert df.height == 3
    assert set(df["team_name"].to_list()) == {"Alphaland", "Betaland", "Gammaland"}


def test_build_squad_values_aggregates_correctly(tmp_path: Path) -> None:
    """Sanity-check the snapshot logic: latest valuation as of snapshot_date.

    Team A (Alphaland): players 1, 2, 3 → expected sum = 100 + 200 + 300 = 600
    Team B (Betaland): players 4, 5, 6 → expected sum = 50 + 50 + 50 = 150
    Team C (Gammaland): players 7, 8, 9 → expected sum = 1000 + 0 + 0 = 1000
    """
    spec = _build_fake_dcaribou(tmp_path)
    df = ing.build_squad_values(tmp_path, spec).sort("team_name")
    by_team = {row["team_name"]: row["market_value_eur"] for row in df.iter_rows(named=True)}
    assert by_team["Alphaland"] == pytest.approx(600)
    assert by_team["Betaland"] == pytest.approx(150)
    assert by_team["Gammaland"] == pytest.approx(1000)


def test_friendly_game_excluded(tmp_path: Path) -> None:
    """The 2023-09-01 friendly is OUT of the tournament window and must be
    filtered out — its player (10) should not appear in any team's squad."""
    spec = _build_fake_dcaribou(tmp_path)
    df = ing.build_squad_values(tmp_path, spec)
    # Total players across teams must be 9 (3 per team × 3 teams), not 12.
    assert df["players_n"].sum() == 9


def test_post_snapshot_valuation_not_picked(tmp_path: Path) -> None:
    """Player 3 has rows on 2024-04-01 (300) and 2024-07-01 (9999).
    Snapshot date is 2024-06-10, so 9999 must NOT contaminate the sum."""
    spec = _build_fake_dcaribou(tmp_path)
    df = ing.build_squad_values(tmp_path, spec)
    a = df.filter(pl.col("team_name") == "Alphaland")
    assert a["market_value_eur"].item() == pytest.approx(600)


def test_output_schema_contract(tmp_path: Path) -> None:
    """The downstream consumer (Ola 2.A ablation) depends on this schema.
    Lock it in to prevent silent rename drift."""
    spec = _build_fake_dcaribou(tmp_path)
    df = ing.build_squad_values(tmp_path, spec)
    expected_columns = {
        "team_name",
        "tournament",
        "competition_id",
        "season",
        "market_value_eur",
        "players_n",
        "snapshot_date",
        "club_id",
    }
    assert set(df.columns) == expected_columns
    # Tournament + snapshot_date populated as constants
    assert df["tournament"].unique().to_list() == ["fake2024"]
    assert df["snapshot_date"].unique().to_list() == ["2024-06-10"]


def test_missing_tournament_raises(tmp_path: Path) -> None:
    """Empty result (e.g., wrong competition_id) must fail loudly, not
    return an empty parquet that silently breaks Ola 2.A."""
    _build_fake_dcaribou(tmp_path)
    wrong_spec = ing.TournamentSpec(
        slug="nope",
        competition_id="NOT_A_REAL_ID",
        season=2023,
        start_date=date(2024, 6, 10),
        end_date=date(2024, 6, 20),
    )
    with pytest.raises(RuntimeError, match="No games found"):
        ing.build_squad_values(tmp_path, wrong_spec)


# ─────────────────────────────────────────────────────────────────
# build_all CLI orchestration
# ─────────────────────────────────────────────────────────────────


def test_build_all_writes_per_tournament_parquets(tmp_path: Path) -> None:
    spec = _build_fake_dcaribou(tmp_path)
    out_dir = tmp_path / "out"
    summary = ing.build_all(tmp_path, out_dir, tournaments=(spec,))
    assert summary == {"fake2024": 3}
    assert (out_dir / "squad_values_fake2024.parquet").exists()
    # Also writes a combined parquet when ≥ 1 tournament succeeds.
    assert (out_dir / "squad_values_all.parquet").exists()


def test_build_all_continues_when_one_tournament_missing(
    tmp_path: Path, capsys
) -> None:
    """If one tournament is missing from dcaribou, build_all should log
    and continue rather than abort the whole batch."""
    spec_ok = _build_fake_dcaribou(tmp_path)
    spec_missing = ing.TournamentSpec(
        slug="missing",
        competition_id="NOT_A_REAL_ID",
        season=2023,
        start_date=date(2024, 6, 10),
        end_date=date(2024, 6, 20),
    )
    summary = ing.build_all(
        tmp_path, tmp_path / "out", tournaments=(spec_ok, spec_missing)
    )
    assert summary == {"fake2024": 3, "missing": 0}


# ─────────────────────────────────────────────────────────────────
# CLI / argparse
# ─────────────────────────────────────────────────────────────────


def test_main_requires_a_mode(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        ing.main(["--data-dir", str(tmp_path)])
    assert exc.value.code == 2  # argparse error


def test_main_tournament_requires_output(tmp_path: Path) -> None:
    _build_fake_dcaribou(tmp_path)
    with pytest.raises(SystemExit) as exc:
        ing.main(["--data-dir", str(tmp_path), "--tournament", "wc2022"])
    assert exc.value.code == 2


def test_main_tournament_unknown_slug_errors(tmp_path: Path) -> None:
    _build_fake_dcaribou(tmp_path)
    with pytest.raises(SystemExit) as exc:
        ing.main(
            [
                "--data-dir",
                str(tmp_path),
                "--tournament",
                "not-a-real-slug",
                "--output",
                str(tmp_path / "out.parquet"),
            ]
        )
    assert exc.value.code == 2
