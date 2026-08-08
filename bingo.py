"""Pure domain logic for the Trackmania bingo game."""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from player import PLAYERS, Player
from track import Track

GAME_DURATION = timedelta(hours=5)
LINE_DURATION = timedelta(minutes=10)
PLAYABLE_TRACK_NUMBERS = (1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14, 16, 17, 18, 19)


@dataclass(frozen=True)
class PlayerTime:
    player: Player
    time: int


@dataclass(frozen=True)
class TrackRanking:
    track: Track
    rankings: tuple[PlayerTime, ...]
    owner: Player | None
    margin: int | None


@dataclass(frozen=True)
class BingoState:
    started_at: datetime
    status: str = "active"
    board: tuple[tuple[TrackRanking, ...], ...] = ()
    timer_owner: Player | None = None
    timer_started_at: datetime | None = None
    winner: Player | None = None


def build_bingo_grid(tracks: Iterable[Track]) -> tuple[tuple[Track, ...], ...]:
    """Arrange four tracks from each campaign batch in every row and column."""

    ordered_tracks = list(tracks)
    if len(ordered_tracks) != 16:
        raise ValueError("The bingo grid requires exactly 16 tracks.")

    batches = [ordered_tracks[index : index + 4] for index in range(0, 16, 4)]
    return tuple(
        tuple(batches[(row + column) % 4][(row + column) % 4] for column in range(4))
        for row in range(4)
    )


def rank_track(
    track: Track, player_times: Iterable[dict], players: Iterable[Player] = PLAYERS
) -> TrackRanking:
    """Rank configured players by time and calculate the lead over second place."""

    configured_players = {player.account_id: player for player in players}
    rankings = sorted(
        (
            PlayerTime(configured_players[item["player"].account_id], item["pb"])
            for item in player_times
            if item.get("player") is not None
            and item.get("pb") is not None
            and item["player"].account_id in configured_players
        ),
        key=lambda result: result.time,
    )
    ranked_players = tuple(rankings)
    if not ranked_players:
        return TrackRanking(track, ranked_players, None, None)
    if len(ranked_players) < 2:
        return TrackRanking(track, ranked_players, ranked_players[0].player, None)
    if ranked_players[0].time == ranked_players[1].time:
        return TrackRanking(track, ranked_players, None, None)

    return TrackRanking(
        track,
        ranked_players,
        ranked_players[0].player,
        ranked_players[1].time - ranked_players[0].time,
    )


def _ranking_by_track(records: Iterable[dict]) -> dict[int, TrackRanking]:
    return {
        record["track"].number: rank_track(record["track"], record.get("players", []))
        for record in records
        if record["track"].number in PLAYABLE_TRACK_NUMBERS
    }


def _lines(board: tuple[tuple[TrackRanking, ...], ...]) -> list[tuple[Player, ...]]:
    lines = [*board, *zip(*board)]
    return [
        tuple(cell.owner for cell in line)
        for line in lines
        if all(cell.owner is not None for cell in line)
    ]


def _line_owner(
    board: tuple[tuple[TrackRanking, ...], ...], current_owner: Player | None
) -> Player | None:
    owners = _lines(board)
    if current_owner is not None and any(
        all(owner == current_owner for owner in line) for line in owners
    ):
        return current_owner
    return owners[0][0] if owners else None


def start_bingo(started_at: datetime) -> BingoState:
    """Create a new active bingo game."""

    return BingoState(started_at=started_at)


def stop_bingo(state: BingoState) -> BingoState:
    """Manually stop an active game."""

    if state.status != "active":
        return state
    return replace(state, status="stopped")


def update_bingo_state(
    state: BingoState, records: Iterable[dict], now: datetime
) -> BingoState:
    """Apply rankings and timer transitions without mutating the prior state."""

    if state.status != "active":
        return state
    if now - state.started_at >= GAME_DURATION:
        return replace(state, status="expired")

    rankings = _ranking_by_track(records)
    tracks = [
        rankings[number].track
        if number in rankings
        else Track(str(number), str(number), number=number)
        for number in PLAYABLE_TRACK_NUMBERS
    ]
    grid_tracks = build_bingo_grid(tracks)
    board = tuple(
        tuple(
            rankings.get(track.number, TrackRanking(track, (), None, None))
            for track in row
        )
        for row in grid_tracks
    )
    owner = _line_owner(board, state.timer_owner)
    if owner is None:
        return replace(state, board=board, timer_owner=None, timer_started_at=None)
    timer_started_at = state.timer_started_at
    if state.timer_owner != owner or timer_started_at is None:
        timer_started_at = now
    if now - timer_started_at >= LINE_DURATION:
        return replace(
            state,
            board=board,
            timer_owner=owner,
            timer_started_at=timer_started_at,
            status="completed",
            winner=owner,
        )
    return replace(
        state,
        board=board,
        timer_owner=owner,
        timer_started_at=timer_started_at,
    )
