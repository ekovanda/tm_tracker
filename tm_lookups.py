"""
Contains dataclasses of mapping objects
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from player import Player
from track import Track


@dataclass
class Club:
    clubId: str
    owner_account_id: str
    owner_alias: Optional[str]


CLUBS: List[Club] = {"Elliot": Club("85915", "7e468ff6-4558-43ce-ad23-591dd86291c0", "Elliot")} 

