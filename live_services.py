import json
from dataclasses import dataclass

import requests

from authentication import get_user_agent
from player import PLAYERS, Player
from tm_lookups import Club
from track import TRACKS, Track

REQUEST_TIMEOUT_SECONDS = 30
LIVE_SERVICES_URL = "https://live-services.trackmania.nadeo.live"
PLAYABLE_TRACK_NUMBERS = (1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14, 16, 17, 18, 19)


@dataclass(frozen=True)
class Campaign:
    """Official campaign metadata exposed to the campaign selector."""

    campaign_id: str
    name: str


class LiveServiceError(RuntimeError):
    """Raised when Live Services returns or produces an unusable response."""

    def __init__(
        self,
        message: str,
        *,
        category: str,
        status_code: int | None = None,
        retryable: bool = False,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.status_code = status_code
        self.retryable = retryable
        self.retry_after = retry_after


def _authorization_headers(jwt_token: str) -> dict[str, str]:
    if not jwt_token:
        raise ValueError("Missing a jwt token.")

    return {
        "Content-Type": "application/json",
        "Authorization": f"nadeo_v1 t={jwt_token}",
        "User-Agent": get_user_agent(),
    }


def _get_json(url: str, headers: dict[str, str], **kwargs) -> object:
    try:
        response = requests.get(
            url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS, **kwargs
        )
    except requests.Timeout as error:
        raise LiveServiceError(
            "Live Services request timed out.", category="timeout", retryable=True
        ) from error
    except requests.ConnectionError as error:
        raise LiveServiceError(
            "Live Services connection failed.", category="connection", retryable=True
        ) from error
    except requests.RequestException as error:
        raise LiveServiceError(
            "Live Services request failed.", category="transport", retryable=True
        ) from error

    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        status_code = response.status_code
        if status_code == 401:
            category = "authentication"
        elif status_code == 429:
            category = "rate_limit"
        elif status_code >= 500:
            category = "server"
        else:
            category = "http"
        retry_after = None
        raw_retry_after = getattr(response, "headers", {}).get("Retry-After")
        if raw_retry_after is not None:
            try:
                retry_after = max(0.0, float(raw_retry_after))
            except (TypeError, ValueError):
                retry_after = None
        raise LiveServiceError(
            f"Live Services returned HTTP {status_code}.",
            category=category,
            status_code=status_code,
            retryable=status_code == 429 or status_code >= 500,
            retry_after=retry_after,
        ) from error

    try:
        return json.loads(response.text)
    except json.JSONDecodeError as error:
        raise LiveServiceError(
            "Live Services returned malformed JSON.", category="json"
        ) from error


def _campaign_payload(payload: object) -> list[dict]:
    try:
        return _list_from_payload(payload, "campaignList")
    except (TypeError, ValueError) as error:
        raise LiveServiceError(
            "Live Services returned an invalid campaign payload.", category="payload"
        ) from error


def _list_from_payload(payload: object, key: str) -> list[dict]:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict) and isinstance(payload.get(key), list):
        items = payload[key]
    else:
        raise TypeError(f"Expected a list payload or a '{key}' list.")

    if not all(isinstance(item, dict) for item in items):
        raise ValueError(f"Every item in '{key}' must be an object.")
    return items


def get_official_campaigns(jwt_token: str, length: int = 100) -> list[Campaign]:
    """Return official campaigns available to the authenticated user."""

    payload = _get_json(
        f"{LIVE_SERVICES_URL}/api/token/campaign/official",
        _authorization_headers(jwt_token),
        params={"offset": 0, "length": length},
    )
    campaigns = _campaign_payload(payload)

    try:
        return [
            Campaign(
                campaign_id=str(item.get("id", item.get("campaignId"))),
                name=str(item["name"]),
            )
            for item in campaigns
        ]
    except (KeyError, TypeError) as error:
        raise LiveServiceError(
            "Live Services returned an invalid campaign payload.", category="payload"
        ) from error


