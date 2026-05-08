"""Bayesian updater: fold a completed match result into TournamentLiveState.

After every tournament match the operator calls BayesianUpdater.update()
to incorporate observed goals / corners / shots and player events (injuries,
bookings). The updated state then feeds the next prediction cycle.

The update is idempotent: passing the same match_id twice is a no-op.

Yellow-card accumulation rules (WC2026):
- 2 yellow cards across group stage → suspended for first knockout match.
- At the group→knockout boundary the operator calls
  wipe_group_stage_bookings() to reset the count.
- Red card → immediate 1-match suspension (handled via suspended_player_ids).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bip.evaluation.tournaments.live.state import TeamLiveState, TournamentLiveState

SUSPENSION_THRESHOLD = 2  # yellow cards needed to trigger suspension


@dataclass(frozen=True)
class TournamentMatchResult:
    """Operator-supplied result for one completed tournament match.

    Stats marked Optional (corners, shots, sot) are set to None when not
    available from the data source — the updater skips those fields gracefully.
    """

    match_id: str
    home_team_id: int
    away_team_id: int

    home_goals: int
    away_goals: int

    home_corners: int | None = None
    away_corners: int | None = None
    home_shots: int | None = None
    away_shots: int | None = None
    home_sot: int | None = None
    away_sot: int | None = None

    # Player events — api_football_ids.
    injured_home: tuple[int, ...] = field(default_factory=tuple)
    injured_away: tuple[int, ...] = field(default_factory=tuple)
    yellow_home: tuple[int, ...] = field(default_factory=tuple)
    yellow_away: tuple[int, ...] = field(default_factory=tuple)
    red_home: tuple[int, ...] = field(default_factory=tuple)
    red_away: tuple[int, ...] = field(default_factory=tuple)


class BayesianUpdater:
    """Mutates TournamentLiveState in place after each match result.

    Usage::

        updater = BayesianUpdater()
        result = TournamentMatchResult(match_id="wc2026_grpA_001", ...)
        updater.update(state, result)
        state.save(Path("state/after_match_001.json"))
    """

    def update(
        self,
        state: TournamentLiveState,
        result: TournamentMatchResult,
    ) -> None:
        """Incorporate one match result. Idempotent on match_id."""
        if result.match_id in state.completed_match_ids:
            return

        state.completed_match_ids.append(result.match_id)
        self._update_side(state, result.home_team_id, result, is_home=True)
        self._update_side(state, result.away_team_id, result, is_home=False)

    def wipe_group_stage_bookings(self, state: TournamentLiveState) -> None:
        """Clear yellow card counts and suspensions at the group→knockout boundary.

        Call once, after all group-stage matches are processed, before
        generating round-of-16 predictions.
        """
        for ts in state.team_states.values():
            ts.yellow_cards.clear()
            ts.suspended_player_ids.clear()

    # ── private ──────────────────────────────────────────────────────────────

    def _update_side(
        self,
        state: TournamentLiveState,
        team_id: int,
        result: TournamentMatchResult,
        *,
        is_home: bool,
    ) -> None:
        ts = state.team_states.get(team_id)
        if ts is None:
            return  # team not registered in this state snapshot

        # Goals
        scored = result.home_goals if is_home else result.away_goals
        conceded = result.away_goals if is_home else result.home_goals
        ts.obs_goals_for += scored
        ts.obs_goals_against += conceded

        # Corners (optional)
        corners_for = result.home_corners if is_home else result.away_corners
        corners_against = result.away_corners if is_home else result.home_corners
        if corners_for is not None and corners_against is not None:
            ts.obs_corners_for += corners_for
            ts.obs_corners_against += corners_against

        # Shots (optional)
        shots = result.home_shots if is_home else result.away_shots
        if shots is not None:
            ts.obs_shots_for += shots

        # SoT (optional)
        sot = result.home_sot if is_home else result.away_sot
        if sot is not None:
            ts.obs_sot_for += sot

        ts.n_matches_played += 1

        # ── Player events ────────────────────────────────────────────────────

        injured = result.injured_home if is_home else result.injured_away
        for pid in injured:
            if pid not in ts.injured_player_ids:
                ts.injured_player_ids.append(pid)

        # Red cards → 1-match suspension
        reds = result.red_home if is_home else result.red_away
        for pid in reds:
            if pid not in ts.suspended_player_ids:
                ts.suspended_player_ids.append(pid)

        # Yellow cards → accumulate, trigger suspension at threshold
        yellows = result.yellow_home if is_home else result.yellow_away
        for pid in yellows:
            ts.yellow_cards[pid] = ts.yellow_cards.get(pid, 0) + 1
            if ts.yellow_cards[pid] >= SUSPENSION_THRESHOLD:
                if pid not in ts.suspended_player_ids:
                    ts.suspended_player_ids.append(pid)
