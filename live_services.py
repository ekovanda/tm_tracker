"""
API requests against Nadeo Live Services endpoints
"""
from typing import Dict
from tm_lookups import Club, Track, Player
from tm_lookups import PLAYERS, TRACKS
import requests
import json

def get_club_track_pbs(club: Club, track: Track, groupUid="Personal_Best", jwt_token = None) -> Dict:
    """
    Gets dictionary of PBs of Club members on a Track.
    """
    if not jwt_token:
        raise ValueError("Missing a jwt token.")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"nadeo_v1 t={jwt_token}",
    }

    length = 10
    offset = 0

    url = f"https://live-services.trackmania.nadeo.live/api/token/leaderboard/group/{groupUid}/map/{track.uid}/club/{club.clubId}/top?length={length}&offset={offset}"

    # Note that this is a get request
    club_track_pbs = requests.get(url, headers=headers) 
    print(json.loads(club_track_pbs.text))
    return json.loads(club_track_pbs.text)


def postprocess_club_track_pbs(club_track_pbs: Dict) -> Dict:
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
    players = [{"player": None, "pb": None} for _ in range(num_players)]

    for idx, player_info in enumerate(club_track_pbs["top"]):
        players[idx]["player"] = _get_player_by_account_id(player_info["accountId"])
        players[idx]["pb"] = player_info["score"]
    return {"track": track, "players": players} 

def _get_track_by_uid(map_uid: str, tracks = TRACKS) -> Track:
    for track in tracks:
        if track.uid == map_uid:
            return track
    
    raise ValueError(f"No track found for uid {map_uid}")

def _get_player_by_account_id(account_id: str, players=PLAYERS) -> Player:
    for player in players:
        if player.account_id == account_id:
            return player
        
    raise ValueError(f"No player found for account_id {account_id}")


