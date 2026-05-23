"""Tests for the scrape_transfermarkt CLI — --from-csv path (Wave 1.A.3).

The --scrape path is a documented NotImplementedError stub and only its
error-message contract is tested. The --from-csv path is the load-bearing
one for the v3 sprint: operator hand-fills (or pastes from Kaggle) a CSV,
runs --from-csv, gets the parquet that fit_v2_pipeline reads.
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl
import pytest


# Import script as a module; pytest auto-handles the path.
_SCRIPT_DIR = Path(__file__).resolve().parents[3] / "scripts" / "spike" / "wc2026_v3"
sys.path.insert(0, str(_SCRIPT_DIR))
import scrape_transfermarkt as st  # noqa: E402


def _write_csv(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "values.csv"
    pl.DataFrame(rows).write_csv(p)
    return p


def test_convert_csv_to_parquet_happy_path(tmp_path: Path) -> None:
    csv = _write_csv(
        tmp_path,
        [
            {"team_name": "France", "market_value_eur": 1_200_000_000.0},
            {"team_name": "Saudi Arabia", "market_value_eur": 40_000_000.0},
            {"team_name": "Ghana", "market_value_eur": 75_000_000.0},
        ],
    )
    out = tmp_path / "out.parquet"
    n = st.convert_csv_to_parquet(csv, out)
    assert n == 3
    assert out.exists()
    df = pl.read_parquet(out)
    # Sorted by team_name → Ghana < Saudi Arabia < France alphabetically
    assert df["team_name"].to_list() == ["France", "Ghana", "Saudi Arabia"]


def test_convert_creates_parent_dirs(tmp_path: Path) -> None:
    csv = _write_csv(
        tmp_path, [{"team_name": "Brazil", "market_value_eur": 900_000_000.0}]
    )
    out = tmp_path / "nested" / "deep" / "out.parquet"
    st.convert_csv_to_parquet(csv, out)
    assert out.exists()


def test_convert_empty_csv_raises(tmp_path: Path) -> None:
    csv = _write_csv(
        tmp_path,
        [
            {"team_name": "X", "market_value_eur": 100.0},
        ],
    )
    # Drop the row to truly emptify
    pl.DataFrame(
        {"team_name": [], "market_value_eur": []},
        schema={"team_name": pl.String, "market_value_eur": pl.Float64},
    ).write_csv(csv)
    out = tmp_path / "out.parquet"
    with pytest.raises(ValueError, match="Empty CSV"):
        st.convert_csv_to_parquet(csv, out)


def test_convert_missing_csv_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        st.convert_csv_to_parquet(tmp_path / "nope.csv", tmp_path / "out.parquet")


def test_main_from_csv_mode(tmp_path: Path, capsys) -> None:
    csv = _write_csv(
        tmp_path, [{"team_name": "Argentina", "market_value_eur": 600_000_000.0}]
    )
    out = tmp_path / "out.parquet"
    rc = st.main(["--from-csv", str(csv), "--output", str(out)])
    assert rc == 0
    assert out.exists()
    captured = capsys.readouterr()
    assert "Wrote 1 squad values" in captured.out


def test_main_scrape_mode_is_stub(tmp_path: Path) -> None:
    """--scrape is intentionally NotImplemented; protocol is in the docstring."""
    out = tmp_path / "out.parquet"
    with pytest.raises(NotImplementedError, match="not implemented"):
        st.main(["--scrape", "--tournament", "wc2026", "--output", str(out)])


def test_main_requires_a_mode(tmp_path: Path) -> None:
    """Neither --from-csv nor --scrape → argparse error (exit code 2)."""
    out = tmp_path / "out.parquet"
    with pytest.raises(SystemExit) as exc:
        st.main(["--output", str(out)])
    assert exc.value.code == 2
