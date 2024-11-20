"""
API requests against Nadeo Live Services endpoints
"""
from typing import Dict
from tm_lookups import Club, Map
import requests
import json

def get_club_map_pbs(club: Club, map: Map, groupUid="Personal_Best", jwt_token = None) -> Dict:
    """
    Gets dictionary of PBs of Club members on a Map.
    """
    if not jwt_token:
        raise ValueError("Missing a jwt token.")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"nadeo_v1 t={jwt_token}",
    }

    length = 10
    offset = 0

    url = f"https://live-services.trackmania.nadeo.live/api/token/leaderboard/group/{groupUid}/map/{map.uid}/club/{club.clubId}/top?length={length}&offset={offset}"

    # Note that this is a get request
    club_track_records = requests.get(url, headers=headers) 

    return json.loads(club_track_records.text)