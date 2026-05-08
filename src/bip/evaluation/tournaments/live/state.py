"""In-tournament state: per-team Bayesian λ estimates + player availability.

The state starts from pre-tournament priors (qualifying baselines) and
updates after each completed match. Properties compute the current blended
estimate on the fly — no need to store them separately.

JSON round-trip is supported via .save() / TournamentLiveState.load().
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Effective sample size assigned to the pre-tournament prior.
# A value of 10 means: the prior is worth 10 tournament matches.
# After 3 group-stage matches, the tournament data has 30% weight.
DEFAULT_N_PRIOR = 10


@dataclass
class TeamLiveState:
    """Per-team mutable state updated after each tournament match."""

    team_id: int

    # Pre-tournament priors — set once at initialization, never mutated.
    prior_goals_for: float
    prior_goals_against: float
    prior_corners_for: float
    prior_corners_against: float
    prior_shots_for: float
    prior_sot_for: float

    # Running sums of tournament observations (add to after each match).
    obs_goals_for: float = 0.0
    obs_goals_against: float = 0.0
    obs_corners_for: float = 0.0
    obs_corners_against: float = 0.0
    obs_shots_for: float = 0.0
    obs_sot_for: float = 0.0
    n_matches_played: int = 0

    # How many "equivalent matches" the prior is worth.
    n_prior: int = DEFAULT_N_PRIOR

    # Player availability (api_football_ids as int).
    injured_player_ids: list[int] = field(default_factory=list)
    suspended_player_ids: list[int] = field(default_factory=list)
    yellow_cards: dict[int, int] = field(default_factory=dict)  # id → count

    # ── computed estimates ─────────────────────────────────────────

    @property
    def lambda_goals_for(self) -> float:
        return _blend(self.prior_goals_for, self.obs_goals_for,
                      self.n_matches_played, self.n_prior)

    @property
    def lambda_goals_against(self) -> float:
        return _blend(self.prior_goals_against, self.obs_goals_against,
                      self.n_matches_played, self.n_prior)

    @property
    def lambda_corners_for(self) -> float:
        return _blend(self.prior_corners_for, self.obs_corners_for,
                      self.n_matches_played, self.n_prior)

    @property
    def lambda_corners_against(self) -> float:
        return _blend(self.prior_corners_against, self.obs_corners_against,
                      self.n_matches_played, self.n_prior)

    @property
    def lambda_shots_for(self) -> float:
        return _blend(self.prior_shots_for, self.obs_shots_for,
                      self.n_matches_played, self.n_prior)

    @property
    def lambda_sot_for(self) -> float:
        return _blend(self.prior_sot_for, self.obs_sot_for,
                      self.n_matches_played, self.n_prior)

    def suspension_risk_ids(self) -> list[int]:
        """Players with exactly 1 yellow — one more triggers suspension."""
        return [pid for pid, cnt in self.yellow_cards.items() if cnt == 1]


@dataclass
class TournamentLiveState:
    """Full tournament state: one TeamLiveState per participating team."""

    tournament_slug: str
    team_states: dict[int, TeamLiveState] = field(default_factory=dict)
    completed_match_ids: list[str] = field(default_factory=list)

    def get_team(self, team_id: int) -> TeamLiveState | None:
        return self.team_states.get(team_id)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            json.dump(_to_dict(self), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> TournamentLiveState:
        raw = json.loads(path.read_text())
        return _from_dict(raw)


# ── Bayesian blend ────────────────────────────────────────────────────────────


def _blend(prior: float, obs_sum: float, n_obs: int, n_prior: int) -> float:
    """Weighted average of pre-tournament prior and in-tournament observations.

    Formula: (n_prior * λ_prior + obs_sum) / (n_prior + n_obs)

    When n_obs == 0 (no matches played yet), returns the prior.
    As n_obs grows, the tournament data takes over.
    """
    if n_obs == 0:
        return prior
    return (n_prior * prior + obs_sum) / (n_prior + n_obs)


# ── JSON serialization ────────────────────────────────────────────────────────


def _to_dict(state: TournamentLiveState) -> dict:
    return {
        "tournament_slug": state.tournament_slug,
        "completed_match_ids": state.completed_match_ids,
        "team_states": {
            str(tid): asdict(ts)
            for tid, ts in state.team_states.items()
        },
    }


def _from_dict(raw: dict) -> TournamentLiveState:
    team_states: dict[int, TeamLiveState] = {}
    for k, v in raw.get("team_states", {}).items():
        # JSON keys are always strings; convert back to int.
        v["yellow_cards"] = {int(yk): yv for yk, yv in v.get("yellow_cards", {}).items()}
        team_states[int(k)] = TeamLiveState(**v)
    return TournamentLiveState(
        tournament_slug=raw["tournament_slug"],
        team_states=team_states,
        completed_match_ids=raw.get("completed_match_ids", []),
    )