def get_campaign_tracks(campaign_id: str, jwt_token: str) -> list[Track]:
    """Return all maps in a campaign in their official campaign order."""

    campaigns_payload = _get_json(
        f"{LIVE_SERVICES_URL}/api/token/campaign/official",
        _authorization_headers(jwt_token),
        params={"offset": 0, "length": 100},
    )
    campaigns = _campaign_payload(campaigns_payload)
    campaign = next(
        (item for item in campaigns if str(item.get("id")) == str(campaign_id)),
        None,
    )
    if campaign is None:
        raise LiveServiceError(
            f"Campaign not found: {campaign_id}.", category="payload"
        )

    playlist = campaign.get("playlist")
    if not isinstance(playlist, list) or not all(
        isinstance(item, dict) and item.get("mapUid") for item in playlist
    ):
        raise LiveServiceError(
            f"Campaign has no valid playlist: {campaign_id}.", category="payload"
        )

    maps_payload = _get_json(
        f"{LIVE_SERVICES_URL}/api/token/map/get-multiple",
        _authorization_headers(jwt_token),
        params={"mapUidList": ",".join(item["mapUid"] for item in playlist)},
    )
    try:
        maps = _list_from_payload(maps_payload, "mapList")
    except (TypeError, ValueError) as error:
        raise LiveServiceError(
            "Live Services returned an invalid map payload.", category="payload"
        ) from error
    try:
        maps_by_uid = {str(item["uid"]): item for item in maps}
    except KeyError as error:
        raise LiveServiceError(
            f"Campaign map metadata is missing: {error}.", category="payload"
        ) from error

    try:
        return [
            Track(
                name=str(maps_by_uid[item["mapUid"]]["name"]),
                uid=str(item["mapUid"]),
                number=index + 1,
            )
            for index, item in enumerate(playlist)
        ]
    except KeyError as error:
        raise LiveServiceError(
            f"Campaign map metadata is missing: {error}.", category="payload"
        ) from error


def get_playable_campaign_tracks(campaign_id: str, jwt_token: str) -> list[Track]:
    """Return the 16 campaign tracks used by the bingo board."""

    tracks = get_campaign_tracks(campaign_id, jwt_token)
    track_by_number = {track.number: track for track in tracks}
    missing_numbers = [
        number for number in PLAYABLE_TRACK_NUMBERS if number not in track_by_number
    ]
    if missing_numbers:
        raise LiveServiceError(
            f"Campaign is missing track numbers: {missing_numbers}",
            category="payload",
        )

    return [track_by_number[number] for number in PLAYABLE_TRACK_NUMBERS]


def get_club_track_pbs(
    club: Club, track: Track, group_uid="Personal_Best", jwt_token=None
) -> dict:
    """
    Gets dictionary of PBs of Club members on a Track.
    """
    headers = _authorization_headers(jwt_token)

    length = 10
    offset = 0

    url = (
        "https://live-services.trackmania.nadeo.live/api/token/leaderboard/"
        f"group/{group_uid}/map/{track.uid}/club/{club.club_id}/top?"
        f"length={length}&offset={offset}"
    )

    payload = _get_json(url, headers)
    if not isinstance(payload, dict):
        raise LiveServiceError(
            "Live Services returned an invalid leaderboard payload.",
            category="payload",
        )
    return payload


def postprocess_club_track_pbs(club_track_pbs: dict, tracks=None) -> dict:
    """
    Returns Dict of:
    {
    "track": Track
    "players": [
            {
            "player": Player,
            "pb": int(pb)
            },
            ...
        ]
    }
    """
    track = _get_track_by_uid(club_track_pbs["mapUid"], tracks=tracks)

    num_players: int = club_track_pbs["length"]
    players: list[dict[str, Player | int | None]] = [
        {"player": None, "pb": None} for _ in range(num_players)
    ]

    for idx, player_info in enumerate(club_track_pbs["top"]):
        players[idx]["player"] = _get_player_by_account_id(player_info["accountId"])
        players[idx]["pb"] = player_info["score"]
    return {"track": track, "players": players}


def _get_track_by_uid(map_uid: str, tracks=None) -> Track:
    tracks = TRACKS if tracks is None else tracks
    for track in tracks:
        if track.uid == map_uid:
            return track

    raise ValueError(f"No track found for uid {map_uid}")


def _get_player_by_account_id(account_id: str, players=None) -> Player:
    players = PLAYERS if players is None else players
    for player in players:
        if player.account_id == account_id:
            return player

    raise ValueError(f"No player found for account_id {account_id}")
