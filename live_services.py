import json
from dataclasses import dataclass

import requests

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


def _authorization_headers(jwt_token: str) -> dict[str, str]:
    if not jwt_token:
        raise ValueError("Missing a jwt token.")

    return {
        "Content-Type": "application/json",
        "Authorization": f"nadeo_v1 t={jwt_token}",
    }


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

    response = requests.get(
        f"{LIVE_SERVICES_URL}/api/token/campaigns/official",
        headers=_authorization_headers(jwt_token),
        params={"offset": 0, "length": length},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = json.loads(response.text)
    campaigns = _list_from_payload(payload, "campaigns")

    return [
        Campaign(
            campaign_id=str(item.get("id", item.get("campaignId"))),
            name=str(item["name"]),
        )
        for item in campaigns
    ]


def get_campaign_tracks(campaign_id: str, jwt_token: str) -> list[Track]:
    """Return all maps in a campaign in their official campaign order."""

    response = requests.get(
        f"{LIVE_SERVICES_URL}/api/token/campaign/{campaign_id}/maps",
        headers=_authorization_headers(jwt_token),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = json.loads(response.text)
    maps = _list_from_payload(payload, "maps")

    return [
        Track(
            name=str(item["name"]),
            uid=str(item.get("mapUid") or item["uid"]),
            number=index + 1,
        )
        for index, item in enumerate(maps)
    ]


def get_playable_campaign_tracks(campaign_id: str, jwt_token: str) -> list[Track]:
    """Return the 16 campaign tracks used by the bingo board."""

    tracks = get_campaign_tracks(campaign_id, jwt_token)
    track_by_number = {track.number: track for track in tracks}
    missing_numbers = [
        number for number in PLAYABLE_TRACK_NUMBERS if number not in track_by_number
    ]
    if missing_numbers:
        raise ValueError(f"Campaign is missing track numbers: {missing_numbers}")

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
        f"group/{group_uid}/map/{track.uid}/club/{club.clubId}/top?"
        f"length={length}&offset={offset}"
    )

    # Note that this is a get request
    club_track_pbs = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
    return json.loads(club_track_pbs.text)


def postprocess_club_track_pbs(club_track_pbs: dict) -> dict:
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
    track = _get_track_by_uid(club_track_pbs["mapUid"])

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
